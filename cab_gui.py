"""P4: PyQt5 + VTK viewer/editor for scSTREAM Pre .cab projects.

Layout aligned with STpre (scSTREAM Pre manual + screenshot):

  Menu: File / Edit / View / Part / Wizard / Mesh / Option / Help
  Toolbars: File | Edit | Display | (Parts) | (Mouse)
  Main: Tree/List View + Control | Draw + Message
  Status bar: coordinates / selection mode / operation / target

Icons, PaneFrame, MessageWindow patterns ported from pph_gui.
"""

from __future__ import annotations

import os
import sys

import cab_vtk
import xemt_export
from cab_container import CabArchive
from cab_icons import AppIcons
from cab_panes import (
    ControlWindow, MessageWindow, PaneFrame, TreeListView,
)
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
from s_export import build_sdat

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import QSize, Qt
    from PyQt5.QtWidgets import (
        QAction, QApplication, QComboBox, QFileDialog, QLabel, QMainWindow,
        QMessageBox, QSplitter, QToolBar,
    )
    from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    import vtk
    try:
        import vtkmodules.vtkInteractionStyle  # noqa: F401
        import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
    except Exception:
        pass
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless environments
    _HAS_GUI_DEPS = False
    QtWidgets = None
    QMainWindow = object  # type: ignore


ST_MANUAL = (r"C:\Program Files\Cradle\CradleCFD2025.2"
             r"\Manuals\ST\HTML\Pre_eng\index.html")


class CabViewer(QMainWindow if _HAS_GUI_DEPS else object):
    """Main window: load / browse / edit / export / rebuild a cab file."""

    def __init__(self, path: str | None = None, enable_3d: bool = True):
        if not _HAS_GUI_DEPS:
            raise RuntimeError("PyQt5/vtk not installed")
        super().__init__()
        self.setWindowTitle("cabdecoding — STpre layout")
        self.resize(1600, 900)
        self._enable_3d = enable_3d
        self.archive: CabArchive | None = None
        self.model: StpreModel | None = None
        self.props: PropertyModel | None = None
        self.actors: list[tuple] = []
        self._layer_actors: dict[str, list] = {
            "domain_frame": [], "axis_global": [], "origin": [],
            "mesh": [], "mesh_block": [], "element": [], "face": [],
        }
        self.current_path: str | None = None
        self._dirty = False
        self._wireframe = False
        self._translucent = False
        self._drawing_mode = "Shading"
        self._hidden_parts: set[str] = set()
        # Domain names in opaque "face mode" (tree checkbox checked)
        self._domain_face_mode: set[str] = set()
        self._recent: list[str] = []
        self._orientation = None
        self._trackball_style = None
        self._rubber_style = None
        self._iren_ready = False
        self._mouse_mode = "trackball"  # trackball | rubber
        self._cad_meshes = None

        self._build_ui()
        self._apply_style()
        self.log("Ready. Open a .cab project to begin.")
        if path:
            self.load(path)

    # ------------------------------------------------------------------ UI

    def log(self, msg: str, level: str = "INFO") -> None:
        if hasattr(self, "message_win"):
            self.message_win.log(msg, level)
        self.statusBar().showMessage(msg, 8000)

    def _nyi(self, name: str) -> None:
        self.log(
            f"[{name}] not available in cab viewer "
            f"(STpre-only / not yet mapped).",
            "WARN")

    def _build_ui(self) -> None:
        self._build_menus()
        self._build_toolbars()

        self.tree_view = TreeListView(self)
        self.tree_view.visibility_changed.connect(self._on_visibility)
        self.tree_view.item_selected.connect(self._on_item_selected)
        self.tree_view.context_action.connect(self._on_context_action)
        # compat alias for older tests
        self.model_tree = self.tree_view.layout_tree

        self.control = ControlWindow(self)
        self.control.drawing_mode_changed.connect(self._set_drawing_mode)
        self.control.layer_toggled.connect(self._on_layer_toggled)
        self.control.selection_target_changed.connect(self._on_sel_target)
        self.control.apply_requested.connect(self._apply_edits)
        self.control.lib_tree.itemSelectionChanged.connect(
            self._on_lib_selected)

        left = QSplitter(Qt.Vertical, self)
        left.addWidget(PaneFrame("Tree/List View", self.tree_view))
        left.addWidget(PaneFrame("Control", self.control))
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 2)
        left.setSizes([420, 280])

        if self._enable_3d:
            self.vtk_widget = QVTKRenderWindowInteractor(self)
            self.renderer = vtk.vtkRenderer()
            self.renderer.SetBackground(0.93, 0.93, 0.94)
            self.renderer.SetBackground2(0.78, 0.82, 0.90)
            self.renderer.GradientBackgroundOn()
            self.renderer.GetActiveCamera().ParallelProjectionOn()
            self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
            draw_body = self.vtk_widget
        else:
            self.vtk_widget = None
            self.renderer = None
            draw_body = QLabel("3D 视图已禁用（headless 测试模式）", self)
            draw_body.setAlignment(Qt.AlignCenter)

        self.draw_pane = PaneFrame("Draw Window", draw_body)
        self.message_win = MessageWindow(self)
        msg_pane = PaneFrame("Message", self.message_win)

        right = QSplitter(Qt.Vertical, self)
        right.addWidget(self.draw_pane)
        right.addWidget(msg_pane)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 1)
        right.setSizes([640, 140])

        main = QSplitter(Qt.Horizontal, self)
        main.addWidget(left)
        main.addWidget(right)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([300, 1200])
        self.setCentralWidget(main)

        # status bar segments
        self._coord_label = QLabel("( —, —, — )")
        self._mode_label = QLabel("Part")
        self._op_label = QLabel("Selection")
        self._target_label = QLabel("Part")
        self._group_label = QLabel("Global mode")
        sb = self.statusBar()
        sb.addPermanentWidget(self._coord_label, 1)
        for w in (self._mode_label, self._op_label,
                  self._target_label, self._group_label):
            sb.addPermanentWidget(w)
        self.status = sb
        sb.showMessage("No project")

        # aliases used by property helpers / tests
        self.prop_fields = self.control.prop_fields

    def _build_menus(self) -> None:
        mb = self.menuBar()

        def add(menu, text, slot=None, shortcut=None):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            if slot:
                act.triggered.connect(slot)
            else:
                act.triggered.connect(
                    lambda _=False, t=text: self._nyi(t))
            menu.addAction(act)
            return act

        m = mb.addMenu("File(&F)")
        add(m, "Open…", self._open_dialog, "Ctrl+O")
        add(m, "Save", self._save, "Ctrl+S")
        add(m, "Save As…", self._save_dialog, "Ctrl+Shift+S")
        m.addSeparator()
        add(m, "Import…")
        add(m, "Export…", self._export_dialog, "Ctrl+E")
        m.addSeparator()
        add(m, "Print")
        add(m, "Execute Solver")
        add(m, "Execute Post")
        m.addSeparator()
        self._recent_menu = m.addMenu("Recent Files")
        add(m, "Exit", self.close, "Alt+F4")

        m = mb.addMenu("Edit(&E)")
        add(m, "Undo")
        add(m, "Redo")
        m.addSeparator()
        add(m, "Deletion of Parts")
        add(m, "Group")
        add(m, "Reset Computational Domain",
            lambda: self._on_item_selected("domain", None))

        m = mb.addMenu("View(&V)")
        add(m, "Fit to DrawWindow", self._fit_view, "Ctrl+F")
        add(m, "Reset DrawWindow", self._reset_view)
        m.addSeparator()
        add(m, "XY Plane", lambda: self._set_plane("xy"))
        add(m, "XZ Plane", lambda: self._set_plane("xz"))
        add(m, "YZ Plane", lambda: self._set_plane("yz"))
        m.addSeparator()
        add(m, "Rubber Box Zoom", lambda: self._set_mouse_mode("rubber"))
        add(m, "Trackball Camera",
            lambda: self._set_mouse_mode("trackball"))
        m.addSeparator()
        self._tb_toggles = []
        for name, attr in (("File Bar", "tb_file"),
                           ("Edit Bar", "tb_edit"),
                           ("Parts Bar", "tb_parts"),
                           ("Mouse Bar", "tb_mouse"),
                           ("Display Bar", "tb_disp")):
            act = QAction(name, self)
            act.setCheckable(True)
            act.setChecked(name != "Parts Bar")
            act.triggered.connect(
                lambda on, a=attr: self._toggle_toolbar(a, on))
            m.addAction(act)
            self._tb_toggles.append(act)

        m = mb.addMenu("Part(&P)")
        for label in ("Cuboid", "Cylinder", "Sphere", "Panel",
                      "Sketch Part", "Fan"):
            add(m, label)

        m = mb.addMenu("Wizard(&W)")
        add(m, "Initial Setting…", self._wizard_initial)
        add(m, "Condition Setting…", self._wizard_condition)

        m = mb.addMenu("Mesh(&G)")
        add(m, "Gridding (read-only)", self._mesh_info)
        add(m, "Checking S-File", self._check_sfile)
        add(m, "Meshing")
        add(m, "Editing Mesh")

        m = mb.addMenu("Option(&O)")
        add(m, "(Mouse) Trackball",
            lambda: self._set_mouse_mode("trackball"))
        add(m, "(Mouse) Rubber Band Zoom",
            lambda: self._set_mouse_mode("rubber"))
        add(m, "Environment Settings")
        add(m, "Detailed Program Settings")

        m = mb.addMenu("Help(&H)")
        add(m, "User's Guide", self._open_manual)
        add(m, "About cabdecoding", self._about)

    def _build_toolbars(self) -> None:
        icon_sz = 22

        def tb(name: str) -> QToolBar:
            bar = QToolBar(name, self)
            bar.setObjectName(name)
            bar.setMovable(False)
            bar.setIconSize(QSize(icon_sz, icon_sz))
            bar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            return bar

        def act(bar, text, icon, tip, slot):
            a = QAction(AppIcons.get(icon, icon_sz), text, self)
            a.setToolTip(tip)
            a.triggered.connect(slot)
            bar.addAction(a)
            return a

        self.tb_file = tb("File")
        act(self.tb_file, "Open", "open", "Open Project (CAB)",
            self._open_dialog)
        act(self.tb_file, "Save", "save", "Save CAB", self._save)
        act(self.tb_file, "Export", "export", "Export .s / .xemt",
            self._export_dialog)
        act(self.tb_file, "Reload", "reload", "Reload Project", self._reload)
        self.addToolBar(self.tb_file)

        self.tb_edit = tb("Edit")
        act(self.tb_edit, "XY", "plane_xy", "XY Plane",
            lambda: self._set_plane("xy"))
        act(self.tb_edit, "XZ", "plane_xz", "XZ Plane",
            lambda: self._set_plane("xz"))
        act(self.tb_edit, "YZ", "plane_yz", "YZ Plane",
            lambda: self._set_plane("yz"))
        act(self.tb_edit, "Fit", "fit", "Fit to DrawWindow", self._fit_view)
        act(self.tb_edit, "Reset", "show_all", "Reset DrawWindow",
            self._reset_view)
        self.addToolBar(self.tb_edit)

        self.tb_disp = tb("Display")
        disp_label = QLabel()
        disp_label.setPixmap(AppIcons.get("display", 18).pixmap(18, 18))
        self.tb_disp.addWidget(disp_label)
        self.tb_display = QComboBox(self)
        self.tb_display.addItems(["Line", "Shading", "Translucent"])
        self.tb_display.setCurrentText("Shading")
        self.tb_display.setMinimumWidth(100)
        self.tb_display.setToolTip(
            "Part drawing: Line / Shading / Translucent\n"
            "勾选 Control→Element division 叠加网格线")
        self.tb_display.currentTextChanged.connect(self._toolbar_display)
        self.tb_disp.addWidget(self.tb_display)
        self.addToolBar(self.tb_disp)

        self.tb_parts = tb("Parts")
        for text, icon in (("Cube", "cube"), ("Cylinder", "cylinder"),
                           ("Sphere", "sphere"), ("Panel", "panel")):
            act(self.tb_parts, text, icon, f"Create {text}",
                lambda _=False, t=text: self._nyi(f"Part — {t}"))
        self.addToolBar(self.tb_parts)
        self.tb_parts.setVisible(False)

        self.tb_mouse = tb("Mouse")
        # Cradle 3-button Trackball（同 pph_gui）：左旋转 / 中平移 / 右缩放
        tips = {
            "Trackball": "Trackball Camera（左键旋转·中键平移·右键/滚轮缩放）",
            "Rubber": "橡皮框缩放（拖拽框选放大）",
            "Fit": "Fit to DrawWindow",
            "Reset": "Reset DrawWindow",
        }
        self._act_trackball = act(
            self.tb_mouse, "Trackball", "rotate", tips["Trackball"],
            lambda: self._set_mouse_mode("trackball"))
        self._act_rubber = act(
            self.tb_mouse, "Rubber", "zoom", tips["Rubber"],
            lambda: self._set_mouse_mode("rubber"))
        act(self.tb_mouse, "Fit", "fit", tips["Fit"], self._fit_view)
        act(self.tb_mouse, "Reset", "show_all", tips["Reset"],
            self._reset_view)
        self._act_trackball.setCheckable(True)
        self._act_rubber.setCheckable(True)
        self._act_trackball.setChecked(True)
        self.addToolBar(self.tb_mouse)

    def _toggle_toolbar(self, attr: str, on: bool) -> None:
        bar = getattr(self, attr, None)
        if bar is not None:
            bar.setVisible(on)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #e8e8e8; }
            QMenuBar { background: #f0f0f0; }
            QToolBar { background: #f5f5f5; border: none; spacing: 2px;
                       padding: 2px; }
            QToolBar QToolButton {
                padding: 2px 6px 1px 6px; margin: 1px;
                border: 1px solid transparent; border-radius: 3px;
            }
            QToolBar QToolButton:hover {
                background: #e3f2fd; border: 1px solid #90caf9;
            }
            QToolBar QToolButton:pressed { background: #bbdefb; }
            #PaneFrame, #PaneBody {
                background: #ffffff;
                border: 1px solid #9a9a9a;
            }
            #PaneBody { border: none; }
            #PaneTitleBar {
                background: #d8d8d8;
                border-bottom: 1px solid #9a9a9a;
            }
            #PaneTitle { font-weight: bold; color: #333; }
        """)

    # ------------------------------------------------------------ loading

    def load(self, path: str) -> bool:
        try:
            raw = open(path, "rb").read()
            archive = CabArchive.parse(raw)
            archive.fill_member_data()
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", str(exc))
            self.log(f"Open failed: {exc}", "ERROR")
            return False
        self.archive = archive
        self.current_path = path
        self._dirty = False
        self._hidden_parts.clear()
        self._domain_face_mode.clear()
        members = {m.name: m.data for m in archive.members}
        xml_name = next(n for n in members if n.endswith(".xml")
                        and not n.startswith("_"))
        prop_name = next(n for n in members if n.endswith("_property.xml"))
        self.model = StpreModel(parse_stpre(members[xml_name]))
        self.props = PropertyModel(parse_property(members[prop_name]))
        self._xml_member = xml_name
        self._prop_member = prop_name
        # Default: Domain face mode ON (matches tree checkbox checked=True)
        self._domain_face_mode = set(self.model.analysis_names())
        self._cad_meshes = None
        xt_name = next((n for n in members if n.endswith(".x_t")), None)
        if xt_name:
            try:
                import ps_facet2_nodes
                if ps_facet2_nodes.available():
                    # STpre's own node path: PK_TOPOL_facet_2 tables
                    # (facet -> fin -> data -> point -> coordinate), with
                    # per-face adaptive refinement for large curved faces.
                    self._cad_meshes = ps_facet2_nodes.tessellate_xt(
                        members[xt_name], adaptive=True)
            except Exception as exc:
                self.log(f"Parasolid facet_2 tessellation skipped: {exc}",
                         "WARN")
                self._cad_meshes = None
            if not self._cad_meshes:
                try:
                    import ps_tessellate
                    if ps_tessellate.available():
                        self._cad_meshes = ps_tessellate.tessellate_xt(
                            members[xt_name])
                except Exception as exc:
                    self.log(
                        f"Parasolid GO tessellation skipped: {exc}", "WARN")
                    self._cad_meshes = None
        self.tree_view.populate(self.model, archive.members)
        self.control.populate_library(self.props)
        self.control.clear_property()
        self._rebuild_scene()
        self._update_title()
        self._add_recent(path)
        boxes = cab_vtk.part_boxes(self.model, self._cad_meshes)
        n_cells = sum(len(b.cells) for b in boxes)
        n_cad = sum(1 for b in boxes if b.cad_polydata is not None)
        self.log(f"Loaded {path}  parts={len(self.model.parts())}  "
                 f"materials={len(self.props.material_names())}  "
                 f"mesh-cells={n_cells}  cad-parts={n_cad}")
        if n_cad:
            self.log(
                f"Part shading uses Parasolid .x_t tessellation "
                f"({n_cad} bodies). Domain tree check: ON=opaque face mesh, "
                f"OFF=volume wireframe (STpre Layout of Parts).",
                "INFO")
        else:
            self.log(
                "Draw geometry = structured-mesh body boxes (element lists). "
                "Install Cradle CFD (pskernel) for smooth .x_t Part shading.",
                "INFO")
        self.statusBar().showMessage(f"已加载 {path}")
        return True

    def _update_title(self) -> None:
        base = "cabdecoding — STpre layout"
        if self.current_path:
            name = os.path.basename(self.current_path)
            mark = " *" if self._dirty else ""
            self.setWindowTitle(f"{base} — {name}{mark}")
        else:
            self.setWindowTitle(base)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_title()

    def _add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        if path in self._recent:
            self._recent.remove(path)
        self._recent.insert(0, path)
        self._recent = self._recent[:8]
        self._recent_menu.clear()
        for p in self._recent:
            act = QAction(p, self)
            act.triggered.connect(lambda _=False, pp=p: self.load(pp))
            self._recent_menu.addAction(act)

    # ------------------------------------------------------------- events

    def _on_item_selected(self, kind: str, name) -> None:
        self.control.show_property(kind, name, self.model, self.props)
        self.prop_fields = self.control.prop_fields
        self._mode_label.setText("Part" if kind == "part" else kind)

    def _on_lib_selected(self) -> None:
        items = self.control.lib_tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole)
        if data:
            self._on_item_selected(data[0], data[1])

    def _on_context_action(self, action: str, kind: str, name) -> None:
        if action == "refer":
            self._on_item_selected(kind, name)

    def _on_visibility(self, kind: str, name: str, visible: bool) -> None:
        if kind == "domain":
            if visible:
                self._domain_face_mode.add(name)
            else:
                self._domain_face_mode.discard(name)
            if self.model is not None:
                self._rebuild_scene()
            return
        if visible:
            self._hidden_parts.discard(name)
        else:
            self._hidden_parts.add(name)
        if not self._enable_3d:
            return
        part_on = self.control.layer_on("part")
        elem_on = self.control.layer_on("element")
        for actor, pname in self.actors:
            if pname == name:
                actor.SetVisibility(1 if (visible and part_on) else 0)
        for actor, pname in getattr(self, "_edge_actors", []):
            if pname == name:
                # Element division independent of Part shading (STpre)
                actor.SetVisibility(1 if (visible and elem_on) else 0)
        if self.renderer:
            self.renderer.GetRenderWindow().Render()

    def _on_layer_toggled(self, key: str, on: bool) -> None:
        # Layers that add/remove geometry need a rebuild.
        if key in ("element", "face", "mesh", "mesh_block") \
                and self.model is not None:
            self._rebuild_scene()
            return
        if key == "part":
            for actor, pname in self.actors:
                show = on and pname not in self._hidden_parts
                actor.SetVisibility(1 if show else 0)
            # keep element edges if Element division is on
        elif key == "axis_global":
            self._set_orientation_marker(on)
        else:
            for actor in self._layer_actors.get(key, []):
                actor.SetVisibility(1 if on else 0)
        if self.renderer and self._enable_3d:
            self.renderer.GetRenderWindow().Render()
        if key in ("sketch_plane", "condition", "aspect_ratio",
                   "axis_sketch") and on:
            self._nyi(f"Drawing layer — {key}")

    def _on_sel_target(self, target: str) -> None:
        self._target_label.setText(target)
        if target != "Part":
            self._nyi(f"Target of selection — {target}")

    def _show_property(self, kind: str, name) -> None:
        """Test / external helper."""
        self.control.show_property(kind, name, self.model, self.props)
        self.prop_fields = self.control.prop_fields

    def _apply_edits(self) -> None:
        kind, name = self.control.prop_target()
        if self.model is None:
            return
        changed = False
        if kind == "part" and name:
            new_name = self.control.field_text("名称")
            material = self.control.field_text("材料")
            color = self.control.field_text("颜色 RGBA")
            if new_name and new_name != name:
                changed = self.model.rename_part(name, new_name) or changed
                name = new_name
            if material:
                changed = self.model.set_part_property(
                    name, material) or changed
            if color:
                parts = color.split(",")[:4]
                if len(parts) == 4 and all(
                        x.strip().lstrip("-").isdigit() for x in parts):
                    rgba = tuple(int(x) for x in parts)
                    changed = self.model.set_part_color(
                        name, rgba) or changed
        elif kind == "value" and name:
            for label, w in list(self.control.prop_fields.items()):
                if label == "名称":
                    continue
                val = self.control.field_text(label)
                changed = self.model.set_value_param(
                    name, label, val) or changed
        if changed:
            self._mark_dirty()
            self.tree_view.populate(self.model, self.archive.members
                                    if self.archive else [])
            self._rebuild_scene()
            self.log("Edits applied (Save CAB to persist)")
            self.statusBar().showMessage("已应用修改（另存为 cab 生效）")

    # ---------------------------------------------------------------- 3D

    def _ensure_interactor(self) -> None:
        """Trackball + observers（对齐 pph_gui View3DTab.showEvent）。"""
        if not self._enable_3d or self.vtk_widget is None or self._iren_ready:
            return
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleTrackballCamera)
        except Exception:
            vtkInteractorStyleTrackballCamera = (
                vtk.vtkInteractorStyleTrackballCamera)
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self._trackball_style = vtkInteractorStyleTrackballCamera()
        iren.SetInteractorStyle(self._trackball_style)
        iren.AddObserver("MouseMoveEvent", self._on_mouse_move, 1.0)
        iren.Initialize()
        self._iren_ready = True
        self._set_orientation_marker(self.control.layer_on("axis_global"))

    def _set_mouse_mode(self, mode: str) -> None:
        if not self._enable_3d or self.vtk_widget is None:
            return
        self._ensure_interactor()
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleRubberBandZoom,
                vtkInteractorStyleTrackballCamera)
        except Exception:
            vtkInteractorStyleRubberBandZoom = (
                vtk.vtkInteractorStyleRubberBandZoom)
            vtkInteractorStyleTrackballCamera = (
                vtk.vtkInteractorStyleTrackballCamera)
        if mode == "rubber":
            style = vtkInteractorStyleRubberBandZoom()
            style.SetRenderOnMouseMove(1)
            self._rubber_style = style
            iren.SetInteractorStyle(style)
            self._mouse_mode = "rubber"
            self._op_label.setText("Rubber")
            self._act_rubber.setChecked(True)
            self._act_trackball.setChecked(False)
            self.log("Mouse: Rubber Band Zoom — drag a box to zoom")
        else:
            self._trackball_style = vtkInteractorStyleTrackballCamera()
            iren.SetInteractorStyle(self._trackball_style)
            self._mouse_mode = "trackball"
            self._op_label.setText("Trackball")
            self._act_trackball.setChecked(True)
            self._act_rubber.setChecked(False)
            self.log("Mouse: Trackball — L-rotate / M-pan / R-zoom / wheel")

    def _set_orientation_marker(self, on: bool) -> None:
        if not self._enable_3d or self.vtk_widget is None:
            return
        if self._orientation is not None:
            try:
                self._orientation.SetEnabled(0)
            except Exception:
                pass
            self._orientation = None
        if not on:
            return
        try:
            iren = self.vtk_widget.GetRenderWindow().GetInteractor()
            self._orientation = cab_vtk.orientation_marker_widget(iren)
        except Exception as exc:
            self.log(f"Orientation marker failed: {exc}", "WARN")

    def _on_mouse_move(self, obj, _event) -> None:
        if self.renderer is None:
            return
        try:
            x, y = obj.GetEventPosition()
            picker = vtk.vtkWorldPointPicker()
            picker.Pick(float(x), float(y), 0.0, self.renderer)
            wx, wy, wz = picker.GetPickPosition()
            # show mm to match STpre / XML units
            self._coord_label.setText(
                f"( {wx * 1000:.4g} , {wy * 1000:.4g} , {wz * 1000:.4g} )")
        except Exception:
            pass

    def _domain_scale(self) -> float:
        """Characteristic length (m) for origin marker sizing."""
        if self.model is None:
            return 0.05
        frame = cab_vtk.domain_frame(self.model)
        if frame is None:
            return 0.05
        b = frame.bounds
        return max(b[1] - b[0], b[3] - b[2], b[5] - b[4], 1e-6)

    def _rebuild_scene(self) -> None:
        if not self._enable_3d or self.model is None or self.renderer is None:
            return
        self._ensure_interactor()
        self.renderer.RemoveAllViewProps()
        self.actors.clear()
        self._edge_actors: list[tuple] = []
        for k in self._layer_actors:
            self._layer_actors[k] = []

        mode = self._drawing_mode
        wire = mode == "Line"
        translucent = mode == "Translucent"
        self._wireframe = wire
        part_on = self.control.layer_on("part")
        # STpre: Element division overlays mesh lines with Part shading
        element_on = self.control.layer_on("element")
        face_on = self.control.layer_on("face")

        boxes = cab_vtk.part_boxes(
            self.model, getattr(self, "_cad_meshes", None))
        for box in boxes:
            # Part shading: CAD mesh when available; Element: mesh boxes
            pd_part = cab_vtk.part_polydata(box, for_part=True)
            pd_elem = cab_vtk.part_polydata(box, for_part=False)
            tree_vis = box.name not in self._hidden_parts
            # STpre Line + Element division = structured face mesh on occupancy
            pd_elem_lines = None
            if element_on or wire:
                pd_elem_lines = cab_vtk.element_division_lines(
                    self.model, box.name)

            # --- Part geometry (Line / Shading / Translucent) ---
            if wire:
                # Line + Element division (STpre): structured face mesh.
                # Line alone: CAD/occupancy edges.
                if element_on and pd_elem_lines is not None:
                    pd_line = pd_elem_lines
                else:
                    pd_line = pd_part
                edge = cab_vtk.edges_actor(
                    pd_line, color=box.color, line_width=1.35)
                edge.SetVisibility(1 if (part_on and tree_vis) else 0)
                self.renderer.AddActor(edge)
                self.actors.append((edge, box.name))
            else:
                mapper = vtk.vtkPolyDataMapper()
                mapper.SetInputData(pd_part)
                actor = vtk.vtkActor()
                actor.SetMapper(mapper)
                prop = actor.GetProperty()
                prop.SetColor(*box.color)
                prop.SetOpacity(0.35 if translucent else 1.0)
                prop.SetInterpolationToGouraud()
                prop.SetAmbient(0.25)
                prop.SetDiffuse(0.85)
                prop.SetSpecular(0.2)
                prop.SetSpecularPower(18)
                actor.SetVisibility(1 if (part_on and tree_vis) else 0)
                self.renderer.AddActor(actor)
                self.actors.append((actor, box.name))

            # --- Element division overlay (Shading/Translucent only) ---
            # In Line mode the part actor already IS the face mesh.
            if (element_on or face_on) and not wire:
                line_w = 1.0 if face_on and not element_on else 1.15
                col = (0.12, 0.12, 0.14) if element_on else (0.2, 0.35, 0.55)
                if element_on:
                    pd_lines = pd_elem_lines if pd_elem_lines is not None \
                        else pd_elem
                else:
                    pd_lines = pd_elem
                mesh_edge = cab_vtk.edges_actor(
                    pd_lines, color=col, line_width=line_w)
                show_e = tree_vis and (element_on or face_on)
                mesh_edge.SetVisibility(1 if show_e else 0)
                self.renderer.AddActor(mesh_edge)
                self._edge_actors.append((mesh_edge, box.name))
                key = "element" if element_on else "face"
                self._layer_actors[key].append(mesh_edge)

        # Domain(cuboid) tree checkbox (STpre Layout of Parts):
        #   checked   → opaque face mesh (面模式)
        #   unchecked → hidden-line volume wireframe (体网格线框)
        mesh_on = self.control.layer_on("mesh")
        mesh_block_on = self.control.layer_on("mesh_block")
        if element_on or mesh_on or mesh_block_on:
            for aname in self.model.analysis_names():
                aboxes = self.model.analysis_boxes(aname)
                if not aboxes:
                    continue
                face_mode = aname in self._domain_face_mode
                if face_mode and not wire and (element_on or mesh_on):
                    # Opaque cyan shell — hides interior parts
                    pd_shell = cab_vtk.element_division_shell(
                        self.model, boxes=aboxes)
                    if pd_shell is not None:
                        shell = cab_vtk.shaded_poly_actor(
                            pd_shell, color=(0.55, 0.78, 0.88),
                            opacity=1.0)
                        shell.SetVisibility(1)
                        self.renderer.AddActor(shell)
                        key = "element" if element_on else "mesh"
                        self._layer_actors[key].append(shell)
                    pd_dom = cab_vtk.element_division_lines(
                        self.model, boxes=aboxes, interior_stride=0,
                        surface_eps=1e-5)
                    if pd_dom is not None:
                        dom_edge = cab_vtk.edges_actor(
                            pd_dom, color=(0.08, 0.10, 0.14),
                            line_width=1.0)
                        self.renderer.AddActor(dom_edge)
                        self._edge_actors.append((dom_edge, aname))
                        key = "element" if element_on else "mesh"
                        self._layer_actors[key].append(dom_edge)
                elif not face_mode and (element_on or mesh_on):
                    # STpre Domain unchecked: dense face-grid cage (see-through).
                    # All 6 faces of the domain brick — no opaque shell, Part
                    # stays visible in the center (matches curvedbox screenshot).
                    pd_dom = cab_vtk.element_division_lines(
                        self.model, boxes=aboxes,
                        interior_stride=0, surface_eps=0.0)
                    if pd_dom is not None:
                        dom_edge = cab_vtk.edges_actor(
                            pd_dom, color=(0.42, 0.54, 0.66),
                            line_width=1.0, opacity=0.9)
                        self.renderer.AddActor(dom_edge)
                        self._edge_actors.append((dom_edge, aname))
                        key = "element" if element_on else "mesh"
                        self._layer_actors[key].append(dom_edge)
                if mesh_block_on and not face_mode:
                    # Coarser magenta Mesh-block overlay (STpre Mesh block)
                    axes = self.model.mesh_axes()
                    nmax = max((len(v) for v in axes.values()), default=2)
                    stride = max(6, nmax // 10)
                    grid = cab_vtk.mesh_block_grid(self.model, stride=stride)
                    if grid is not None and grid.GetNumberOfCells() > 0:
                        mb_actor = cab_vtk.edges_actor(
                            grid, color=(0.82, 0.22, 0.58),
                            line_width=1.8, opacity=0.95)
                        self.renderer.AddActor(mb_actor)
                        self._layer_actors["mesh_block"].append(mb_actor)

        if self.control.layer_on("domain_frame"):
            frame = cab_vtk.domain_frame(self.model)
            if frame:
                pd = cab_vtk._make_box_polydata(frame, wireframe=True)
                mapper = vtk.vtkPolyDataMapper()
                mapper.SetInputData(pd)
                actor = vtk.vtkActor()
                actor.SetMapper(mapper)
                # Bright green outer edges (STpre Domain frame)
                actor.GetProperty().SetColor(0.12, 0.78, 0.28)
                actor.GetProperty().SetOpacity(frame.opacity)
                actor.GetProperty().SetRepresentationToWireframe()
                actor.GetProperty().SetLineWidth(2.4)
                self.renderer.AddActor(actor)
                self._layer_actors["domain_frame"].append(actor)

        # Mesh Block overview when Domain is in face mode (or alone)
        if mesh_block_on:
            face_any = bool(self._domain_face_mode)
            if face_any or not (element_on or mesh_on):
                axes = self.model.mesh_axes()
                nmax = max((len(v) for v in axes.values()), default=2)
                stride = 1 if nmax <= 80 else max(1, nmax // 40)
                grid = cab_vtk.mesh_block_grid(self.model, stride=stride)
                if grid is not None and grid.GetNumberOfCells() > 0:
                    mesh_actor = cab_vtk.edges_actor(
                        grid, color=(0.75, 0.25, 0.55), line_width=1.4)
                    self.renderer.AddActor(mesh_actor)
                    self._layer_actors["mesh_block"].append(mesh_actor)

        self._set_orientation_marker(self.control.layer_on("axis_global"))

        if self.control.layer_on("origin"):
            scale = self._domain_scale()
            src = vtk.vtkSphereSource()
            src.SetRadius(max(scale * 0.008, 1e-4))
            src.SetThetaResolution(16)
            src.SetPhiResolution(16)
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(src.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(0.25, 0.25, 0.25)
            self.renderer.AddActor(actor)
            self._layer_actors["origin"].append(actor)

        self._fit_view()

    def _set_drawing_mode(self, mode: str) -> None:
        # Compat: old "Mesh lines" mode → Shading + Element division
        if mode == "Mesh lines":
            mode = "Shading"
            cb = self.control.layer_checks.get("element")
            if cb is not None and not cb.isChecked():
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)
        self._drawing_mode = mode
        self._wireframe = mode == "Line"
        self._translucent = mode == "Translucent"
        if self.tb_display.currentText() != mode:
            self.tb_display.blockSignals(True)
            idx = self.tb_display.findText(mode)
            if idx >= 0:
                self.tb_display.setCurrentIndex(idx)
            self.tb_display.blockSignals(False)
        self.control.set_drawing_mode(mode)
        if self.model is not None:
            self._rebuild_scene()

    def _toolbar_display(self, mode: str) -> None:
        self._set_drawing_mode(mode)

    def _set_wireframe(self, on: bool) -> None:
        """Compat helper for tests."""
        self._set_drawing_mode("Line" if on else "Shading")

    def _ensure_parallel_camera(self) -> None:
        if self.renderer is None:
            return
        self.renderer.GetActiveCamera().ParallelProjectionOn()

    def _fit_view(self) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self.renderer.GetRenderWindow().Render()

    def _reset_view(self) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        cam = self.renderer.GetActiveCamera()
        cam.SetViewUp(0, 1, 0)
        cam.SetPosition(1, 1, 1)
        cam.SetFocalPoint(0, 0, 0)
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self.renderer.GetRenderWindow().Render()

    def _set_plane(self, plane: str) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        cam = self.renderer.GetActiveCamera()
        cam.SetFocalPoint(0, 0, 0)
        if plane == "xy":
            cam.SetPosition(0, 0, 1)
            cam.SetViewUp(0, 1, 0)
        elif plane == "xz":
            cam.SetPosition(0, -1, 0)
            cam.SetViewUp(0, 0, 1)
        else:
            cam.SetPosition(1, 0, 0)
            cam.SetViewUp(0, 0, 1)
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self.renderer.GetRenderWindow().Render()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._enable_3d:
            self._ensure_interactor()

    # ------------------------------------------------------------ actions

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 cab", "", "scSTREAM project (*.cab);;All (*)")
        if path:
            self.load(path)

    def _reload(self) -> None:
        if self.current_path:
            self.load(self.current_path)
        else:
            self.log("No project open.", "WARN")

    def _save(self) -> None:
        if self.model is None:
            return
        if not self.current_path:
            self._save_dialog()
            return
        if self._rebuild_to(self.current_path):
            self._dirty = False
            self._update_title()

    def _save_dialog(self) -> None:
        if self.model is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为 cab", "", "scSTREAM project (*.cab)")
        if not path:
            return
        if self._rebuild_to(path):
            self.current_path = path
            self._dirty = False
            self._update_title()

    def _rebuild_to(self, path: str) -> bool:
        if self.archive is None or self.model is None:
            return False
        xml_name = getattr(self, "_xml_member", None)
        member = next(
            (m for m in self.archive.members if m.name == xml_name), None)
        if member is None:
            member = next(m for m in self.archive.members
                          if m.name.endswith(".xml")
                          and not m.name.startswith("_"))
        if self.props is not None:
            prop_member = next(
                (m for m in self.archive.members
                 if m.name.endswith("_property.xml")), None)
            if prop_member is not None:
                prop_member.data = self.props.doc.serialize()
        member.data = self.model.doc.serialize()
        data = self.archive.to_bytes(preserve_source_blocks=False)
        with open(path, "wb") as fh:
            fh.write(data)
        self.log(f"Saved {path} ({len(data):,} B)")
        self.statusBar().showMessage(f"已重建 {path} ({len(data):,} B)")
        return True

    def _export_dialog(self) -> None:
        if self.model is None or self.props is None:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "导出", self.model.project_name or "export",
            "S File (*.s);;XEMT File (*.xemt);;S + XEMT (*)")
        if not path:
            return
        base, ext = os.path.splitext(path)
        if not ext:
            ext = ".s"
        wrote = []
        if "XEMT" in selected and "S +" not in selected:
            out = base + ".xemt"
            with open(out, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write(xemt_export.build_emt(self.model, self.props))
            wrote.append(out)
        elif "S +" in selected or selected.startswith("S File") or ext == ".s":
            with open(base + ".s", "w", encoding="utf-8-sig",
                      newline="") as fh:
                fh.write(build_sdat(self.model, self.props))
            wrote.append(base + ".s")
            if "S +" in selected or ext != ".xemt":
                with open(base + ".xemt", "w", encoding="utf-8-sig",
                          newline="") as fh:
                    fh.write(xemt_export.build_emt(self.model, self.props))
                wrote.append(base + ".xemt")
        else:
            with open(base + ".xemt", "w", encoding="utf-8-sig",
                      newline="") as fh:
                fh.write(xemt_export.build_emt(self.model, self.props))
            wrote.append(base + ".xemt")
        self.log("Exported " + ", ".join(wrote))

    def _wizard_initial(self) -> None:
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        ar = self.model.analysis_region()
        base = size = ""
        if ar is not None:
            b = ar.find("base")
            s = ar.find("size")
            base = (b.text or "").strip() if b is not None else ""
            size = (s.text or "").strip() if s is not None else ""
        axes = self.model.mesh_axes()
        msg = (
            f"Project: {self.model.project_name}\n"
            f"Parts: {len(self.model.parts())}\n"
            f"Domain base: {base}\n"
            f"Domain size: {size}\n"
            f"Mesh: "
            f"{len(axes.get('x', []))}×{len(axes.get('y', []))}×"
            f"{len(axes.get('z', []))}\n"
            f"Materials: {len(self.props.material_names()) if self.props else 0}"
        )
        QMessageBox.information(self, "Initial Setting (read-only)", msg)

    def _wizard_condition(self) -> None:
        self.tree_view.tabs.setCurrentWidget(self.tree_view.cond_tree)
        self.log("Condition Setting — select an item in Conditions tab")

    def _mesh_info(self) -> None:
        if self.model is None:
            return
        self._on_item_selected("mesh_block", "RootBlock")
        axes = self.model.mesh_axes()
        self.log(
            f"Mesh block: "
            f"{len(axes.get('x', []))}×{len(axes.get('y', []))}×"
            f"{len(axes.get('z', []))} points")

    def _check_sfile(self) -> None:
        if self.model is None or self.props is None:
            return
        text = build_sdat(self.model, self.props)
        lines = text.splitlines()
        self.log(f"S-File check: {len(lines)} lines, starts with "
                 f"{lines[0][:40]!r}" if lines else "empty")

    def _open_manual(self) -> None:
        if os.path.isfile(ST_MANUAL):
            os.startfile(ST_MANUAL)  # noqa: S606
            self.log(f"Opened manual: {ST_MANUAL}")
        else:
            self.log(f"Manual not found: {ST_MANUAL}", "ERROR")

    def _about(self) -> None:
        QMessageBox.about(
            self, "About",
            "cabdecoding — scSTREAM Pre (.cab) viewer\n"
            "Layout aligned with Cradle STpre / scSTREAM Pre manual.\n"
            "Icons & pane chrome adapted from pph_gui.")


def main(argv: list[str] | None = None) -> int:
    if not _HAS_GUI_DEPS:
        print("PyQt5 / vtk 未安装：python -m pip install -r requirements-gui.txt")
        return 1
    app = QApplication(argv or sys.argv)
    path = None
    args = argv if argv is not None else sys.argv
    if len(args) > 1 and os.path.isfile(args[1]):
        path = args[1]
    win = CabViewer(path)
    win.show()
    if win.vtk_widget is not None:
        win._ensure_interactor()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())

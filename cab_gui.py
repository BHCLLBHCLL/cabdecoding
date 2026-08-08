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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

import cab_vtk
import xemt_export
from cab_container import CabArchive, CabFolder, CabMember
from cab_icons import AppIcons
from cab_panes import (
    ControlWindow, MessageWindow, PaneFrame, TreeListView,
)
from cabxml import (
    PropertyModel, StpreModel, new_property_bytes, new_stpre_bytes,
    parse_property, parse_stpre,
)
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


# M5: dialogs live in cab_dialogs (STpre-style framework, aligned with the
# [Edit Computational Domain] screenshot / Pre_eng manual / STpreParts DLL
# strings).  Aliases keep the historical private names used by tests.
import cab_dialogs  # noqa: E402

_DomainDialog = cab_dialogs.DomainDialog
_GriddingDialog = cab_dialogs.GriddingDialog
_MeshBlockDialog = cab_dialogs.MeshBlockDialog
_PartDialog = cab_dialogs.PartDialog


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
            "mesh": [], "mesh_block": [], "root_block": [],
            "element": [], "face": [], "section": [],
        }
        self.current_path: str | None = None
        self._dirty = False
        self._wireframe = False
        self._translucent = False
        self._drawing_mode = "Shading"
        self._hidden_parts: set[str] = set()
        # Domain names in opaque "face mode" (tree checkbox checked)
        self._domain_face_mode: set[str] = set()
        # Layout of Parts → RootBlock blue wireframe (STpre)
        self._root_block_visible: bool = True
        self._recent: list[str] = []
        self._orientation = None
        self._trackball_style = None
        self._rubber_style = None
        self._iren_ready = False
        self._mouse_mode = "trackball"  # trackball | rubber
        self._cad_meshes = None
        self._undo_stack: list[tuple] = []
        self._redo_stack: list[tuple] = []
        self._undo_limit = 50
        self._log_level = "INFO"
        self._startup_redraw = True
        # Reusable STpre COM session: Gridding/Meshing share one STpre
        # process instead of cold-starting COM + OpenCabFile per click.
        self._stpre_session = None

        self._build_ui()
        self._apply_style()
        self._apply_stored_options()
        if path:
            self.load(path)
        else:
            self._new_project(silent=True)

    # ------------------------------------------------------------------ UI

    def log(self, msg: str, level: str = "INFO") -> None:
        order = {"INFO": 0, "WARN": 1, "ERROR": 2}
        if order.get(level, 0) < order.get(self._log_level, 0):
            return
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
        self.tree_view.item_activated.connect(self._on_item_activated)
        self.tree_view.context_action.connect(self._on_context_action)
        # compat alias for older tests
        self.model_tree = self.tree_view.layout_tree

        self.control = ControlWindow(self)
        self.control.drawing_mode_changed.connect(self._set_drawing_mode)
        self.control.layer_toggled.connect(self._on_layer_toggled)
        self.control.selection_target_changed.connect(self._on_sel_target)
        self.control.apply_requested.connect(self._apply_edits)
        self.control.sketch_action.connect(self._on_sketch_action)
        self.control.layer_apply_requested.connect(self._on_layer_apply)
        self.control.active_part_apply.connect(self._on_active_part_apply)
        self.control.lib_tree.itemSelectionChanged.connect(
            self._on_lib_selected)
        # Opening Control→Sketch should show the sketch plane (STpre-like)
        self.control.tabs.currentChanged.connect(self._on_control_tab)

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
        self.msg_pane = msg_pane
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
        add(m, "New…", self._new_project, "Ctrl+N")
        add(m, "Open…", self._open_dialog, "Ctrl+O")
        add(m, "Save", self._save, "Ctrl+S")
        add(m, "Save As…", self._save_dialog, "Ctrl+Shift+S")
        m.addSeparator()
        add(m, "Import…", self._import_dialog)
        add(m, "Export…", self._export_dialog, "Ctrl+E")
        m.addSeparator()
        add(m, "Print", self._print_dialog)
        add(m, "Execute Solver", self._execute_solver)
        add(m, "Execute Post", self._execute_post)
        m.addSeparator()
        self._recent_menu = m.addMenu("Recent Files")
        add(m, "Exit", self.close, "Alt+F4")

        m = mb.addMenu("Edit(&E)")
        add(m, "Undo", self._undo, "Ctrl+Z")
        add(m, "Redo", self._redo, "Ctrl+Y")
        m.addSeparator()
        add(m, "Deletion of Parts", self._delete_parts_dialog)
        add(m, "Group", self._group_dialog)
        add(m, "Reset Computational Domain", self._domain_dialog)

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
        m.addSeparator()
        self._act_msg = QAction("Show Message Window", self)
        self._act_msg.setCheckable(True)
        self._act_msg.setChecked(True)
        self._act_msg.triggered.connect(self._toggle_message_window)
        m.addAction(self._act_msg)
        self._act_status = QAction("Show Status Bar", self)
        self._act_status.setCheckable(True)
        self._act_status.setChecked(True)
        self._act_status.triggered.connect(self._toggle_status_bar)
        m.addAction(self._act_status)

        m = mb.addMenu("Part(&P)")
        try:
            import cab_parts as _cab_parts_menu
            _part_items = _cab_parts_menu.PART_MENU_ITEMS
        except Exception:
            _part_items = (
                ("Cuboid…", "cube"), ("Cylinder…", "cylinder"),
                ("Sphere…", "sphere"), ("Panel…", "panel"),
            )
        for item in _part_items:
            if item is None:
                m.addSeparator()
                continue
            label, kind = item
            add(m, label,
                lambda _=False, k=kind: self._create_part_dialog(k))

        m = mb.addMenu("Wizard(&W)")
        add(m, "Initial Setting…", self._wizard_initial)
        add(m, "Condition Setting…", self._wizard_condition)

        m = mb.addMenu("Mesh(&G)")
        # Order aligned with STpre [Mesh] menu (Pre_eng manual + net.exe)
        add(m, "Gridding…", self._gridding_dialog)
        add(m, "Meshing", self._meshing_dialog)
        add(m, "Checking Parts Interferences", self._interference_dialog)
        add(m, "Editing Mesh…", self._edit_mesh_dialog)
        add(m, "Showing Element Cross-Section…", self._section_dialog)
        add(m, "Checking S-File…", self._check_sfile_dialog)
        m.addSeparator()
        self._act_stpre_api = QAction(
            "Gridding/Meshing via STpre API", self)
        self._act_stpre_api.setCheckable(True)
        self._act_stpre_api.setChecked(self._stpre_api_enabled())
        self._act_stpre_api.triggered.connect(self._toggle_stpre_api)
        m.addAction(self._act_stpre_api)

        m = mb.addMenu("Option(&O)")
        add(m, "(Mouse) Trackball",
            lambda: self._set_mouse_mode("trackball"))
        add(m, "(Mouse) Rubber Band Zoom",
            lambda: self._set_mouse_mode("rubber"))
        add(m, "Environment Settings", self._environment_settings)
        add(m, "Detailed Program Settings", self._detailed_settings)

        m = mb.addMenu("Help(&H)")
        add(m, "User's Guide", self._open_manual)
        add(m, "Version", self._version_dialog)
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
        act(self.tb_file, "New", "save", "New Project", self._new_project)
        act(self.tb_file, "Open", "open", "Open Project (CAB)",
            self._open_dialog)
        act(self.tb_file, "Import", "import", "Import XT File",
            self._import_dialog)
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
        for text, kind, icon in (
                ("Cuboid", "cube", "cube"),
                ("Hexahedron", "hexahedron", "cube"),
                ("Cylinder", "cylinder", "cylinder"),
                ("Conical", "conical", "cylinder"),
                ("Sphere", "sphere", "sphere"),
                ("Panel", "panel", "panel"),
                ("Quad Panel", "quad_panel", "panel"),
                ("Revolved", "revolved", "cylinder"),
                ("Point", "point", "condition"),
                ("Fan", "fan", "part"),
                ("Axial Fan", "axial_fan", "part"),
                ("Blower", "blower_fan", "part"),
                ("Sketch", "sketch", "panel"),
                ("Pipe", "pipe", "cylinder"),
        ):
            act(self.tb_parts, text, icon, f"Create {text}",
                lambda _=False, k=kind: self._create_part_dialog(k))
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

    def _toggle_message_window(self, on: bool) -> None:
        if hasattr(self, "msg_pane"):
            self.msg_pane.setVisible(on)

    def _toggle_status_bar(self, on: bool) -> None:
        self.statusBar().setVisible(on)

    # ----------------------------------------------------- Option menu

    def _environment_settings(self) -> None:
        """Option -> Environment Settings."""
        try:
            from cab_options import OptionsDialog
        except Exception:
            self.log("cab_options unavailable.", "ERROR")
            return
        dlg = OptionsDialog(self, props=self.props, detailed=False)
        if dlg.exec_():
            self._apply_options(dlg.values())

    def _detailed_settings(self) -> None:
        """Option -> Detailed Program Settings."""
        try:
            from cab_options import OptionsDialog
        except Exception:
            self.log("cab_options unavailable.", "ERROR")
            return
        dlg = OptionsDialog(self, props=self.props, detailed=True)
        if dlg.exec_():
            self._apply_options(dlg.values())

    def _apply_options(self, values: dict) -> None:
        self._undo_limit = int(values.get("undo_levels", 50))
        self._log_level = str(values.get("log_level", "INFO"))
        self.message_win.set_max_blocks(
            int(values.get("message_max_blocks", 2000)))
        mode = values.get("drawing_mode")
        if mode and mode in ("Line", "Shading", "Translucent"):
            self._set_drawing_mode(mode)
        self._toggle_status_bar(bool(values.get("show_status_bar", True)))
        bg = values.get("background", "Gradation")
        if self.renderer is not None:
            if bg == "Black":
                self.renderer.SetBackground(0.0, 0.0, 0.0)
                self.renderer.GradientBackgroundOff()
            elif bg == "White":
                self.renderer.SetBackground(1.0, 1.0, 1.0)
                self.renderer.GradientBackgroundOff()
            else:
                self.renderer.SetBackground(0.93, 0.93, 0.94)
                self.renderer.SetBackground2(0.78, 0.82, 0.90)
                self.renderer.GradientBackgroundOn()
            if self.vtk_widget is not None:
                self.vtk_widget.GetRenderWindow().Render()
        self.log(
            f"Options applied: undo={self._undo_limit}, "
            f"log={self._log_level}, mode={mode}")

    def _apply_stored_options(self) -> None:
        try:
            from cab_options import get_setting
            self._apply_options({
                "undo_levels": int(get_setting("undo_levels", 50)),
                "log_level": str(get_setting("log_level", "INFO")),
                "message_max_blocks": int(
                    get_setting("message_max_blocks", 2000)),
                "drawing_mode": str(get_setting("drawing_mode", "Shading")),
                "show_status_bar":
                    str(get_setting("show_status_bar", "True")) == "True",
                "background": str(get_setting("background", "Gradation")),
            })
        except Exception:
            pass

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

    def _new_project(self, silent: bool = False) -> None:
        """File -> New: initialise an empty cab project in memory.

        The project already contains the two XML members (project definition
        + property library), so File -> Import x_t / domain / gridding /
        meshing can run immediately; Save As persists it as a cab.
        """
        name = "Untitled"
        archive = CabArchive()
        archive.version_minor = 3
        archive.version_major = 1
        archive.cfolders = 1
        archive.cfiles = 0
        archive.flags = 0
        archive.set_id = 0
        archive.i_cabinet = 0
        archive.folders = [CabFolder(coff_cab_start=0, c_cfdata=0,
                                     type_compress=1)]
        xml_name = f"{name}.xml"
        prop_name = f"_{name}_property.xml"
        date, time = 0x575F, 0xA32D
        archive.members = [
            CabMember(name=xml_name, cb_file=0, uoff_folder_start=0,
                      i_folder=0, date=date, time=time, attribs=0x00A0,
                      data=new_stpre_bytes(name)),
            CabMember(name=prop_name, cb_file=0, uoff_folder_start=0,
                      i_folder=0, date=date, time=time, attribs=0x00A0,
                      data=new_property_bytes()),
        ]
        self.archive = archive
        self.current_path = None
        self.model = StpreModel(parse_stpre(archive.members[0].data))
        self.props = PropertyModel(parse_property(archive.members[1].data))
        self._xml_member = xml_name
        self._prop_member = prop_name
        self._cad_meshes = None
        self._hidden_parts.clear()
        self._domain_face_mode = set()
        self._root_block_visible = True
        self._dirty = False
        # Default Domain(100³) + RootBlock + sketch plane so the Draw Window
        # shows STpre-like UV grid / UVW / blue wireframe on startup.
        self._ensure_default_workspace()
        self.tree_view.populate(self.model, archive.members)
        self.control.populate_library(self.props)
        self.control.load_sketch(self.model)
        self.control.clear_property()
        self._rebuild_scene(fit=True)
        self._update_title()
        if not silent:
            self.log(
                "New project created: import an .x_t (File -> Import), "
                "then set the domain, gridding and meshing.")
        else:
            self.log(
                "Ready. Default Domain / RootBlock / Sketch plane shown.",
                "INFO")

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
        self._root_block_visible = True
        members = {m.name: m.data for m in archive.members}
        xml_name = next(n for n in members if n.endswith(".xml")
                        and not n.startswith("_"))
        prop_name = next(n for n in members if n.endswith("_property.xml"))
        self.model = StpreModel(parse_stpre(members[xml_name]))
        self.props = PropertyModel(parse_property(members[prop_name]))
        # Fill gaps from STpre standard_property_ENG.xml (in-memory; saved
        # with the project on next Save).
        try:
            from cab_materials import merge_standard_into
            n_add = merge_standard_into(self.props)
            if n_add:
                self.log(
                    f"Material library merged from STpre standard "
                    f"(+{n_add} entries → "
                    f"{len(self.props.material_names())}).",
                    "INFO")
        except Exception as exc:
            self.log(f"Standard material library merge skipped: {exc}",
                     "WARN")
        self._xml_member = xml_name
        self._prop_member = prop_name
        # Default: Domain face mode ON (matches tree checkbox checked=True)
        self._domain_face_mode = set(self.model.analysis_names())
        self._root_block_visible = self.model.root_block_visible()
        self._cad_meshes = self._tessellate_members(members)
        self._append_primitive_tess()
        self._clear_undo()
        self.tree_view.populate(self.model, archive.members)
        self.control.populate_library(self.props)
        self._ensure_sketch_plane()
        self.control.load_sketch(self.model)
        self.control.clear_property()
        self._rebuild_scene(fit=True)
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

    def _tessellate_members(self, members: dict) -> Optional[list]:
        """Tessellate every ``.x_t``/``.stl`` member (facet_2 first)."""
        xt_names = [n for n in members if n.endswith(".x_t")]
        stl_names = [n for n in members if n.endswith(".stl")]
        if not xt_names and not stl_names:
            return None
        out: list = []
        if xt_names:
            try:
                from cab_options import get_setting
                facet_tol = float(get_setting("facet_tol", 1e-4))
                facet_angle = float(get_setting("facet_angle", 12.0))
            except Exception:
                facet_tol, facet_angle = 1e-4, 12.0
            try:
                import ps_facet2_nodes
                if ps_facet2_nodes.available():
                    for xt_name in xt_names:
                        try:
                            out += ps_facet2_nodes.tessellate_xt(
                                members[xt_name], adaptive=True,
                                facet_tol=facet_tol,
                                facet_angle_deg=facet_angle)
                        except Exception as exc:
                            self.log(
                                f"facet_2 tessellation skipped {xt_name}: "
                                f"{exc}", "WARN")
            except Exception as exc:
                self.log(f"Parasolid facet_2 tessellation skipped: {exc}",
                         "WARN")
            if not out:
                try:
                    import ps_tessellate
                    if ps_tessellate.available():
                        for xt_name in xt_names:
                            try:
                                out += ps_tessellate.tessellate_xt(
                                    members[xt_name], facet_tol=facet_tol,
                                    facet_angle_deg=facet_angle)
                            except Exception as exc:
                                self.log(
                                    f"GO tessellation skipped {xt_name}: "
                                    f"{exc}", "WARN")
                except Exception as exc:
                    self.log(
                        f"Parasolid GO tessellation skipped: {exc}", "WARN")
        if stl_names:
            try:
                import cab_import
                import ps_facet2_nodes as _f2
                for name in stl_names:
                    pts, tris = cab_import.parse_stl_bytes(members[name])
                    out.append(_f2.TessPart(
                        name=Path(name).stem, points=pts,
                        triangles=tris.astype(np.int32), tag=0))
            except Exception as exc:
                self.log(f"STL member rebuild skipped: {exc}", "WARN")
        return out or None

    # ------------------------------------------------------- undo / redo

    def _snapshot(self) -> tuple:
        xml = self.model.doc.serialize() if self.model is not None else None
        prop = self.props.doc.serialize() if self.props is not None else None
        return (xml, prop)

    def _restore_snapshot(self, snap: tuple) -> None:
        xml, prop = snap
        if xml is not None:
            self.model = StpreModel(parse_stpre(xml))
        if prop is not None:
            self.props = PropertyModel(parse_property(prop))
        members = {m.name: m.data for m in self.archive.members} \
            if self.archive is not None else {}
        self._cad_meshes = self._tessellate_members(members)
        self._append_primitive_tess()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self.control.populate_library(self.props)
        self.control.load_sketch(self.model)
        self._rebuild_scene(fit=True)
        self._mark_dirty()
        self._update_title()

    def _push_undo(self, snap: tuple) -> None:
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _clear_undo(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _undo(self) -> None:
        if not self._undo_stack:
            self.log("Nothing to undo.", "WARN")
            return
        self._redo_stack.append(self._snapshot())
        self._restore_snapshot(self._undo_stack.pop())
        self.log("Undo")

    def _redo(self) -> None:
        if not self._redo_stack:
            self.log("Nothing to redo.", "WARN")
            return
        self._undo_stack.append(self._snapshot())
        self._restore_snapshot(self._redo_stack.pop())
        self.log("Redo")

    # ------------------------------------------------- Edit: delete/group

    def _delete_parts_dialog(self) -> None:
        """Edit -> Deletion of Parts: multi-select removal dialog."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
        )
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Deletion of Parts")
        lay = QVBoxLayout(dlg)
        lst = QListWidget(dlg)
        lst.setSelectionMode(QListWidget.MultiSelection)
        for p in self.model.parts():
            QListWidgetItem(p.name, lst)
        lay.addWidget(lst)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        btn_del = QPushButton("Delete", dlg)
        btn_close = QPushButton("Close", dlg)
        row.addWidget(btn_del)
        row.addWidget(btn_close)
        lay.addLayout(row)
        deleted: list[str] = []

        def _do_delete() -> None:
            names = [lst.item(i).text() for i in range(lst.count())
                     if lst.item(i).isSelected()]
            if not names:
                self.log("Deletion of Parts: select at least one part.",
                         "WARN")
                return
            if QMessageBox.question(
                    dlg, "Deletion of Parts",
                    f"Delete {len(names)} part(s)?") != QMessageBox.Yes:
                return
            snap = self._snapshot()
            for n in names:
                self.model.delete_part(n)
                self._cad_meshes = [
                    m for m in (self._cad_meshes or [])
                    if getattr(m, "name", None) != n]
            deleted.extend(names)
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            self._rebuild_scene()
            self.log(f"Deletion of Parts: removed {', '.join(names)}")

        btn_del.clicked.connect(_do_delete)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec_()

    def _group_dialog(self) -> None:
        """Edit -> Group: create a group and move parts into it."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QLineEdit, QListWidget, QListWidgetItem, QPushButton,
            QVBoxLayout,
        )
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Group")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Group name (empty = ungroup)", dlg))
        edit = QLineEdit(dlg)
        edit.setPlaceholderText("e.g. my_group")
        lay.addWidget(edit)
        lst = QListWidget(dlg)
        lst.setSelectionMode(QListWidget.MultiSelection)
        for p in self.model.parts():
            QListWidgetItem(p.name, lst)
        lay.addWidget(lst)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        btn_ok = QPushButton("Apply", dlg)
        btn_close = QPushButton("Close", dlg)
        row.addWidget(btn_ok)
        row.addWidget(btn_close)
        lay.addLayout(row)

        def _apply() -> None:
            names = [lst.item(i).text() for i in range(lst.count())
                     if lst.item(i).isSelected()]
            if not names:
                self.log("Group: select at least one part.", "WARN")
                return
            snap = self._snapshot()
            moved = self.model.move_parts_to_group(
                names, edit.text().strip())
            if not moved:
                return
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            self._rebuild_scene()
            self.log(f"Group: moved {len(moved)} part(s) into "
                     f"'{edit.text().strip() or '(root)'}'")

        btn_ok.clicked.connect(_apply)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec_()

    # ------------------------------------------------------------- events

    def _on_item_selected(self, kind: str, name) -> None:
        self.control.show_property(kind, name, self.model, self.props)
        self.prop_fields = self.control.prop_fields
        self._mode_label.setText("Part" if kind == "part" else kind)

    def _on_item_activated(self, kind: str, name) -> None:
        """Double-click behaviour (STpre tree): Domain -> edit dialog;
        RootBlock -> Mesh:block dialog; part -> part edit dialog."""
        if kind == "domain":
            self._domain_dialog()
        elif kind == "mesh_block":
            self._mesh_block_dialog()
        elif kind == "part" and name:
            self._part_dialog(name)

    def _on_lib_selected(self) -> None:
        items = self.control.lib_tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole)
        if data:
            self._on_item_selected(data[0], data[1])

    def _on_context_action(self, action: str, kind: str, name) -> None:
        if action == "refer":
            if kind == "domain":
                self._domain_dialog()
            elif kind == "mesh_block":
                self._mesh_block_dialog()
            elif kind == "part" and name:
                self._part_dialog(name)
            else:
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
        if kind == "mesh_block":
            # Layout → RootBlock: blue AABB wireframe (not Drawing→Mesh block)
            self._root_block_visible = visible
            if self.model is not None:
                self.model.set_root_block_visible(visible)
            for actor in self._layer_actors.get("root_block", []):
                actor.SetVisibility(1 if visible else 0)
            if self.renderer and self._enable_3d:
                # Rebuild if actors were never created (e.g. first check-on)
                if visible and not self._layer_actors.get("root_block"):
                    self._rebuild_scene(fit=False)
                else:
                    self.renderer.GetRenderWindow().Render()
            return
        if kind in ("domain_face", "others"):
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
        elif key in ("sketch_plane", "axis_sketch"):
            if self.model is not None:
                # Keep camera — auto-fit was making the grid look "wrong"
                # and washing out the UVW / Origin triad.
                if key == "sketch_plane" and on:
                    cb = self.control.layer_checks.get("axis_sketch")
                    if cb is not None and not cb.isChecked():
                        cb.blockSignals(True)
                        cb.setChecked(True)
                        cb.blockSignals(False)
                self._rebuild_scene(fit=False)
            return
        else:
            for actor in self._layer_actors.get(key, []):
                actor.SetVisibility(1 if on else 0)
        if self.renderer and self._enable_3d:
            self.renderer.GetRenderWindow().Render()
        if key in ("condition", "aspect_ratio") and on:
            self._nyi(f"Drawing layer — {key}")

    def _on_control_tab(self, index: int) -> None:
        """Show/Select ↔ Sketch: turn Sketch plane Drawing On when needed."""
        try:
            w = self.control.tabs.widget(index)
        except Exception:
            return
        if w is getattr(self.control, "sketch_page", None):
            cb = self.control.layer_checks.get("sketch_plane")
            if cb is not None and not cb.isChecked():
                cb.setChecked(True)  # emits layer_toggled → rebuild
            elif self.model is not None:
                self._rebuild_scene()

    def _ensure_drawing_layers(self, *keys: str) -> None:
        """Turn on Drawing On/Off checkboxes without cascading rebuilds."""
        for key in keys:
            cb = self.control.layer_checks.get(key)
            if cb is not None and not cb.isChecked():
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)

    def _ensure_default_workspace(self) -> None:
        """New-project defaults: Domain 100³ mm, RootBlock, sketch plane."""
        if self.model is None:
            return
        if self.model.analysis_region() is None:
            self.model.ensure_domain(
                name="Domain(cuboid)",
                base=(0.0, 0.0, 0.0),
                size=(100.0, 100.0, 100.0),
                unit="mm",
                material="air(incompressible/20C)",
            )
        # Always materialise mesh_block so Layout→RootBlock + Mesh:block work
        bb = self.model.root_block_bounds() or (
            0.0, 0.0, 0.0, 100.0, 100.0, 100.0)
        if self.model.mesh_block() is None:
            self.model.set_root_block_range(
                (bb[0], bb[1], bb[2]), (bb[3], bb[4], bb[5]),
                name="RootBlock")
        self._root_block_visible = True
        self.model.set_root_block_visible(True)
        # STpre default Sketch Plane (Δ=5, Min=-25, Max=125 mm) — not
        # fit_plane_to_domain, which would rewrite interval to span/10.
        try:
            import cab_sketch
            plane = cab_sketch.default_sketch_plane(self.model)
            cab_sketch.apply_plane(self.model, plane)
        except Exception:
            self._ensure_sketch_plane(force_fit=False)
        self._ensure_drawing_layers(
            "sketch_plane", "axis_sketch", "axis_global",
            "domain_frame", "origin")

    def _ensure_sketch_plane(self, *, force_fit: bool = False) -> None:
        """Create/fit ``<sketch_control>`` from the computational domain."""
        if self.model is None:
            return
        try:
            import cab_sketch
        except Exception:
            return
        from cabxml import _first
        sc = _first(self.model.root, "sketch_control")
        if sc is None:
            cab_sketch.apply_plane(
                self.model, cab_sketch.default_sketch_plane(self.model))
        elif force_fit:
            # Explicit Fit / Reset paths may call with force_fit=True
            if self.model.analysis_region() is not None:
                plane = cab_sketch.reset_plane_to_domain(self.model)
                plane = cab_sketch.fit_plane_to_domain(self.model, plane)
            else:
                plane = cab_sketch.default_sketch_plane(self.model)
            cab_sketch.apply_plane(self.model, plane)

    def _on_sketch_action(self, mode: str) -> None:
        """Control -> Sketch: update / reset / fit the sketch plane."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        try:
            import cab_sketch
        except Exception:
            self.log("cab_sketch unavailable.", "ERROR")
            return
        if mode == "reset":
            plane = cab_sketch.reset_plane_to_domain(self.model)
        elif mode == "fit":
            plane = cab_sketch.fit_plane_to_domain(
                self.model, self.control.sketch_plane())
        else:
            plane = self.control.sketch_plane()
        cab_sketch.apply_plane(self.model, plane)
        # Applying sketch settings should make the plane visible
        cb = self.control.layer_checks.get("sketch_plane")
        if cb is not None and not cb.isChecked():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self.control.load_sketch(self.model)
        self._rebuild_scene()
        self._mark_dirty()
        self._update_title()
        self.log(
            f"Sketch plane {mode}: origin={plane.origin}, "
            f"U={plane.u}, W={plane.w}, grid "
            f"u={plane.u_range}, v={plane.v_range}")

    def _on_sel_target(self, target: str) -> None:
        self._target_label.setText(target)
        if target == "Detail":
            self._nyi("Drawing On/Off — Detail…")
            return
        if target not in ("Part", "Parts"):
            self._nyi(f"Target of selection — {target}")

    def _on_layer_apply(self) -> None:
        """Control → Layer → Apply: filter part visibility by Display Layer."""
        if self.model is None:
            return
        visible = self.control.display_layer_set()
        op = self.control.operating_layer()
        from cabxml import _first
        for p in self.model.parts():
            el = self.model.find_part(p.name)
            layer = 1
            if el is not None:
                c = _first(el, "layer")
                if c is not None and c.text and c.text.strip().isdigit():
                    layer = int(c.text.strip())
            hide = layer not in visible
            if hide:
                self._hidden_parts.add(p.name)
            else:
                self._hidden_parts.discard(p.name)
        self._rebuild_scene()
        self.log(
            f"Layer Apply: display={sorted(visible)}, operating={op}")

    def _on_active_part_apply(self, name: str) -> None:
        if name:
            self._on_item_selected("part", name)
            self.log(f"ActivePart Apply: {name}")

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

    def _rebuild_scene(self, *, fit: bool = False) -> None:
        """Rebuild Draw Window actors.

        ``fit=True`` resets the camera (load / import / Fit). Layer toggles
        such as Sketch plane must pass ``fit=False`` so enabling the grid
        does not yank the view or make axes appear to vanish.
        """
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
                    # Interior mesh-block grid only (nmax>2); outer blue
                    # silhouette is Layout→RootBlock.
                    axes = self.model.mesh_axes()
                    nmax = max((len(v) for v in axes.values()), default=0)
                    if nmax > 2:
                        stride = max(6, nmax // 10)
                        grid = cab_vtk.mesh_block_grid(
                            self.model, stride=stride)
                        if grid is not None and grid.GetNumberOfCells() > 0:
                            mb_actor = cab_vtk.edges_actor(
                                grid, color=(0.82, 0.22, 0.58),
                                line_width=1.8, opacity=0.95)
                            self.renderer.AddActor(mb_actor)
                            self._layer_actors["mesh_block"].append(
                                mb_actor)

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

        # Layout of Parts → RootBlock: STpre thin blue AABB wireframe
        # (independent of Mesh→Gridding / Drawing→Mesh block dense grid)
        if self._root_block_visible:
            try:
                rb_actor = cab_vtk.root_block_actor(self.model)
            except Exception as exc:
                self.log(f"RootBlock draw failed: {exc}", "WARN")
                rb_actor = None
            if rb_actor is not None:
                self.renderer.AddActor(rb_actor)
                self._layer_actors.setdefault("root_block", []).append(
                    rb_actor)

        # STpre sketch plane (major/minor grid) + U/V/W arrow triad
        try:
            import cab_sketch
            plane = cab_sketch.plane_from_xml(self.model)
        except Exception:
            plane = None
        if plane is not None and self.control.layer_on("sketch_plane"):
            try:
                for sk_actor in cab_vtk.sketch_plane_actors(plane):
                    self.renderer.AddActor(sk_actor)
                    self._layer_actors.setdefault(
                        "sketch_plane", []).append(sk_actor)
            except Exception as exc:
                self.log(f"Sketch plane draw failed: {exc}", "WARN")
            # UVW triad travels with the sketch plane (STpre); Axis(Sketch)
            # can still hide it independently.
            if self.control.layer_on("axis_sketch"):
                try:
                    for ax_actor in cab_vtk.sketch_axes_actors(plane):
                        self.renderer.AddActor(ax_actor)
                        self._layer_actors.setdefault(
                            "axis_sketch", []).append(ax_actor)
                except Exception as exc:
                    self.log(f"Sketch axes draw failed: {exc}", "WARN")
        elif plane is not None and self.control.layer_on("axis_sketch"):
            # Axes without grid still allowed
            try:
                for ax_actor in cab_vtk.sketch_axes_actors(plane):
                    self.renderer.AddActor(ax_actor)
                    self._layer_actors.setdefault(
                        "axis_sketch", []).append(ax_actor)
            except Exception as exc:
                self.log(f"Sketch axes draw failed: {exc}", "WARN")

        # Drawing→Mesh block: dense *interior* grid only (many axis points).
        # Outer blue AABB is Layout→RootBlock above — do not substitute a
        # magenta cage for the 2-point RootBlock silhouette.
        if mesh_block_on:
            axes = self.model.mesh_axes()
            nmax = max((len(v) for v in axes.values()), default=0)
            if nmax > 2:
                face_any = bool(self._domain_face_mode)
                if face_any or not (element_on or mesh_on):
                    stride = 1 if nmax <= 80 else max(1, nmax // 40)
                    grid = cab_vtk.mesh_block_grid(
                        self.model, stride=stride)
                    if grid is not None and grid.GetNumberOfCells() > 0:
                        mesh_actor = cab_vtk.edges_actor(
                            grid, color=(0.75, 0.25, 0.55),
                            line_width=1.4)
                        self.renderer.AddActor(mesh_actor)
                        self._layer_actors["mesh_block"].append(
                            mesh_actor)

        self._set_orientation_marker(self.control.layer_on("axis_global"))

        if self.control.layer_on("origin"):
            # World-origin hub only. Global XYZ = corner Axis(Global);
            # local UVW = Axis(Sketch) on the sketch plane.
            scale = self._domain_scale()
            for actor in cab_vtk.world_origin_marker_actors(scale):
                self.renderer.AddActor(actor)
                self._layer_actors["origin"].append(actor)

        if fit:
            self._fit_view()
        elif self.renderer.GetRenderWindow() is not None:
            self.renderer.GetRenderWindow().Render()

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
            # First paint: re-draw default RootBlock / sketch after the
            # render window is realized (init-time VTK draw can be empty).
            if getattr(self, "_startup_redraw", True) and self.model is not None:
                self._startup_redraw = False
                self._rebuild_scene(fit=True)

    # ------------------------------------------------------------ actions

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 cab", "", "scSTREAM project (*.cab);;All (*)")
        if path:
            self.load(path)

    def _import_dialog(self) -> None:
        """File -> Import: add an .x_t file as new parts + cab member."""
        if self.model is None or self.archive is None:
            self.log("No project open.", "WARN")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Geometry", "",
            "Geometry (*.x_t *.xmt_txt *.step *.stp *.stl *.sat *.sab);;"
            "Parasolid XT (*.x_t *.xmt_txt);;STEP (*.step *.stp);;"
            "STL (*.stl);;ACIS SAT (*.sat *.sab);;All files (*)")
        if not path:
            return
        snap = self._snapshot()
        try:
            import cab_import
            if not cab_import.available():
                QMessageBox.warning(
                    self, "导入不可用",
                    "未找到 Cradle pskernel.dll，无法导入 x_t。")
                return
            bodies, raw, fmt = cab_import.import_file_with_payload(path)
            if not bodies:
                QMessageBox.warning(
                    self, "导入失败", "文件中没有可显示的 body。")
                return
            if fmt == "stl":
                member = cab_import.add_stl_member(
                    self.archive, raw,
                    name=Path(path).stem + ".stl")
                added = cab_import.register_parts(
                    self.model, bodies, kind="polygon")
            else:
                member = cab_import.add_xt_member(self.archive, raw)
                self.model.add_body_file(member.name)
                added = cab_import.register_parts(self.model, bodies)
            self._cad_meshes = list(self._cad_meshes or []) + \
                [b.tess for b in bodies]
            # Tree checkboxes reset to ON — clear stale hide flags so the
            # new CAD is actually drawn (was easy to confuse with Origin).
            self._hidden_parts.clear()
            self._push_undo(snap)
            self.tree_view.populate(self.model, self.archive.members)
            self._ensure_sketch_plane(force_fit=True)
            self.control.load_sketch(self.model)
            # Imported CAD defaults to Shading (even if Options/toolbar is Line)
            self._drawing_mode = "Shading"
            self._wireframe = False
            self._translucent = False
            if self.tb_display.currentText() != "Shading":
                self.tb_display.blockSignals(True)
                idx = self.tb_display.findText("Shading")
                if idx >= 0:
                    self.tb_display.setCurrentIndex(idx)
                self.tb_display.blockSignals(False)
            self.control.set_drawing_mode("Shading")
            self._rebuild_scene(fit=True)
            self._mark_dirty()
            skipped = len(bodies) - len(added)
            self.log(
                f"Imported {path}: {len(bodies)} bodies -> {member.name}, "
                f"parts added: {', '.join(added) or '-'}"
                + (f", {skipped} duplicate name(s) skipped" if skipped else ""))
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            self.log(f"Import failed: {exc}", "ERROR")

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

    # ------------------------------------------------------ File: Print

    def _render_window_png(self) -> Optional[bytes]:
        """Snapshot of the Draw window as PNG bytes (None when no 3D)."""
        if self.renderer is None or self.vtk_widget is None:
            return None
        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(self.vtk_widget.GetRenderWindow())
        w2i.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetWriteToMemory(True)
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()
        res = writer.GetResult()
        return bytes(res) if res is not None else None

    def _print_to_png(self, path: str) -> bool:
        png = self._render_window_png()
        if png is None:
            self.log("Print: 3D view is disabled.", "WARN")
            return False
        with open(path, "wb") as fh:
            fh.write(png)
        self.log(f"Print: saved Draw window snapshot to {path}")
        return True

    def _print_dialog(self) -> None:
        """File -> Print: snapshot preview + Save PNG / system print."""
        png = self._render_window_png()
        if png is None:
            QMessageBox.warning(self, "Print", "3D 视图不可用，无法打印。")
            return
        from PyQt5.QtGui import QImage, QPixmap
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Print")
        lay = QtWidgets.QVBoxLayout(dlg)
        img = QImage.fromData(png)
        lab = QLabel(dlg)
        lab.setPixmap(QPixmap.fromImage(img).scaled(
            720, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(lab)
        row = QtWidgets.QHBoxLayout()
        btn_png = QtWidgets.QPushButton("Save PNG…", dlg)
        btn_print = QtWidgets.QPushButton("Print…", dlg)
        btn_close = QtWidgets.QPushButton("Close", dlg)
        row.addStretch(1)
        for b in (btn_png, btn_print, btn_close):
            row.addWidget(b)
        lay.addLayout(row)

        def _save_png() -> None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save snapshot", "draw.png", "PNG (*.png)")
            if path:
                self._print_to_png(path)

        def _print() -> None:
            try:
                from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
            except Exception:
                QMessageBox.warning(
                    self, "Print", "QtPrintSupport 不可用。")
                return
            printer = QPrinter(QPrinter.HighResolution)
            d = QPrintDialog(printer, dlg)
            if d.exec_() == QtWidgets.QDialog.Accepted:
                from PyQt5.QtGui import QPainter
                painter = QPainter(printer)
                rect = painter.viewport()
                pix = QPixmap.fromImage(img)
                scaled = pix.scaled(rect.size(), Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
                painter.drawPixmap(0, 0, scaled)
                painter.end()

        btn_png.clicked.connect(_save_png)
        btn_print.clicked.connect(_print)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec_()

    # ------------------------------------------------- File: execute

    def _find_program(self, names: list[str]) -> Optional[str]:
        prog = None
        try:
            import ps_facet2_nodes
            prog = ps_facet2_nodes.find_cradle_programs()
        except Exception:
            pass
        if prog is not None:
            for name in names:
                p = prog / name
                if p.is_file():
                    return str(p)
        for name in names:
            hit = shutil.which(name)
            if hit:
                return hit
        return None

    def _export_temp_s_files(self) -> Optional[str]:
        if self.model is None or self.props is None:
            return None
        tmp = tempfile.mkdtemp(prefix="cab_solve_")
        base = os.path.join(tmp, self.model.project_name or "model")
        with open(base + ".s", "w", encoding="utf-8-sig",
                  newline="") as fh:
            fh.write(build_sdat(self.model, self.props))
        with open(base + ".xemt", "w", encoding="utf-8-sig",
                  newline="") as fh:
            fh.write(xemt_export.build_emt(self.model, self.props))
        return base + ".s"

    def _launch_program(self, exe: Optional[str], args: list[str]) -> bool:
        if not exe:
            self.log("Program not found (Cradle CFD 2025.2).", "WARN")
            return False
        try:
            subprocess.Popen([exe] + args)
            self.log(f"Launched {os.path.basename(exe)}")
            return True
        except Exception as exc:
            self.log(f"Launch failed: {exc}", "ERROR")
            return False

    def _execute_solver(self) -> None:
        """File -> Execute Solver: confirm, export temp S files, launch."""
        if self.model is None or self.props is None:
            self.log("No project open.", "WARN")
            return
        ret = QMessageBox.question(
            self, "Execute Solver",
            "Solver 将读取当前工程的 S 文件并启动。继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        sfile = self._export_temp_s_files()
        if sfile is None:
            self.log("Execute Solver: export failed.", "ERROR")
            return
        exe = self._find_program(
            ["stsol_Dx64net.exe", "stsol_Sx64net.exe", "stsol.exe"])
        if self._launch_program(exe, [sfile]):
            self.log(f"Execute Solver: {sfile}")
        else:
            QMessageBox.warning(
                self, "Execute Solver",
                "未找到 stsol 求解器；S 文件已导出到:\n" + sfile)

    def _execute_post(self) -> None:
        """File -> Execute Post: confirm and launch Postprocessor."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        ret = QMessageBox.question(
            self, "Execute Post",
            "启动 Postprocessor？", QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        exe = self._find_program(
            ["scPOST_Dx64net.exe", "scPOST_Sx64net.exe", "scPOST.exe"])
        args = [self.current_path] if self.current_path else []
        if not self._launch_program(exe, args):
            QMessageBox.warning(self, "Execute Post", "未找到 scPOST 后处理。")

    def _wizard_initial(self) -> None:
        """Wizard -> Initial Setting: the STpre Initial Wizard (M6)."""
        if self.model is None or self.props is None:
            self.log("No project open.", "WARN")
            return
        import cab_wizards
        snap = self._snapshot()
        dlg = cab_wizards.InitialWizard(
            self.model, self.props, self._cad_meshes,
            archive=self.archive, parent=self)
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            # Wizard may have imported CAD — show Shading by default
            self._drawing_mode = "Shading"
            self._wireframe = False
            self._translucent = False
            self.control.set_drawing_mode("Shading")
            if self.tb_display.currentText() != "Shading":
                self.tb_display.blockSignals(True)
                idx = self.tb_display.findText("Shading")
                if idx >= 0:
                    self.tb_display.setCurrentIndex(idx)
                self.tb_display.blockSignals(False)
            self._rebuild_scene(fit=True)
            self.log("Initial Setting finished; save the cab to persist.")

    def _domain_dialog(self) -> None:
        """Edit -> Reset Computational Domain (M2)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        snap = self._snapshot()
        dlg = _DomainDialog(
            self.model, self.props, self._cad_meshes, self)
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.log("Computational domain updated; save the cab to persist.")

    def _wizard_condition(self) -> None:
        """Wizard -> Condition Setting: the STpre Condition Wizard (M6)."""
        if self.model is None or self.props is None:
            self.log("No project open.", "WARN")
            return
        import cab_wizards
        snap = self._snapshot()
        dlg = cab_wizards.ConditionWizard(self.model, self.props, self)
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            self._rebuild_scene()
            self.log("Condition Setting finished; save the cab to persist.")

    def _part_dialog(self, name: str) -> None:
        """Double-click a part -> STpre-style part edit dialog (M5)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        snap = self._snapshot()
        dlg = _PartDialog(self.model, self.props, name, self)
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            self.log(f"Part '{dlg.part_name}' updated; "
                     f"save the cab to persist.")

    def _append_primitive_tess(self) -> None:
        """Regenerate primitive (cube/cylinder/sphere/panel) previews."""
        try:
            import cab_parts
            prim = cab_parts.primitives_from_model(self.model)
        except Exception:
            prim = []
        if prim:
            self._cad_meshes = list(self._cad_meshes or []) + prim
        try:
            import cab_sketch
            sket = cab_sketch.sketch_parts_from_model(self.model)
        except Exception:
            sket = []
        if sket:
            self._cad_meshes = list(self._cad_meshes or []) + sket

    def _create_part_dialog(self, kind: str) -> None:
        """Part(P) → create primitive (STpre Part menu)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        try:
            import cab_parts
        except Exception:
            self.log("cab_parts unavailable.", "ERROR")
            return
        if kind not in cab_parts.PRIMITIVE_KINDS:
            self._nyi(f"Part — {kind}")
            return
        if kind == "sketch":
            self._sketch_part_dialog()
            return
        dlg = cab_parts.CreatePartDialog(
            self.model, self.props, initial_kind=kind, parent=self,
            single_kind=True)

        def _preview(spec):
            try:
                tess = cab_parts.tess_for_spec(spec["kind"], spec["params"])
                tess.name = f"__preview__{spec['kind']}"
                meshes = [m for m in (self._cad_meshes or [])
                          if not getattr(m, "name", "").startswith(
                              "__preview__")]
                self._cad_meshes = meshes + [tess]
                self._rebuild_scene()
                self.log(f"Preview {spec['kind']} '{spec.get('name', '')}'")
            except Exception as exc:
                self.log(f"Preview failed: {exc}", "WARN")

        if hasattr(dlg, "preview_requested") and dlg.preview_requested:
            dlg.preview_requested.connect(_preview)
        if not dlg.exec_():
            # drop transient preview meshes
            self._cad_meshes = [
                m for m in (self._cad_meshes or [])
                if not getattr(m, "name", "").startswith("__preview__")]
            if self._enable_3d:
                self._rebuild_scene()
            return
        spec = dlg.spec()
        if not spec["name"]:
            self.log("Create Part: a part name is required.", "WARN")
            return
        if self.model.find_part(spec["name"]) is not None:
            QMessageBox.warning(
                self, "Create Part", f"Part '{spec['name']}' already exists.")
            return
        snap = self._snapshot()
        color = spec.get("color", "25,117,255,255")
        if not cab_parts.register_primitive(
                self.model, name=spec["name"], kind=spec["kind"],
                params=spec["params"], material=spec["material"],
                attribute=spec["attribute"], color=color,
                layer=spec.get("layer", "1")):
            self.log("Create Part: registration failed.", "ERROR")
            return
        tess = cab_parts.tess_for_spec(spec["kind"], spec["params"])
        tess.name = spec["name"]
        self._cad_meshes = [
            m for m in (self._cad_meshes or [])
            if not getattr(m, "name", "").startswith("__preview__")] + [tess]
        self._push_undo(snap)
        self._mark_dirty()
        self._update_title()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self._rebuild_scene()
        self.log(
            f"Created {spec['kind']} part '{spec['name']}' "
            f"(attribute={spec['attribute']}, material={spec['material']})")

    def _sketch_part_dialog(self) -> None:
        """Part -> Sketch Part: full sketch-plane based creation (M8)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        try:
            import cab_sketch
        except Exception:
            self.log("cab_sketch unavailable.", "ERROR")
            return
        dlg = cab_sketch.SketchPartDialog(
            self.model, self.props, parent=self)
        if not dlg.exec_():
            return
        spec = dlg.spec()
        name = spec["name"]
        if not name:
            self.log("Sketch Part: a part name is required.", "WARN")
            return
        if self.model.find_part(name) is not None:
            QMessageBox.warning(
                self, "Sketch Part", f"Part '{name}' already exists.")
            return
        poly = spec["profile"].polygon()
        if spec["profile"].geometry_type == "point_sequence":
            need = 3 if spec["profile"].close else 2
            if len(poly) < need:
                QMessageBox.warning(
                    self, "Sketch Part",
                    "Point sequence needs >= 3 vertices (closed) "
                    "or >= 2 (open).")
                return
        snap = self._snapshot()
        plane = cab_sketch.plane_from_xml(self.model)
        ok = cab_sketch.register_sketch_part(
            self.model, name=name, plane=plane,
            profile=spec["profile"], model_type=spec["model_type"],
            thickness_mm=spec["thickness"], material=spec["material"],
            attribute=spec["attribute"])
        if not ok:
            self.log("Sketch Part: registration failed.", "ERROR")
            return
        tess = cab_sketch.sketch_tess(
            plane, spec["profile"], spec["model_type"], spec["thickness"])
        tess.name = name
        self._cad_meshes = list(self._cad_meshes or []) + [tess]
        self._push_undo(snap)
        self._mark_dirty()
        self._update_title()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self._rebuild_scene()
        self.log(
            f"Created sketch part '{name}' "
            f"({spec['model_type']}, {spec['profile'].geometry_type}, "
            f"thickness={spec['thickness']} mm)")

    def _mesh_info(self) -> None:
        if self.model is None:
            return
        self._on_item_selected("mesh_block", "RootBlock")
        axes = self.model.mesh_axes()
        self.log(
            f"Mesh block: "
            f"{len(axes.get('x', []))}×{len(axes.get('y', []))}×"
            f"{len(axes.get('z', []))} points")

    def _mesh_block_dialog(self) -> None:
        """Layout → RootBlock: STpre ``Mesh:block`` (not Mesh:Set division)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        snap = self._snapshot()
        dlg = _MeshBlockDialog(self.model, self)
        if dlg.exec_():
            self._push_undo(snap)
            self._root_block_visible = True
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            self._rebuild_scene(fit=False)
            self._mark_dirty()
            self._update_title()
            self.log("RootBlock updated; save the cab to persist.")

    # ------------------------------------------------- STpre API bridge

    def _stpre_api_enabled(self) -> bool:
        try:
            from cab_options import get_setting
            return str(get_setting("use_stpre_api", "False")).lower() \
                == "true"
        except Exception:
            return False

    def _toggle_stpre_api(self, on: bool) -> None:
        from cab_options import set_setting
        set_setting("use_stpre_api", "True" if on else "False")
        if not on:
            self._close_stpre_session()
        self.log(f"STpre API gridding/meshing: {'ON' if on else 'OFF'}")

    def _close_stpre_session(self) -> None:
        """Quit the shared STpre process (option off, failure, app exit)."""
        session = getattr(self, "_stpre_session", None)
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
            self._stpre_session = None

    def closeEvent(self, event) -> None:
        self._close_stpre_session()
        super().closeEvent(event)

    def _run_stpre_api(self, action: str,
                       params: Optional[list] = None,
                       method: str = "detail") -> str:
        """Run gridding/meshing in external STpre; returns stpre|native.

        File-relay: the current project is saved to a temp CAB, STpre
        (COM automation) executes the mesh commands and saves another CAB,
        and the mesh sections are merged back into the in-memory model.

        The STpre process is kept alive in ``self._stpre_session``:
        [Gridding] starts it once, then [Meshing] re-opens a *new* relay
        CAB in the same process and only runs ExecuteElement, which avoids
        the 5-7 s COM cold-start (plus second OpenCabFile) per click.
        """
        if not self._stpre_api_enabled() or self.model is None \
                or self.archive is None:
            return "native"
        try:
            import cab_stpre_api
            if not cab_stpre_api.api_available():
                self.log(
                    "STpre COM ProgID not found; using native gridding.",
                    "WARN")
                return "native"
            import os
            import tempfile
            from cab_container import CabArchive
            from cabxml import StpreModel, parse_stpre
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QApplication

            # Meshing reuses the mesh_block that [Gridding] (STpre or
            # native) already wrote into the in-memory model, so the relay
            # carries it and STpre only has to execute element division.
            axes = self.model.mesh_axes()
            has_mesh = bool(axes) and all(
                len(axes.get(a, [])) >= 2 for a in "xyz")
            keep_mesh = action != "grid" and has_mesh
            tmp = tempfile.mkdtemp(prefix="cab_stpre_")
            src = os.path.join(tmp, "in.cab")
            dst = os.path.join(tmp, "out.cab")
            if not cab_stpre_api.build_relay_cab(
                    self.model, self.archive, src, keep_mesh=keep_mesh):
                self.log("STpre API relay build failed; using native.",
                         "WARN")
                return "native"
            if params is None:
                params = cab_stpre_api.build_grid_params(self.model)
            fresh_session = self._stpre_session is None
            session = self._stpre_session
            if session is None:
                session = cab_stpre_api.STpreSession()
                self._stpre_session = session
            if not session.ensure_open(src):
                detail = getattr(cab_stpre_api, "last_error", None)
                self.log(
                    "STpre API open failed"
                    + (f" ({detail})" if detail else "")
                    + "; falling back to native.", "WARN")
                self._close_stpre_session()
                return "native"
            # Gridding: SetGridParam + ExecuteGrid.  Meshing with an
            # existing mesh_block: ExecuteElement only.  Meshing without a
            # mesh_block (user skipped Gridding): full grid + element.
            run_grid = action == "grid" or not keep_mesh
            run_element = action != "grid"
            self.log(
                f"STpre API: {'gridding' if run_grid else 'skipping grid'} "
                f"/ {'element division' if run_element else 'no elements'} "
                f"in shared session "
                f"({'started' if fresh_session else 'reused'})...")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            ok = True
            try:
                if run_grid and not session.grid(params, method):
                    ok = False
                elif run_element and not session.element():
                    ok = False
                elif not session.save(dst):
                    ok = False
            finally:
                QApplication.restoreOverrideCursor()
            if not ok or not os.path.isfile(dst):
                detail = getattr(cab_stpre_api, "last_error", None)
                self.log(
                    "STpre API gridding/meshing failed"
                    + (f" ({detail})" if detail else "")
                    + "; falling back to native.", "WARN")
                self._close_stpre_session()
                return "native"
            arch = CabArchive.parse(open(dst, "rb").read())
            arch.fill_member_data()
            members = {m.name: m.data for m in arch.members}
            xml_name = next(n for n in members if n.endswith(".xml")
                            and not n.startswith("_"))
            out_model = StpreModel(parse_stpre(members[xml_name]))
            merged = cab_stpre_api.merge_mesh_result(self.model, out_model)
            self.tree_view.populate(
                self.model, self.archive.members)
            self.control.load_sketch(self.model)
            self._rebuild_scene()
            self._mark_dirty()
            self._update_title()
            self.log(f"STpre API done: merged {', '.join(merged)}")
            return "stpre"
        except Exception as exc:
            self.log(f"STpre API failed: {exc}; using native.", "WARN")
            self._close_stpre_session()
            return "native"

    def _gridding_dialog(self) -> None:
        """Mesh -> Gridding (M3) — ``Mesh:Set division``."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        snap = self._snapshot()
        dlg = _GriddingDialog(
            self.model, self._cad_meshes, self)
        if self._stpre_api_enabled():
            dlg.stpre_callback = self._stpre_grid_from_dialog
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.log("Grid saved; save the cab to persist.")

    def _stpre_grid_from_dialog(self, spec, edge_contact: bool) -> bool:
        """Run STpre API gridding with the dialog's actual settings."""
        try:
            import cab_stpre_api
            params = cab_stpre_api.build_params_from_gridspec(
                spec, edge_contact=1 if edge_contact else 0)
            method = dict((p[0], p[1]) for p in params)[
                "division_method"]
            return self._run_stpre_api("grid", params=params,
                                       method=method) == "stpre"
        except Exception as exc:
            self.log(f"STpre API gridding failed: {exc}; native.", "WARN")
            return False

    def _meshing_dialog(self) -> None:
        """Mesh -> Meshing (M4): generate element occupancy from CAD."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        if self._run_stpre_api("mesh") == "stpre":
            return
        axes = self.model.mesh_axes()
        if not axes or any(len(v) < 2 for v in axes.values()):
            QMessageBox.warning(
                self, "Meshing", "No mesh_block found. Run Mesh -> Gridding "
                                 "first.")
            return
        meshes = self._cad_meshes or []
        if not meshes:
            QMessageBox.warning(
                self, "Meshing", "No tessellated CAD parts available.")
            return
        try:
            import cab_mesh
            snap = self._snapshot()
            transforms = {p.name: p.transform for p in self.model.parts()}

            def tick(done: int, total: int) -> None:
                self.statusBar().showMessage(
                    f"Meshing: classifying part {done}/{total} …")

            analysis_box, part_boxes = cab_mesh.classify_cells(
                axes, meshes, transforms=transforms, progress=tick)
            analysis_name = (self.model.analysis_names() or
                             ["Domain(cuboid)"])[0]
            cab_mesh.apply_elements(
                self.model, analysis_name, analysis_box, part_boxes)
            self._push_undo(snap)
            self._rebuild_scene()
            self._mark_dirty()
            self._update_title()
            total = sum(len(v) for v in part_boxes.values())
            self.log(
                f"Meshing done: {len(part_boxes)} part(s), {total} box "
                f"list(s); domain {analysis_box}. Save to persist.")
        except Exception as exc:
            QMessageBox.critical(self, "Meshing failed", str(exc))
            self.log(f"Meshing failed: {exc}", "ERROR")

    def _check_sfile(self) -> None:
        if self.model is None or self.props is None:
            return
        text = build_sdat(self.model, self.props)
        lines = text.splitlines()
        self.log(f"S-File check: {len(lines)} lines, starts with "
                 f"{lines[0][:40]!r}" if lines else "empty")

    def _interference_dialog(self) -> None:
        """Mesh -> Checking Parts Interferences (M6)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        snap = self._snapshot()
        dlg = cab_dialogs.InterferenceDialog(self.model, self)
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.log("Interference check finished; save to persist.")

    def _edit_mesh_dialog(self) -> None:
        """Mesh -> Editing Mesh (M6): toggle part/fluid cells."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        axes = self.model.mesh_axes()
        if not axes or any(len(v) < 2 for v in axes.values()):
            QMessageBox.warning(
                self, "Editing Mesh", "No mesh_block found. Run Mesh -> "
                                      "Gridding and Mesh -> Meshing first.")
            return
        snap = self._snapshot()
        dlg = cab_dialogs.EditMeshDialog(self.model, self)
        if dlg.exec_():
            self._push_undo(snap)
            self._mark_dirty()
            self._update_title()
            self.tree_view.populate(
                self.model, self.archive.members if self.archive else [])
            self.log("Editing Mesh finished; save the cab to persist.")

    def _section_dialog(self) -> None:
        """Mesh -> Showing Element Cross-Section (M6)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        axes = self.model.mesh_axes()
        if not axes or any(len(v) < 2 for v in axes.values()):
            QMessageBox.warning(
                self, "Showing Element Cross-Section",
                "No mesh_block found. Run Mesh -> Gridding first.")
            return
        dlg = cab_dialogs.SectionDialog(self.model, self)
        dlg.exec_()
        self._clear_section()

    def _check_sfile_dialog(self) -> None:
        """Mesh -> Checking S-File (M6)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        dlg = cab_dialogs.SFileCheckDialog(self.model, self)
        dlg.exec_()

    def _confirm_interferences(self, names: list[str]) -> None:
        """Highlight the interfering parts in the Draw window."""
        if not names:
            return
        for name in names:
            self._hidden_parts.discard(name)
        self.log("Interference confirm: showing " + ", ".join(names))
        if not self._enable_3d or self.renderer is None:
            return
        part_on = self.control.layer_on("part")
        for actor, pname in self.actors:
            actor.SetVisibility(
                1 if (part_on and pname not in self._hidden_parts) else 0)
        self.renderer.GetRenderWindow().Render()

    def _set_part_visible(self, name: str, visible: bool) -> None:
        """Toggle one part's 3D visibility (Checking S-File checkbox)."""
        if visible:
            self._hidden_parts.discard(name)
        else:
            self._hidden_parts.add(name)
        if not self._enable_3d or self.renderer is None:
            return
        part_on = self.control.layer_on("part")
        for actor, pname in self.actors:
            if pname == name:
                actor.SetVisibility(
                    1 if (visible and part_on) else 0)
        self.renderer.GetRenderWindow().Render()

    def _show_section(self, pd, colors) -> None:
        """Draw the element cross-section slice (live slider refresh)."""
        if not self._enable_3d or self.renderer is None or pd is None:
            return
        self._clear_section()
        actor = cab_vtk.section_actor(pd, colors)
        self.renderer.AddActor(actor)
        self._layer_actors.setdefault("section", []).append(actor)
        self.renderer.GetRenderWindow().Render()

    def _clear_section(self) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        for actor in self._layer_actors.get("section", []):
            self.renderer.RemoveActor(actor)
        self._layer_actors["section"] = []
        if self.renderer.GetRenderWindow() is not None:
            self.renderer.GetRenderWindow().Render()

    def _open_manual(self) -> None:
        if os.path.isfile(ST_MANUAL):
            os.startfile(ST_MANUAL)  # noqa: S606
            self.log(f"Opened manual: {ST_MANUAL}")
        else:
            self.log(f"Manual not found: {ST_MANUAL}", "ERROR")

    @staticmethod
    def _git_rev() -> str:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5)
            return out.stdout.strip() or ""
        except Exception:
            return ""

    def _parasolid_version(self) -> str:
        try:
            import ctypes as C
            import ps_facet2_nodes as m
            sess = m._get_session()
            pk = sess.pk
            fn = getattr(pk, "PK_SESSION_ask_kernel_version", None)
            if fn is None:
                return ""
            fn.restype = C.c_int
            fn.argtypes = [C.POINTER(C.c_int), C.POINTER(C.c_int),
                           C.POINTER(C.c_int)]
            a, b, c = C.c_int(), C.c_int(), C.c_int()
            if fn(C.byref(a), C.byref(b), C.byref(c)) == 0:
                return f"{a.value}.{b.value}.{c.value}"
        except Exception:
            pass
        return ""

    def _version_dialog(self) -> None:
        """Help -> Version."""
        import platform
        lines = [f"cabdecoding  git {self._git_rev() or 'unknown'}"]
        lines.append(f"Python {platform.python_version()}")
        try:
            from PyQt5.QtCore import QT_VERSION_STR
            lines.append(f"Qt {QT_VERSION_STR}")
        except Exception:
            pass
        try:
            lines.append(f"VTK {vtk.VTK_VERSION}")
        except Exception:
            pass
        ps = self._parasolid_version()
        if ps:
            lines.append(f"Parasolid kernel {ps}")
        QMessageBox.information(self, "Version", "\n".join(lines))

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
    _install_startup_message_filter()
    path = None
    args = argv if argv is not None else sys.argv
    if len(args) > 1 and os.path.isfile(args[1]):
        path = args[1]
    win = CabViewer(path)
    win.show()
    _clamp_to_visible_screen(win)
    if win.vtk_widget is not None:
        win._ensure_interactor()
    return app.exec_()


def _install_startup_message_filter() -> None:
    """Suppress two known-benign Qt platform warnings at startup.

    * ``qt.qpa.fonts: Unable to open default EUDC font`` - the system is
      missing EUDC.TTE; cosmetic only.
    * ``QWindowsWindow::setGeometry: Unable to set geometry ...`` - a
      top-level window (sometimes from a foreign Qt process sharing the
      console) is clamped to a visible display on multi-monitor layouts.
    """
    try:
        from PyQt5.QtCore import qInstallMessageHandler, qt_message_handler
    except Exception:  # pragma: no cover
        return

    def handler(mode, context, message) -> None:
        msg = str(message)
        if ("EUDC" in msg and "font" in msg.lower()) or (
                "QWindowsWindow::setGeometry" in msg
                and "Unable to set geometry" in msg):
            return
        qt_message_handler(mode, context, message)

    qInstallMessageHandler(handler)


def _clamp_to_visible_screen(win) -> None:
    """Move the main window onto a visible screen when the assigned
    position falls outside every display (multi-monitor layouts)."""
    try:
        from PyQt5.QtGui import QGuiApplication
        frame = win.frameGeometry()
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(frame):
                return
        geo = QGuiApplication.primaryScreen().availableGeometry()
        win.move(geo.center().x() - win.width() // 2,
                 geo.center().y() - win.height() // 2)
    except Exception:  # pragma: no cover
        pass


if __name__ == "__main__":
    sys.exit(main())

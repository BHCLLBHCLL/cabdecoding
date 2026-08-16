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
from cab_container import (
    CabArchive, CabFolder, CabMember, restore_members, snapshot_members)
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
    from PyQt5.QtCore import QSize, Qt, QTimer
    from PyQt5.QtGui import QKeySequence
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
    from cab_solver_proc import SolverProcess  # R6 求解闭环监控
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless environments
    _HAS_GUI_DEPS = False
    QtWidgets = None
    QMainWindow = object  # type: ignore
    QKeySequence = None  # type: ignore
    SolverProcess = None  # type: ignore


ST_MANUAL = (r"C:\Program Files\Cradle\CradleCFD2025.2"
             r"\Manuals\ST\HTML\Pre_eng\index.html")

# STpre Pre_eng Keyboard / Operation_eng: Draw Window view keys
#   X → YZ from +X,  Y → XZ from +Y,  Z → XY from +Z
#   Shift+X/Y/Z → same plane from the negative axis
# Fit to DrawWindow is toolbar/menu in STpre; cabdecoding also binds F
# (draw-window focus), matching the user/op request for adaptive Fit.
_VIEW_KEY_TO_PLANE = {"x": "yz", "y": "xz", "z": "xy"}


def plane_view_camera(plane: str, *, negative: bool = False
                      ) -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """Camera (position, view_up) for an STpre orthogonal plane view."""
    sign = -1.0 if negative else 1.0
    p = (plane or "").lower()
    if p == "xy":
        return (0.0, 0.0, sign), (0.0, 1.0, 0.0)
    if p == "xz":
        return (0.0, sign, 0.0), (0.0, 0.0, 1.0)
    # yz (default / X key)
    return (sign, 0.0, 0.0), (0.0, 0.0, 1.0)


def view_key_action(keysym: str, *, shift: bool = False
                    ) -> Optional[tuple]:
    """Map a Draw Window key to ('plane', name, negative) or ('fit',)."""
    sym = (keysym or "").lower()
    if sym == "f" and not shift:
        return ("fit",)
    plane = _VIEW_KEY_TO_PLANE.get(sym)
    if plane is not None:
        return ("plane", plane, bool(shift))
    return None


def aspect_ratio_color(ratio: float) -> tuple[float, float, float]:
    """Occupancy aspect-ratio colormap: green <2, yellow 2..5, red >5."""
    if ratio <= 2.0:
        return (0.15, 0.7, 0.3)
    if ratio <= 5.0:
        return (0.95, 0.75, 0.15)
    return (0.9, 0.2, 0.2)


def ray_aabb_face(cam_pos, ray_dir, lo, hi) -> Optional[str]:
    """Nearest AABB face hit by a ray (returns Xmin…Zmax or None)."""
    origin = np.asarray(cam_pos, dtype=float)
    rd = np.asarray(ray_dir, dtype=float)
    n = np.linalg.norm(rd)
    if n < 1e-12:
        return None
    rd = rd / n
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    hits: list[tuple[float, str]] = []
    for axis_i, (lo_name, hi_name) in enumerate(
            (("Xmin", "Xmax"), ("Ymin", "Ymax"), ("Zmin", "Zmax"))):
        if abs(rd[axis_i]) < 1e-12:
            continue
        for plane, fname in ((lo[axis_i], lo_name), (hi[axis_i], hi_name)):
            t = (plane - origin[axis_i]) / rd[axis_i]
            if t <= 0:
                continue
            hit = origin + rd * t
            others = [j for j in range(3) if j != axis_i]
            if all(lo[j] - 1e-9 <= hit[j] <= hi[j] + 1e-9
                   for j in others):
                hits.append((t, fname))
    if not hits:
        return None
    hits.sort(key=lambda h: h[0])
    return hits[0][1]


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
        self._startup_view_tries = 0
        # Reusable STpre COM session: Gridding/Meshing share one STpre
        # process instead of cold-starting COM + OpenCabFile per click.
        self._stpre_session = None
        # R6 求解闭环监控: 当前/最近一次求解器进程 (同一时刻仅允许一个)
        self._solver_proc = None
        self._paneling_mode = False
        self._paneling_faces: list = []
        self._act_paneling_esc = None
        self._clip_planes: list = []
        self._point_part_names: set[str] = set()
        self._hide_virtual_parts = False
        self._material_filter: Optional[str] = None

        self._build_ui()
        self._apply_style()
        self._apply_stored_options()
        # STpre shows Initial Wizard on cold start / File→New (not when a
        # .cab path is passed on the command line).
        self._offer_initial_wizard = False
        self._selected_kind: str | None = None
        self._selected_name = None
        self._selected_items: list[tuple] = []  # [(kind, name), ...]
        if path:
            self.load(path)
        else:
            self._new_project(silent=True)
            self._offer_initial_wizard = True

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
        self.tree_view.items_selected.connect(self._on_items_selected)
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
        self.control.lib_tree.itemDoubleClicked.connect(
            self._on_lib_activated)
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
            self._install_draw_view_shortcuts()
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
        add(m, "Batch Execution...", self._batch_execution)
        add(m, "Execute Post", self._execute_post)
        m.addSeparator()
        self._recent_menu = m.addMenu("Recent Files")
        add(m, "Exit", self.close, "Alt+F4")

        m = mb.addMenu("Edit(&E)")
        # Order / labels aligned with STpre Pre_eng toc (Edit menu).
        add(m, "Undo", self._undo, "Ctrl+Z")
        add(m, "Redo", self._redo, "Ctrl+Y")
        m.addSeparator()
        add(m, "Group", self._group_dialog)
        add(m, "Deletion of Parts", self._delete_parts_dialog)
        add(m, "Parts Conversion", self._parts_conversion_dialog)
        add(m, "Reconstruct of Part Facet", self._facet_accuracy_dialog)
        add(m, "Flipping Part Face", self._flipping_part_face)
        add(m, "Part Face Paneling", self._part_face_paneling)
        add(m, "Sweep Part Face", self._sweep_part_face_dialog)
        add(m, "Alignment", self._alignment_dialog)
        add(m, "Place Part", self._place_part_dialog)
        add(m, "Mirror Copy Parts", self._mirror_copy_dialog)
        add(m, "Connected Region", self._connected_region_dialog)
        add(m, "Boolean Operation", self._boolean_operation_dialog)
        add(m, "Shape change by Boolean operation",
            self._shape_change_boolean_dialog)
        add(m, "Cutting", self._cutting_dialog)
        add(m, "Edit Solid", self._edit_solid_dialog)
        add(m, "Part Simplification", self._part_simplification_dialog)
        add(m, "Shape Simplification", self._shape_simplification_dialog)
        add(m, "Convert Facets to Solid", self._facets_to_solid_dialog)
        add(m, "FEM Conversion", self._fem_conversion_dialog)
        add(m, "Wrapping", self._wrapping_dialog)
        add(m, "Reset Computational Domain", self._reset_domain_dialog)
        add(m, "Edit Wiring on Board", self._edit_wiring_dialog)
        add(m, "Placement of Image", self._placement_of_image_dialog)

        m = mb.addMenu("View(&V)")
        # Ctrl+F: window-wide. Bare F is Draw-Window-only (see
        # _install_draw_view_shortcuts); STpre docs list X/Y/Z there.
        self._act_fit = add(m, "Fit to DrawWindow", self._fit_view, "Ctrl+F")
        add(m, "Reset DrawWindow", self._reset_view)
        m.addSeparator()
        # STpre [View] - [(Setting)] / [(Dialog)] (Pre_eng)
        m_set = m.addMenu("(Setting)")
        add(m_set, "Display All", self._view_display_all)
        add(m_set, "Clipping Display…", self._view_clipping_dialog)
        add(m_set, "Hide Selected Part", self._view_hide_selected)
        add(m_set, "Display the distribution of thermal conditions…",
            self._view_thermal_condition_display)
        self._act_virtual_parts = QAction("Display Virtual Part", self)
        self._act_virtual_parts.setCheckable(True)
        self._act_virtual_parts.setChecked(True)
        self._act_virtual_parts.triggered.connect(self._view_toggle_virtual)
        m_set.addAction(self._act_virtual_parts)
        add(m_set, "Display parts by materials…",
            self._view_parts_by_material)
        m_dlg = m.addMenu("(Dialog)")
        add(m_dlg, "List of Part…", self._view_list_of_part)
        add(m_dlg, "Editing Part Face…", self._view_editing_part_face)
        add(m_dlg, "Editing Contact Thermal Resistance…",
            self._view_editing_contact_tr)
        m.addSeparator()
        add(m, "3DfindIT…", self._open_3dfindit)
        m.addSeparator()
        # Shortcuts X/Y/Z (and Shift+*) installed on the Draw Window widget
        self._act_xy = add(m, "XY Plane", lambda: self._set_plane("xy"))
        self._act_xz = add(m, "XZ Plane", lambda: self._set_plane("xz"))
        self._act_yz = add(m, "YZ Plane", lambda: self._set_plane("yz"))
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
        m.addSeparator()
        add(m, "Distance…", self._option_distance_dialog)
        add(m, "Reference…", self._option_reference_dialog)
        add(m, "Cut Cell…", self._option_cutcell_dialog)
        add(m, "Selection Mode…", self._option_selection_mode)
        add(m, "Viewer Mode…", self._option_viewer_mode)
        add(m, "Thermal Characteristics of Surface…",
            self._option_thermal_surface)
        add(m, "Parametric Study…", self._option_parametric)
        m.addSeparator()
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
        act(self.tb_edit, "XY", "plane_xy",
            "XY Plane (Z) — top view from +Z; Shift+Z from −Z",
            lambda: self._set_plane("xy"))
        act(self.tb_edit, "XZ", "plane_xz",
            "XZ Plane (Y) — front view from +Y; Shift+Y from −Y",
            lambda: self._set_plane("xz"))
        act(self.tb_edit, "YZ", "plane_yz",
            "YZ Plane (X) — side view from +X; Shift+X from −X",
            lambda: self._set_plane("yz"))
        act(self.tb_edit, "Fit", "fit",
            "Fit to DrawWindow (F / Ctrl+F)", self._fit_view)
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
        # Keep in sync with cab_parts.PART_MENU_ITEMS (STpre Part menu)
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
                ("Enclosure", "enclosure", "cube"),
                ("Plate Fin", "plate_fin", "panel"),
                ("Pin Fin", "pin_fin", "panel"),
                ("Peltier", "peltier", "part"),
                ("Two-Resistor", "two_resistor", "part"),
                ("AC Unit", "ac_unit", "part"),
                ("Diffuser", "diffuser", "part"),
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

    def _option_distance_dialog(self) -> None:
        # M25/L10 Option -> Distance: 2-point distance + angle + chain +
        # part-to-part min distance (R13 measurement depth).
        from PyQt5.QtWidgets import (
            QDialog, QFormLayout, QDoubleSpinBox, QLabel, QPushButton,
            QHBoxLayout, QVBoxLayout, QComboBox, QListWidget,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle('Distance / Measurement')
        dlg.setModal(False)
        lay = QVBoxLayout(dlg)
        mode = QComboBox(dlg)
        mode.addItems(['Distance (2 points)', 'Angle (3 points)',
                       'Distance chain (N points)', 'Parts min distance'])
        lay.addWidget(mode)
        form = QFormLayout()
        spins = []
        for lab in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'):
            sp = QDoubleSpinBox(dlg)
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(3)
            form.addRow(lab + ' (mm)', sp)
            spins.append(sp)
        dlg.pick_spins = spins
        p3form = QFormLayout()
        spins3 = []
        for lab in ('X3', 'Y3', 'Z3'):
            sp = QDoubleSpinBox(dlg)
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(3)
            p3form.addRow(lab + ' (mm)', sp)
            spins3.append(sp)
        dlg.pick_spins3 = spins3
        part_a = QComboBox(dlg)
        part_b = QComboBox(dlg)
        part_names = [p.name for p in (self.model.parts()
                                        if self.model else [])]
        part_a.addItems(part_names)
        part_b.addItems(part_names)
        partform = QFormLayout()
        partform.addRow('Part A', part_a)
        partform.addRow('Part B', part_b)
        chain_list = QListWidget(dlg)
        result = QLabel('Distance = —', dlg)
        lay.addLayout(form)
        lay.addLayout(p3form)
        lay.addLayout(partform)
        lay.addWidget(chain_list)
        lay.addWidget(result)
        row = QHBoxLayout()
        pick1 = QPushButton('Pick P1', dlg)
        pick2 = QPushButton('Pick P2', dlg)
        pick3 = QPushButton('Pick P3', dlg)
        addpt = QPushButton('Add point', dlg)
        clear = QPushButton('Clear', dlg)
        calc = QPushButton('Calculate', dlg)
        close = QPushButton('Close', dlg)
        for b in (pick1, pick2, pick3, addpt, clear):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(calc)
        row.addWidget(close)
        lay.addLayout(row)
        hint = QLabel('Select Target of selection = Vertices, then click ',
                      'Pick P1 and pick a vertex in the Draw Window.', dlg)
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #555;')
        lay.addWidget(hint)
        dlg.pick_hint = hint
        dlg.chain_points = []

        def _set_mode(m: int) -> None:
            # 0 distance / 1 angle / 2 chain / 3 parts
            for w in spins3:
                w.setVisible(m == 1)
            part_a.setVisible(m == 3)
            part_b.setVisible(m == 3)
            chain_list.setVisible(m == 2)
            addpt.setVisible(m == 2)
            clear.setVisible(m == 2)
            pick3.setVisible(m == 1)
            pick2.setVisible(m in (0, 1))
        
        mode.currentIndexChanged.connect(_set_mode)
        _set_mode(0)

        def _cur_point(idx: int) -> np.ndarray:
            if idx == 2:
                return np.array([w.value() for w in spins3])
            return np.array([spins[i].value() for i in range(idx * 3,
                                                        idx * 3 + 3)])

        def _calc() -> None:
            m = mode.currentIndex()
            if m == 0:
                p1, p2 = _cur_point(0), _cur_point(1)
                d = float(np.linalg.norm(p2 - p1))
                result.setText(f'Distance = {d:.6g} mm')
                self.log(f'Distance: {d:.6g} mm')
            elif m == 1:
                p1, p2, p3 = _cur_point(0), _cur_point(1), _cur_point(2)
                v1, v2 = p1 - p2, p3 - p2
                n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if n1 < 1e-12 or n2 < 1e-12:
                    result.setText('Angle = — (degenerate)')
                    return
                ang = float(np.degrees(np.arccos(
                    np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))))
                result.setText(f'Angle at P2 = {ang:.6g} deg')
                self.log(f'Angle: {ang:.6g} deg')
            elif m == 2:
                pts = [np.array(p) for p in dlg.chain_points]
                if len(pts) < 2:
                    result.setText('Chain needs >= 2 points')
                    return
                segs = [float(np.linalg.norm(pts[i] - pts[i - 1]))
                        for i in range(1, len(pts))]
                total = sum(segs)
                chain_list.clear()
                for i, s in enumerate(segs, 1):
                    chain_list.addItem(f'{i}: {s:.6g} mm')
                result.setText(
                    f'Chain = {total:.6g} mm ({len(segs)} segments)')
                self.log(f'Chain distance: {total:.6g} mm')
            else:
                a, b = part_a.currentText(), part_b.currentText()
                if not a or not b:
                    result.setText('Select two parts')
                    return
                d = self._min_part_distance(a, b)
                result.setText(
                    f'Min distance = {d:.6g} mm' if d is not None
                    else 'No tessellation for the parts')
                if d is not None:
                    self.log(f'Parts min distance {a}-{b}: {d:.6g} mm')

        dlg.pick_calc = _calc
        dlg.mode = mode
        dlg.chain_add = lambda: dlg.chain_points.append(
            tuple(sp.value() for sp in spins[:3]))
        dlg.chain_clear = lambda: (dlg.chain_points.clear(),
                                   chain_list.clear())
        addpt.clicked.connect(dlg.chain_add)
        clear.clicked.connect(dlg.chain_clear)

        def _begin(slot: str) -> None:
            self._pick_dialog = dlg
            self._pick_slot = slot
            self._on_sel_target('Vertex')
            hint.setText(
                f'Pick {slot} in the Draw Window (Target = Vertices)...')


        def _close() -> None:
            self._clear_pick_dialog(dlg)
            dlg.accept()

        pick1.clicked.connect(lambda: _begin("P1"))
        pick2.clicked.connect(lambda: _begin("P2"))
        pick3.clicked.connect(lambda: _begin("P3"))
        calc.clicked.connect(_calc)
        close.clicked.connect(_close)
        dlg.finished.connect(lambda _r: self._clear_pick_dialog(dlg))
        dlg.show()

    def _min_part_distance(self, a: str, b: str):
        # Min distance (mm) between two parts' tessellation point clouds.
        from scipy.spatial import cKDTree
        pa = pb = None
        for m in (self._cad_meshes or []):
            nm = getattr(m, 'name', None)
            if nm == a and getattr(m, 'points', None) is not None \
                    and len(m.points):
                pa = np.asarray(m.points, float)
            if nm == b and getattr(m, 'points', None) is not None \
                    and len(m.points):
                pb = np.asarray(m.points, float)
        if pa is None or pb is None:
            return None
        tree = cKDTree(pb)
        d, _ = tree.query(pa, k=1)
        return float(d.min()) * 1000.0
    def _option_reference_dialog(self) -> None:
        """M25/L10 Option → Reference (origin pick + axes marker)."""
        from cab_options import get_setting, set_setting
        from PyQt5.QtWidgets import (
            QDialog, QFormLayout, QDoubleSpinBox, QCheckBox, QLabel, QVBoxLayout,
            QPushButton, QHBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Reference")
        dlg.setModal(False)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        ox = QDoubleSpinBox(dlg)
        oy = QDoubleSpinBox(dlg)
        oz = QDoubleSpinBox(dlg)
        for w, key in ((ox, "ref_ox"), (oy, "ref_oy"), (oz, "ref_oz")):
            w.setRange(-1e6, 1e6)
            w.setDecimals(3)
            w.setValue(float(get_setting(key, 0.0)))
        show = QCheckBox("Show reference axes", dlg)
        show.setChecked(str(get_setting("ref_show", "True")) == "True")
        form.addRow("Origin X (mm)", ox)
        form.addRow("Origin Y (mm)", oy)
        form.addRow("Origin Z (mm)", oz)
        form.addRow(show)
        lay.addLayout(form)
        hint = QLabel("Click 'Pick origin' then pick a vertex in the Draw "
                      "Window (Target = Vertices).", dlg)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        lay.addWidget(hint)
        row = QHBoxLayout()
        pick = QPushButton("Pick origin", dlg)
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addWidget(pick)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        dlg.pick_spins = [ox, oy, oz]
        dlg.pick_hint = hint

        def _pick_origin() -> None:
            self._pick_dialog = dlg
            self._pick_slot = "P1"
            self._on_sel_target("Vertex")
            hint.setText("Pick the reference origin in the Draw Window…")

        def _ok() -> None:
            set_setting("ref_ox", ox.value())
            set_setting("ref_oy", oy.value())
            set_setting("ref_oz", oz.value())
            set_setting("ref_show", show.isChecked())
            self.log(
                f"Reference origin=({ox.value():g},{oy.value():g},"
                f"{oz.value():g}) show={show.isChecked()}")
            dlg.accept()

        def _cancel() -> None:
            self._clear_pick_dialog(dlg)
            dlg.reject()

        pick.clicked.connect(_pick_origin)
        ok.clicked.connect(_ok)
        cancel.clicked.connect(_cancel)
        dlg.finished.connect(lambda _r: self._clear_pick_dialog(dlg))
        dlg.show()

    def _clear_pick_dialog(self, dlg) -> None:
        if self._pick_dialog is dlg:
            self._pick_dialog = None
            self._pick_slot = None

    def _feed_pick_point(self, snapped) -> bool:
        """Feed a snapped vertex into the active non-modal pick dialog."""
        dlg = self._pick_dialog
        slot = self._pick_slot
        if dlg is None or slot is None:
            return False
        spins = getattr(dlg, "pick_spins", None)
        if not spins:
            return False
        mm = np.asarray(snapped[2], dtype=float) * 1000.0
        if slot == "P3":
            spins3 = getattr(dlg, "pick_spins3", None)
            if spins3 is not None:
                for i in range(3):
                    spins3[i].setValue(float(mm[i]))
            self._pick_slot = None
            hint = getattr(dlg, "pick_hint", None)
            if hint is not None:
                hint.setText("Point picked.")
            calc = getattr(dlg, "pick_calc", None)
            if calc is not None:
                calc()
            return True
        base = 0 if slot == "P1" else 3
        for i in range(3):
            spins[base + i].setValue(float(mm[i]))
        hint = getattr(dlg, "pick_hint", None)
        if slot == "P1" and len(spins) >= 6:
            self._pick_slot = "P2"
            if hint is not None:
                hint.setText("Pick P2 in the Draw Window…")
        else:
            self._pick_slot = None
            if hint is not None:
                hint.setText("Points picked.")
            calc = getattr(dlg, "pick_calc", None)
            if calc is not None:
                calc()
        return True

    def _option_cutcell_dialog(self) -> None:
        """M27 Option → Cut Cell MVP."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QDialog, QFormLayout, QCheckBox, QDoubleSpinBox, QVBoxLayout,
            QPushButton, QHBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Cut Cell")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        en = QCheckBox("Enable cut-cell", dlg)
        en.setChecked(
            self.model.project_value("cutcell_enable", "F") == "T")
        tol = QDoubleSpinBox(dlg)
        tol.setRange(0.0, 1.0)
        tol.setDecimals(6)
        try:
            tol.setValue(float(
                self.model.project_value("cutcell_tol", "0.01")))
        except ValueError:
            tol.setValue(0.01)
        form.addRow(en)
        form.addRow("Tolerance", tol)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _ok() -> None:
            snap = self._snapshot()
            self.model.set_project_value(
                "cutcell_enable", "T" if en.isChecked() else "F")
            self.model.set_project_value(
                "cutcell_tol", f"{tol.value():g}")
            self.model.set_analysis_set_value(
                "cutcell", "1" if en.isChecked() else "0")
            self._push_undo(snap)
            self._mark_dirty()
            self.log(f"Cut Cell: enable={en.isChecked()} tol={tol.value():g}")
            dlg.accept()

        ok.clicked.connect(_ok)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _option_selection_mode(self) -> None:
        """M29 Option → Selection Mode."""
        from cab_options import get_setting, set_setting
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QRadioButton, QPushButton, QHBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Selection Mode")
        lay = QVBoxLayout(dlg)
        cur = str(get_setting("selection_mode", "Single"))
        radios = []
        for lab in ("Single", "Multi", "Rubber box"):
            rb = QRadioButton(lab, dlg)
            rb.setChecked(lab == cur)
            lay.addWidget(rb)
            radios.append(rb)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _ok() -> None:
            for rb in radios:
                if rb.isChecked():
                    set_setting("selection_mode", rb.text())
                    self.log(f"Selection Mode: {rb.text()}")
                    break
            dlg.accept()

        ok.clicked.connect(_ok)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _option_thermal_surface(self) -> None:
        """P2: Option → Thermal Characteristics of Surface (emissivity set)."""
        if not self._edit_require_model():
            return
        from cab_options import ThermalCharacteristicsDialog
        snap = self._snapshot()
        dlg = ThermalCharacteristicsDialog(self.model, self)
        if dlg.exec_() and dlg.result():
            self._edit_finish(snap, "Thermal characteristics applied.")


    def _option_parametric(self) -> None:
        """P2: Option → Parametric Study (parameter set definition)."""
        if not self._edit_require_model():
            return
        from cab_options import ParametricStudyDialog
        snap = self._snapshot()
        dlg = ParametricStudyDialog(self.model, self)
        if dlg.exec_() and dlg.result():
            self._edit_finish(snap, "Parametric study parameters applied.")


    def _option_viewer_mode(self) -> None:
        """M29 Option → Viewer Mode."""
        from cab_options import get_setting, set_setting
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QRadioButton, QPushButton, QHBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Viewer Mode")
        lay = QVBoxLayout(dlg)
        cur = str(get_setting("viewer_mode", "Edit"))
        radios = []
        for lab in ("Edit", "Viewer (read-only)"):
            rb = QRadioButton(lab, dlg)
            rb.setChecked(lab.startswith(cur) or lab == cur)
            lay.addWidget(rb)
            radios.append(rb)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _ok() -> None:
            for rb in radios:
                if rb.isChecked():
                    mode = "Edit" if rb.text().startswith("Edit") else "Viewer"
                    set_setting("viewer_mode", mode)
                    self.log(f"Viewer Mode: {mode}")
                    break
            dlg.accept()

        ok.clicked.connect(_ok)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _apply_options(self, values: dict) -> None:
        self._undo_limit = int(values.get("undo_levels", 50))
        self._log_level = str(values.get("log_level", "INFO"))
        self.message_win.set_max_blocks(
            int(values.get("message_max_blocks", 2000)))
        mode = values.get("drawing_mode")
        if mode not in ("Line", "Shading", "Translucent"):
            # Default drawing mode is Shading; any missing/legacy/corrupt
            # stored value falls back to it instead of keeping an old Line
            # preference from a previous session.
            mode = "Shading"
        self._set_drawing_mode(mode)
        lang = str(values.get("ui_language", "en"))
        import cab_i18n
        self.setWindowTitle(cab_i18n.tr("app_title", lang))
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
                "ui_language": str(get_setting("ui_language", "en")),
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
        self._load_project_part_library()
        self.control.populate_library(self.props)
        self.control.load_sketch(self.model)
        self.control.clear_property()
        self._rebuild_scene(fit=True)
        self._update_title()
        if not silent:
            self.log(
                "New project created — opening Initial Setting wizard.")
            # File → New: same as STpre, offer Initial Wizard.
            QTimer.singleShot(0, self._wizard_initial)
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
        self._load_project_part_library()
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
        out_src: list[Optional[str]] = []
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
                            # STpre display-mesh recipe (facet_kind=2 branch,
                            # bbox-diagonal tolerances) -- matches STpre
                            # SaveStlFile output exactly.
                            added = ps_facet2_nodes.tessellate_xt_stpre(
                                members[xt_name])
                            if not added:
                                added = ps_facet2_nodes.tessellate_xt(
                                    members[xt_name], adaptive=True,
                                    facet_tol=facet_tol,
                                    facet_angle_deg=facet_angle)
                            out += added
                            out_src += [xt_name] * len(added)
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
                                added = ps_tessellate.tessellate_xt(
                                    members[xt_name], facet_tol=facet_tol,
                                    facet_angle_deg=facet_angle)
                                out += added
                                out_src += [xt_name] * len(added)
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
                    out_src.append(name)
            except Exception as exc:
                self.log(f"STL member rebuild skipped: {exc}", "WARN")
        return self._remap_tess_to_parts(out, out_src) or None

    def _remap_tess_to_parts(self, out: list,
                             out_src: Optional[list] = None) -> list:
        """Attach reloaded x_t/STL tessellations to parts by file reference.

        Parasolid body SDL names can differ from the cab part name (e.g.
        boolean results), so a tessellation whose name matches no part is
        renamed to an unused part whose ``<file>`` reference points at the
        same source member.
        """
        if self.model is None or not out:
            return out or []
        from collections import defaultdict
        from cabxml import _first
        part_refs: list[tuple[str, str]] = []
        for p in self.model.parts():
            el = self.model.find_part(p.name)
            f = _first(el, "file") if el is not None else None
            ref = ""
            if f is not None and f.text:
                ref = (f.text or "").strip()
            part_refs.append((p.name, ref))
        names = {p.name for p in self.model.parts()}
        used = set()
        for t in out:
            nm = getattr(t, "name", None)
            if nm in names and nm not in used:
                used.add(nm)
        src = out_src or [None] * len(out)
        groups: dict[str, list[int]] = defaultdict(list)
        for i, t in enumerate(out):
            if getattr(t, "name", None) not in names and src[i]:
                groups[src[i]].append(i)
        for member_name, idxs in groups.items():
            candidates = [pname for pname, ref in part_refs
                          if ref == member_name and pname not in used]
            for i, pname in zip(idxs, candidates):
                out[i].name = pname
                used.add(pname)
        return out

    # ------------------------------------------------------- undo / redo

    def _snapshot(self) -> tuple:
        xml = self.model.doc.serialize() if self.model is not None else None
        prop = self.props.doc.serialize() if self.props is not None else None
        members = snapshot_members(self.archive) \
            if self.archive is not None else None
        return (xml, prop, members)

    def _restore_snapshot(self, snap: tuple) -> None:
        xml, prop = snap[0], snap[1]
        snap_members = snap[2] if len(snap) > 2 else None
        if xml is not None:
            self.model = StpreModel(parse_stpre(xml))
        if prop is not None:
            self.props = PropertyModel(parse_property(prop))
        if snap_members is not None and self.archive is not None:
            # A5: restore the archive members too, so geometry and XML stay
            # consistent after undo/redo of PK edits (boolean/cut add members).
            restore_members(self.archive, snap_members)
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

    # ----------------------------------------------------------- Edit menu

    def _edit_require_model(self) -> bool:
        if self.model is None:
            self.log("No project open.", "WARN")
            return False
        return True

    def _edit_finish(self, snap, message: str, *,
                     purge_meshes: list[str] | None = None) -> None:
        """Common post-Edit refresh after a successful dialog apply."""
        if purge_meshes:
            keep = set(purge_meshes)
            self._cad_meshes = [
                m for m in (self._cad_meshes or [])
                if getattr(m, "name", None) not in keep]
        self._push_undo(snap)
        self._mark_dirty()
        self._update_title()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self._rebuild_scene()
        self.log(message)

    def _delete_parts_dialog(self) -> None:
        """Edit -> Deletion of Parts (STpre criteria dialog)."""
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.DeletionOfPartsDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied and dlg.deleted:
            self._edit_finish(
                snap, f"Deletion of Parts: removed {', '.join(dlg.deleted)}",
                purge_meshes=dlg.deleted)

    def _group_dialog(self) -> None:
        """Edit -> Group (Create new / Add / Remove / Ungroup)."""
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.GroupDialog(self.model, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, "Group: layout updated.")

    def _parts_conversion_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.PartsConversionDialog(
            self.model, self._cad_meshes, self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(snap, "Parts Conversion finished.")

    def _facet_accuracy_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        if self._cad_meshes is None:
            self._cad_meshes = []
        dlg = cab_edit_dialogs.FacetAccuracyDialog(
            self.model, self, archive=self.archive,
            cad_meshes=self._cad_meshes)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(
                snap,
                f"Facet Accuracy: rebuilt {getattr(dlg, 'reconstructed', 0)} "
                f"part(s).")

    def _flipping_part_face(self) -> None:
        """Edit -> Flipping Part Face (click part / flip selection)."""
        if not self._edit_require_model():
            return
        import cab_edit_ops
        name = None
        tri_ids = None
        picked = getattr(self, "_picked_face", None)
        if picked:
            name, cid = picked
            tri_ids = [cid]
        elif getattr(self, "_selected_kind", None) == "part":
            name = self._selected_name
        if not name:
            parts = self.model.parts()
            if len(parts) == 1:
                name = parts[0].name
        if not name:
            QMessageBox.information(
                self, "Flipping Part Face",
                "Select a part (or pick a Face in Draw Window), then run "
                "this command.")
            return
        snap = self._snapshot()
        ok = cab_edit_ops.flip_selected_triangles(
            self._cad_meshes, name, tri_ids) \
            if tri_ids else cab_edit_ops.flip_part_faces(
                self._cad_meshes, name)
        if not ok:
            self.log(f"Flipping Part Face: no tessellation for '{name}'.",
                     "WARN")
            return
        self._edit_finish(
            snap,
            f"Flipping Part Face: flipped '{name}'"
            + (f" cell {tri_ids[0]}" if tri_ids else "") + ".")

    def _part_face_paneling(self) -> None:
        """Edit -> Part Face Paneling (Esc commits, STpre Pre_eng)."""
        if not self._edit_require_model():
            return
        self._paneling_mode = True
        self._paneling_faces = []  # list[(part_name, cell_id|None)]
        # Face pick target (Control Window Target of selection)
        self._sel_target = "Face"
        self._target_label.setText("Face")
        try:
            grp = getattr(self.control, "sel_group", None)
            if grp is not None:
                for rb in grp.buttons():
                    if rb.text() == "Faces":
                        rb.setChecked(True)
                        break
        except Exception:
            pass
        self._ensure_paneling_esc()
        if self._act_paneling_esc is not None:
            self._act_paneling_esc.setEnabled(True)
        self.log(
            "Part Face Paneling: pick face(s) in Draw Window, "
            "then Esc to panelize (sketch/pipe excluded).",
            "INFO")
        self.statusBar().showMessage(
            "Part Face Paneling — pick Face, Esc to commit")

    def _ensure_paneling_esc(self) -> None:
        if getattr(self, "_act_paneling_esc", None) is not None:
            return
        act = QAction(self)
        act.setShortcut(QKeySequence("Esc"))
        act.setShortcutContext(Qt.WindowShortcut)
        act.setEnabled(False)
        act.triggered.connect(self._commit_part_face_paneling)
        self.addAction(act)
        self._act_paneling_esc = act

    def _commit_part_face_paneling(self) -> None:
        if not getattr(self, "_paneling_mode", False):
            return
        self._paneling_mode = False
        if self._act_paneling_esc is not None:
            self._act_paneling_esc.setEnabled(False)
        faces = list(getattr(self, "_paneling_faces", []) or [])
        picked = getattr(self, "_picked_face", None)
        if not faces and picked:
            faces = [picked]
        if not faces and getattr(self, "_selected_kind", None) == "part" \
                and self._selected_name:
            faces = [(self._selected_name, None)]
        if not faces:
            self.log("Part Face Paneling: no face selected.", "WARN")
            self.statusBar().showMessage("Ready")
            return
        import cab_edit_ops
        snap = self._snapshot()
        created = []
        seen_parts = set()
        for name, cell in faces:
            # One panel per part face pick; skip duplicate part+cell
            key = (name, cell)
            if key in seen_parts:
                continue
            seen_parts.add(key)
            pname = cab_edit_ops.panelize_part_face(
                self.model, self._cad_meshes, name,
                None if cell is None else int(cell))
            if pname:
                created.append(pname)
            else:
                self.log(
                    f"Part Face Paneling: skipped '{name}' "
                    "(sketch/pipe or no geometry).", "WARN")
        if created:
            self._edit_finish(
                snap,
                f"Part Face Paneling: created {', '.join(created)}.")
        else:
            self.log("Part Face Paneling: nothing created.", "WARN")
        self.statusBar().showMessage("Ready")

    def _sweep_part_face_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.FaceExtrusionDialog(
            self.model, self._cad_meshes, self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(
                snap,
                f"Sweep Part Face: created '{dlg.created_name}'.")

    def _alignment_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.AlignPartsDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, "Alignment finished.")

    def _place_part_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.PlacePartDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, "Place Part finished.")

    def _mirror_copy_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.MirrorCopyDialog(
            self.model, [], self, cad_meshes=self._cad_meshes)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(
                snap,
                f"Mirror Copy Parts: created {', '.join(dlg.created)}.")

    def _connected_region_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.ConnectedRegionDialog(self.model, self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(snap, "Connected Region registered.")

    def _blend_edge_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.BlendEdgeDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, 'Blend Edge / Chamfer finished.')

    def _boolean_operation_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.BooleanOperationDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            eng = getattr(dlg, "backend", "") or "?"
            self._edit_finish(
                snap,
                f"Boolean Operation: '{dlg.result_name}' ({eng}).")

    def _shape_change_boolean_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.ShapeChangeBooleanDialog(self.model, self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(
                snap, "Shape change by Boolean operation applied.")

    def _cutting_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.CuttingPlaneDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(
                snap,
                f"Cutting: created {', '.join(dlg.created)}.")

    def _edit_solid_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.EditSolidDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            n = getattr(dlg, "deleted", 0) or 0
            msg = ("Edit Solid finished."
                   if not n else f"Edit Solid: deleted {n} triangle(s).")
            self._edit_finish(snap, msg)

    def _part_simplification_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.PartSimplificationDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            n = getattr(dlg, "deleted", 0) or 0
            msg = ("Part Simplification finished."
                   if not n else
                   f"Part Simplification: deleted {n} triangle(s).")
            self._edit_finish(snap, msg)

    def _shape_simplification_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.ShapeSimplificationDialog(self.model, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, "Shape Simplification finished.")

    def _fem_conversion_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.FEMConversionDialog(
            self.model, self, cad_meshes=getattr(self, "_cad_meshes", []))
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, "FEM Conversion finished.")

    def _facets_to_solid_dialog(self) -> None:
        """Edit -> Convert Facets to Solid: faceted part -> solid x_t part."""
        if not self._edit_require_model():
            return
        from PyQt5.QtWidgets import QInputDialog
        candidates = [
            p.name for p in self.model.parts()
            if p.kind in ("polygon", "body", "stl")
            and next((m for m in (self._cad_meshes or [])
                      if getattr(m, "name", None) == p.name
                      and len(getattr(m, "triangles", []))), None) is not None]
        if not candidates:
            QMessageBox.information(
                self, "Convert Facets to Solid",
                "No faceted part with triangles found.")
            return
        if len(candidates) > 1:
            name, ok = QInputDialog.getItem(
                self, "Convert Facets to Solid", "Part:", candidates,
                0, False)
            if not ok or not name:
                return
        else:
            name = candidates[0]
        import cab_edit_ops
        snap = self._snapshot()
        new_name = cab_edit_ops.facets_to_solid_part(
            self.model, self.archive, self._cad_meshes, name)
        if new_name is None:
            QMessageBox.warning(
                self, "Convert Facets to Solid",
                "Conversion failed (kernel unavailable or mesh not closed).")
            return
        self._edit_finish(
            snap, f"Convert Facets to Solid: created '{new_name}'.")

    def _wrapping_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.WrappingDialog(
            self.model, self._cad_meshes, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(
                snap, f"Wrapping: created '{dlg.created_name}'.")

    def _reset_domain_dialog(self) -> None:
        """Edit -> Reset Computational Domain (coord / gravity / defaults).

        Distinct from tree double-click [Edit Computational Domain].
        """
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.ResetComputationalDomainDialog(
            self.model, self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(
                snap, "Reset Computational Domain applied.")
            self.control.load_sketch(self.model)

    def _edit_wiring_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.EditWiringOnBoardDialog(self.model, self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, "Edit Wiring on Board: registered.")

    def _placement_of_image_dialog(self) -> None:
        if not self._edit_require_model():
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.PlaceImageDialog(self.model, self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(snap, "Placement of Image applied.")

    # ------------------------------------------------------------- events

    def _on_item_selected(self, kind: str, name) -> None:
        self._selected_kind = kind
        self._selected_name = name
        self.control.show_property(kind, name, self.model, self.props)
        self.prop_fields = self.control.prop_fields
        self._mode_label.setText("Part" if kind == "part" else kind)

    def _on_items_selected(self, pairs: list) -> None:
        """Track Ctrl/Shift multi-selection from Layout of Parts tree."""
        self._selected_items = list(pairs or [])
        n_parts = sum(1 for k, _ in self._selected_items if k == "part")
        if n_parts > 1:
            self._mode_label.setText(f"Parts ({n_parts})")

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
        if not data:
            return
        if data[0] == "part_lib":
            # Property pane summary; Place via double-click.
            entry = data[2] if len(data) > 2 else {}
            self.control.show_library_part(str(data[1] or ""), entry or {})
            return
        if data[0] in ("file", "folder", "material", "material_group",
                       "part_lib_group"):
            return
        self._on_item_selected(data[0], data[1])

    def _on_lib_activated(self, item, _column: int = 0) -> None:
        """Double-click Library → Place registered project part (MVP)."""
        data = item.data(0, Qt.UserRole) if item is not None else None
        if not data or data[0] != "part_lib":
            return
        entry = data[2] if len(data) > 2 else None
        if isinstance(entry, dict):
            self._place_library_part(entry)

    def _open_3dfindit(self) -> None:
        """P7: open the external 3DfindIT part search in the browser."""
        import webbrowser
        webbrowser.open("https://www.3dfindit.com")
        self.log("3DfindIT: opened external part search (web).")

    def _place_library_part(self, entry: dict) -> None:
        """Instantiate a registered library stub as a new model part."""
        if self.model is None or not entry:
            return
        try:
            import cab_parts
        except Exception:
            self.log("cab_parts unavailable.", "ERROR")
            return
        kind = (entry.get("kind") or "cube").strip() or "cube"
        if kind not in cab_parts.PRIMITIVE_KINDS:
            kind = "cube"
        base_name = (entry.get("name") or "LibPart").strip() or "LibPart"
        name = base_name
        n = 1
        while self.model.find_part(name) is not None:
            n += 1
            name = f"{base_name}_{n}"
        params = self._prompt_library_params(kind, entry)
        if params is None:
            return
        if entry.get("heat_source") is not None:
            params["heat_source"] = entry["heat_source"]
        if entry.get("temperature") is not None:
            params["temperature"] = entry["temperature"]
        attr = entry.get("attribute") or "Solid"
        mat = entry.get("material") or ""
        snap = self._snapshot()
        if not cab_parts.register_primitive(
                self.model, name=name, kind=kind, params=params,
                material=mat, attribute=attr,
                color="100,160,220,255"):
            self.log("Place library part: registration failed.", "ERROR")
            return
        tess = cab_parts.tess_for_spec(kind, params)
        tess.name = name
        self._cad_meshes = list(self._cad_meshes or []) + [tess]
        self._push_undo(snap)
        self._mark_dirty()
        self._update_title()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self._rebuild_scene()
        self.log(f"Place library part: '{name}' ({kind}) from '{base_name}'")

    def _prompt_library_params(self, kind: str, entry: dict) -> Optional[dict]:
        """P5: ask Base/Size before placing a library stub (MVP dialog)."""
        from PyQt5.QtWidgets import (
            QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
        )
        stored = entry.get("params") or {}
        base0 = tuple(stored.get("base", (0.0, 0.0, 0.0)))
        size0 = tuple(stored.get("size", (10.0, 10.0, 10.0)))
        dlg = QDialog(self)
        dlg.setWindowTitle("Place Library Part")
        form = QFormLayout(dlg)
        form.addRow(QLabel(f"Kind: {kind}"))

        def _spin(v: float) -> QDoubleSpinBox:
            sb = QDoubleSpinBox(dlg)
            sb.setRange(-1.0e9, 1.0e9)
            sb.setDecimals(3)
            sb.setValue(float(v))
            return sb

        spins: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            spins[f"b{ax}"] = _spin(base0[i] if i < len(base0) else 0.0)
            spins[f"s{ax}"] = _spin(size0[i] if i < len(size0) else 10.0)
            form.addRow(f"Base {ax.upper()}", spins[f"b{ax}"])
        for ax in "xyz":
            form.addRow(f"Size {ax.upper()}", spins[f"s{ax}"])
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec_() != QDialog.Accepted:
            return None
        return {
            "base": tuple(spins[f"b{ax}"].value() for ax in "xyz"),
            "size": tuple(spins[f"s{ax}"].value() for ax in "xyz"),
        }

    def _on_context_action(self, action: str, kind: str, name) -> None:
        """Layout of Parts tree popup (STpre labels / multi-select)."""
        if action == "refer":
            if kind == "domain":
                self._domain_dialog()
            elif kind == "mesh_block":
                self._mesh_block_dialog()
            elif kind == "part" and name:
                # ``name`` may be a single part or a list from older callers
                target = name[0] if isinstance(name, list) else name
                if target:
                    self._part_dialog(target)
            else:
                self._on_item_selected(kind, name)
            return

        names = self._context_part_names(name)
        if action == "translate_copy":
            self._ctx_translate_copy(names)
        elif action == "delete":
            self._ctx_delete_parts(names)
        elif action == "change_settings":
            self._ctx_change_settings(names)
        elif action == "parts_list":
            self._view_list_of_part()
        elif action == "create_group":
            self._ctx_create_group(names)
        elif action == "cancel_group":
            if kind == "group" and not isinstance(name, list):
                self._ctx_cancel_group_named(str(name))
            else:
                self._ctx_cancel_group(names)
        elif action == "order_copy":
            self.tree_view._order_clipboard = list(names)
            self.log(f"Change order: Copy ({len(names)} part(s))")
        elif action == "order_append_prev":
            self._ctx_order_append(names_or_anchor=name, before=True)
        elif action == "order_append_next":
            self._ctx_order_append(names_or_anchor=name, before=False)
        elif action == "order_append_group":
            self._ctx_order_append_group(name)
        elif action == "rearrange_group":
            self._ctx_rearrange_group(str(name) if name else "")
        elif action == "register_library":
            self._ctx_register_library(names)
        elif action == "replace_library":
            self._ctx_replace_from_library(names)
        else:
            self._nyi(f"Layout context: {action}")

    def _context_part_names(self, name) -> list[str]:
        if isinstance(name, list):
            return [n for n in name if n]
        selected = [
            n for k, n in getattr(self, "_selected_items", [])
            if k == "part" and n]
        if selected:
            return selected
        if name:
            return [str(name)]
        return []

    def _clone_cad_mesh(self, src: str, dst: str) -> None:
        import copy
        meshes = list(self._cad_meshes or [])
        src_m = next((m for m in meshes if getattr(m, "name", None) == src),
                     None)
        if src_m is None:
            return
        clone = copy.deepcopy(src_m)
        clone.name = dst
        meshes.append(clone)
        self._cad_meshes = meshes

    def _ctx_translate_copy(self, names: list[str]) -> None:
        if not self._edit_require_model() or not names:
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.TranslationCopyPartDialog(
            self.model, names, self)
        if dlg.exec_() and dlg.applied:
            for src, new_name in getattr(dlg, "created_pairs", []) or []:
                self._clone_cad_mesh(src, new_name)
            msg = "Translation/Copy Part applied."
            if dlg.created:
                msg = (f"Translation/Copy Part: created "
                       f"{', '.join(dlg.created)}.")
            self._edit_finish(snap, msg)

    def _ctx_delete_parts(self, names: list[str]) -> None:
        if not self._edit_require_model() or not names:
            return
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Delete Part",
            f"Delete {len(names)} part(s)?\n"
            + ", ".join(names[:12])
            + ("…" if len(names) > 12 else ""),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        snap = self._snapshot()
        deleted = []
        for n in names:
            if self.model.delete_part(n):
                deleted.append(n)
                self._hidden_parts.discard(n)
        if deleted:
            self._edit_finish(
                snap, f"Delete Part: removed {', '.join(deleted)}",
                purge_meshes=deleted)
        else:
            self.log("Delete Part: nothing removed.", "WARN")

    def _ctx_change_settings(self, names: list[str]) -> None:
        if not self._edit_require_model() or not names:
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.ChangePartSettingTogetherDialog(
            self.model, names, props=self.props, parent=self)
        if dlg.exec_() and dlg.applied:
            self._edit_finish(
                snap,
                f"Change part setting together: {len(names)} part(s).")

    def _ctx_create_group(self, names: list[str]) -> None:
        if not self._edit_require_model():
            return
        from PyQt5.QtWidgets import QInputDialog
        gname, ok = QInputDialog.getText(
            self, "Create Group", "Group name:")
        gname = (gname or "").strip()
        if not ok or not gname:
            return
        snap = self._snapshot()
        moved = self.model.move_parts_to_group(names or [], gname)
        self._edit_finish(
            snap,
            f"Create Group '{gname}'"
            + (f" ({len(moved)} part(s))" if moved else "."))

    def _ctx_cancel_group(self, names: list[str]) -> None:
        if not self._edit_require_model() or not names:
            return
        snap = self._snapshot()
        moved = self.model.move_parts_to_group(names, "")
        self._edit_finish(
            snap, f"Cancel Group: {len(moved)} part(s) to root.")

    def _ctx_cancel_group_named(self, group_name: str) -> None:
        if not self._edit_require_model() or not group_name:
            return
        import cab_edit_ops
        snap = self._snapshot()
        moved = cab_edit_ops.ungroup(self.model, group_name)
        self._edit_finish(
            snap,
            f"Cancel Group '{group_name}' ({len(moved)} part(s)).")

    def _ctx_order_append(self, names_or_anchor, *, before: bool) -> None:
        if not self._edit_require_model():
            return
        clip = list(getattr(self.tree_view, "_order_clipboard", []) or [])
        anchor = names_or_anchor
        if isinstance(anchor, list):
            anchor = anchor[0] if anchor else None
        if not clip or not anchor:
            self.log("Change order: Copy parts first, then Append.", "WARN")
            return
        snap = self._snapshot()
        moved = self.model.reorder_parts(clip, str(anchor), before=before)
        where = "previous" if before else "next"
        self._edit_finish(
            snap,
            f"Change order: Append({where}) — {len(moved)} part(s).")

    def _ctx_order_append_group(self, target) -> None:
        if not self._edit_require_model():
            return
        clip = list(getattr(self.tree_view, "_order_clipboard", []) or [])
        if not clip:
            self.log("Change order: Copy parts first.", "WARN")
            return
        from PyQt5.QtWidgets import QInputDialog
        gname = ""
        if isinstance(target, str) and target:
            # If target is a part, use its group; if group name, use it
            import cab_edit_ops
            part = next((p for p in self.model.parts() if p.name == target),
                        None)
            if part is not None and part.group:
                gname = part.group
            else:
                groups = cab_edit_ops.group_names(self.model)
                if target in groups:
                    gname = target
        if not gname:
            gname, ok = QInputDialog.getText(
                self, "Append to group", "Group name:")
            gname = (gname or "").strip()
            if not ok or not gname:
                return
        snap = self._snapshot()
        moved = self.model.move_parts_to_group(clip, gname)
        self._edit_finish(
            snap,
            f"Change order; Append to group '{gname}' "
            f"({len(moved)} part(s)).")

    def _ctx_rearrange_group(self, group_name: str) -> None:
        if not self._edit_require_model() or not group_name:
            return
        from PyQt5.QtWidgets import QInputDialog
        from cabxml import _first, set_text
        new_name, ok = QInputDialog.getText(
            self, "Rearrange Group Name", "New group name:",
            text=group_name)
        new_name = (new_name or "").strip()
        if not ok or not new_name or new_name == group_name:
            return
        snap = self._snapshot()
        for grp in self.model.groups():
            n = _first(grp, "name")
            if n is not None and (n.text or "").strip() == group_name:
                set_text(n, new_name)
                self._edit_finish(
                    snap,
                    f"Rearrange Group Name: '{group_name}' → '{new_name}'.")
                return
        self.log(f"Group '{group_name}' not found.", "WARN")

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
        point_on = self.control.layer_on("point")
        elem_on = self.control.layer_on("element")
        for actor, pname in self.actors:
            if pname == name:
                layer_on = (point_on if name in self._point_part_names
                            else part_on)
                actor.SetVisibility(1 if (visible and layer_on) else 0)
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
                if pname in getattr(self, "_point_part_names", set()):
                    continue  # Point layer owns point-kind markers
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
        if target == "Detail":
            self._view_layer_detail_dialog()
            return
        self._target_label.setText(target)
        self._sel_target = target
        # Face / Vertices / Domain boundary → VTK pick (_on_left_click)
        if target in ("Part", "Parts", "Face", "Faces", "Faces + Vertices",
                      "Vertices", "Vertex", "DomainBoundary"):
            self.log(f"Selection target: {target}")
            return
        self.log(f"Selection target: {target}", "INFO")

    def _layer_detail_rows(self) -> list[tuple[str, str, int, str]]:
        """Read-only per-layer summary for Control → Drawing On/Off → Detail.

        Returns ``(label, On/Off, actor_count, note)`` rows so the dialog is
        a thin view over the current scene state.
        """
        names = {
            "part": "Part",
            "mesh_block": "Mesh block",
            "element": "Element division",
            "condition": "Condition (flow, etc)",
            "sketch_plane": "Sketch plane",
            "domain_frame": "Domain frame",
            "mesh": "Mesh",
            "face": "Face division",
            "axis_global": "Axis (Global)",
            "axis_sketch": "Axis (Sketch)",
            "origin": "Origin",
            "point": "Point",
            "aspect_ratio": "Aspect ratio",
            "root_block": "RootBlock",
        }
        notes = {
            "condition": "Domain-boundary wireframe overlay (MVP).",
            "aspect_ratio": "Element occupancy wireframe (MVP).",
            "point": "Point-kind part markers (octahedron).",
        }
        rows: list[tuple[str, str, int, str]] = []
        for key, label in names.items():
            cb = self.control.layer_checks.get(key)
            state = "On" if (cb is not None and cb.isChecked()) else "Off"
            count = len(self._layer_actors.get(key, []) or [])
            rows.append((label, state, count, notes.get(key, "")))
        return rows

    def _view_layer_detail_dialog(self) -> None:
        """Control → Drawing On/Off → Detail: real per-layer sheet."""
        from PyQt5.QtWidgets import (
            QDialog, QHBoxLayout, QHeaderView, QPushButton, QTableWidget,
            QTableWidgetItem, QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Drawing On/Off — Detail")
        dlg.resize(560, 420)
        lay = QVBoxLayout(dlg)
        table = QTableWidget(0, 4, dlg)
        table.setHorizontalHeaderLabels(
            ["Layer", "State", "Actors", "Note"])
        table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for label, state, count, note in self._layer_detail_rows():
            r = table.rowCount()
            table.insertRow(r)
            for c, text in enumerate((label, state, str(count), note)):
                table.setItem(r, c, QTableWidgetItem(text))
        lay.addWidget(table, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        brow.addWidget(ok)
        lay.addLayout(brow)
        dlg.exec_()

    def _face_condition_types(self) -> dict[str, list[str]]:
        """Map each DomainBoundary face to the condition value types on it."""
        types: dict[str, list[str]] = {f: [] for f in
                                       ("Xmin", "Xmax", "Ymin", "Ymax",
                                        "Zmin", "Zmax")}
        if self.model is None:
            return types
        for c in self.model.conditions():
            region = ""
            value_name = ""
            for ch in c:
                if ch.tag == "region":
                    region = (ch.text or "").strip()
                elif ch.tag == "value":
                    value_name = (ch.text or "").strip()
            if region not in types or not value_name:
                continue
            v = self.model.find_value(value_name)
            vtype = (v.attrib.get("type") or "") if v is not None else ""
            if vtype:
                types[region].append(vtype)
        return types

    @staticmethod
    def _condition_face_color(
            types: list[str]) -> tuple[float, float, float]:
        """Per-face condition color (flux > wall > thermal > fixed > other)."""
        priority = (
            ("flux", (0.25, 0.45, 1.0)),
            ("wall", (0.15, 0.7, 0.3)),
            ("heat_transfer", (1.0, 0.55, 0.1)),
            ("radiation_boundary", (1.0, 0.75, 0.15)),
            ("fixed_temperature", (0.9, 0.2, 0.2)),
            ("fixed_velocity", (0.2, 0.7, 0.8)),
            ("fixed_pressure", (0.6, 0.4, 0.9)),
        )
        for key, color in priority:
            if key in types:
                return color
        if types:
            return (0.8, 0.4, 0.8)
        return (0.62, 0.62, 0.62)

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

    def _install_draw_view_shortcuts(self) -> None:
        """STpre Draw Window keys: X/Y/Z(/Shift) plane views + F Fit.

        Bound with WidgetWithChildrenShortcut on the VTK widget so they
        only fire when the Draw Window has focus (Operation manual).
        """
        if self.vtk_widget is None or QKeySequence is None:
            return
        # Menu actions: show X/Y/Z and activate only with Draw focus
        for act, seq in (
            (getattr(self, "_act_yz", None), "X"),
            (getattr(self, "_act_xz", None), "Y"),
            (getattr(self, "_act_xy", None), "Z"),
        ):
            if act is None:
                continue
            act.setShortcut(QKeySequence(seq))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.vtk_widget.addAction(act)
        # Shift+X/Y/Z → opposite viewpoint (Pre_eng Keyboard)
        for seq, plane in (("Shift+X", "yz"), ("Shift+Y", "xz"),
                           ("Shift+Z", "xy")):
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(
                lambda _=False, p=plane: self._set_plane(p, negative=True))
            self.vtk_widget.addAction(act)
        # F → Fit to DrawWindow (draw focus); Ctrl+F stays window-wide
        act_f = QAction(self)
        act_f.setShortcut(QKeySequence("F"))
        act_f.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        act_f.triggered.connect(self._fit_view)
        self.vtk_widget.addAction(act_f)
        tip = "Fit to DrawWindow (F when Draw Window focused; Ctrl+F)"
        if getattr(self, "_act_fit", None) is not None:
            self._act_fit.setToolTip(tip)
            self._act_fit.setStatusTip(tip)

    def _dispatch_view_key(self, keysym: str, *, shift: bool = False
                           ) -> bool:
        """Apply a Draw Window view key. Returns True if handled."""
        action = view_key_action(keysym, shift=shift)
        if action is None:
            return False
        if action[0] == "fit":
            self._fit_view()
            return True
        _, plane, negative = action
        self._set_plane(plane, negative=negative)
        return True

    def _on_vtk_key_press(self, obj, _event) -> None:
        """Backup path when VTK interactor receives X/Y/Z/F before Qt."""
        try:
            sym = (obj.GetKeySym() or "").lower()
            shift = bool(obj.GetShiftKey())
        except Exception:
            return
        # Ignore modifier-only; strip "shift_" prefix if present
        if sym.startswith("shift_"):
            return
        self._dispatch_view_key(sym, shift=shift)

    def _vtk_window_ready(self) -> bool:
        """True when the QVTK widget has a mapped native window.

        Initializing / rendering before this yields a blank Draw Window on
        Win32 until the user clicks (which forces an expose + Render).
        """
        if self.vtk_widget is None:
            return False
        try:
            if not self.isVisible() or not self.vtk_widget.isVisible():
                return False
            return int(self.vtk_widget.winId()) != 0
        except Exception:
            return False

    def _ensure_interactor(self, *, force: bool = False) -> None:
        """Trackball + observers（对齐 pph_gui View3DTab.showEvent）。

        Deferred until the Draw Window is visible so ``Initialize`` binds to
        a live OpenGL surface.  ``force=True`` skips the readiness gate
        (last-resort startup path).
        """
        if not self._enable_3d or self.vtk_widget is None or self._iren_ready:
            return
        if not force and not self._vtk_window_ready():
            return
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleTrackballCamera)
        except Exception:
            vtkInteractorStyleTrackballCamera = (
                vtk.vtkInteractorStyleTrackballCamera)
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self._trackball_style = vtkInteractorStyleTrackballCamera()
        # Manual clipping refresh after zoom/pan — auto-adjust often clips
        # large RootBlock / Domain wireframe edges after wheel zoom.
        try:
            self._trackball_style.AutoAdjustCameraClippingRangeOff()
        except Exception:
            pass
        iren.SetInteractorStyle(self._trackball_style)
        iren.AddObserver("MouseMoveEvent", self._on_mouse_move, 1.0)
        iren.AddObserver("KeyPressEvent", self._on_vtk_key_press, 1.0)
        iren.AddObserver("LeftButtonPressEvent", self._on_left_click, 1.0)
        iren.AddObserver("RightButtonPressEvent", self._on_draw_right_click, 1.0)
        iren.AddObserver("EndInteractionEvent", self._on_end_interaction, 1.0)
        iren.AddObserver(
            "MouseWheelForwardEvent", self._on_camera_interact, 1.0)
        iren.AddObserver(
            "MouseWheelBackwardEvent", self._on_camera_interact, 1.0)
        self._cell_picker = vtk.vtkCellPicker()
        self._cell_picker.SetTolerance(0.005)
        self._sel_target = getattr(self, "_sel_target", "Part")
        self._picked_face = None  # (part_name, cell_id)
        self._picked_vertex = None  # (part_name, vertex_idx, xyz)
        self._pick_dialog = None    # non-modal dialog waiting for vertex picks
        self._pick_slot: Optional[str] = None  # "P1" | "P2" | None
        # QVTKRenderWindowInteractor.Initialize() sets up the Qt/VTK bridge;
        # falling back to the raw iren when the widget API is unavailable.
        if hasattr(self.vtk_widget, "Initialize"):
            self.vtk_widget.Initialize()
        else:
            iren.Initialize()
        self._iren_ready = True
        self._set_orientation_marker(self.control.layer_on("axis_global"))

    def _on_end_interaction(self, _obj=None, _evt=None) -> None:
        self._refresh_camera_clipping()

    def _on_camera_interact(self, _obj=None, _evt=None) -> None:
        # Wheel zoom may not always emit EndInteraction on all VTK builds.
        self._refresh_camera_clipping()

    def _refresh_camera_clipping(self) -> None:
        """Widen near/far after zoom so Domain/RootBlock wireframes stay intact."""
        if self.renderer is None:
            return
        try:
            self.renderer.ResetCameraClippingRange()
            cam = self.renderer.GetActiveCamera()
            near, far = cam.GetClippingRange()
            span = max(far - near, abs(far), abs(near), 1e-3)
            pad = span * 2.0
            cam.SetClippingRange(near - pad, far + pad)
        except Exception:
            pass

    def _clip_exempt_actors(self) -> set:
        """Overlays that must stay whole under View→Clipping (STpre-like)."""
        keys = (
            "root_block", "domain_frame", "condition", "aspect_ratio",
            "sketch_plane", "axis_sketch", "origin", "mesh", "mesh_block",
        )
        out = set()
        for k in keys:
            for a in self._layer_actors.get(k, []) or []:
                out.add(a)
        return out

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
            try:
                style.AutoAdjustCameraClippingRangeOff()
            except Exception:
                pass
            self._rubber_style = style
            iren.SetInteractorStyle(style)
            self._mouse_mode = "rubber"
            self._op_label.setText("Rubber")
            self._act_rubber.setChecked(True)
            self._act_trackball.setChecked(False)
            self.log("Mouse: Rubber Band Zoom — drag a box to zoom")
        else:
            self._trackball_style = vtkInteractorStyleTrackballCamera()
            try:
                self._trackball_style.AutoAdjustCameraClippingRangeOff()
            except Exception:
                pass
            iren.SetInteractorStyle(self._trackball_style)
            self._mouse_mode = "trackball"
            self._op_label.setText("Trackball")
            self._act_trackball.setChecked(True)
            self._act_rubber.setChecked(False)
            self.log("Mouse: Trackball — L-rotate / M-pan / R-zoom / wheel")
        self._refresh_camera_clipping()

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
            dlg = getattr(self, "_sketch_dlg", None)
            if dlg is not None and getattr(
                    dlg, "accepts_plane_picks", lambda: False)():
                import cab_sketch
                uv = cab_sketch.pick_sketch_uv_mm(
                    self.renderer, float(x), float(y), dlg.plane)
                if uv is not None:
                    self._coord_label.setText(
                        f"UV( {uv[0]:.4g} , {uv[1]:.4g} ) mm")
                    return
            picker = vtk.vtkWorldPointPicker()
            picker.Pick(float(x), float(y), 0.0, self.renderer)
            wx, wy, wz = picker.GetPickPosition()
            # show mm to match STpre / XML units
            self._coord_label.setText(
                f"( {wx * 1000:.4g} , {wy * 1000:.4g} , {wz * 1000:.4g} )")
        except Exception:
            pass

    def _on_left_click(self, obj, _event) -> None:
        """Sketch-plane vertex pick, or Face/Vertex pick via vtkCellPicker."""
        if self.renderer is None:
            return
        try:
            x, y = obj.GetEventPosition()
        except Exception:
            return

        # Sketch Part dialog open → click sketch plane to add UV vertices
        dlg = getattr(self, "_sketch_dlg", None)
        if dlg is not None and getattr(dlg, "accepts_plane_picks", lambda: False)():
            try:
                import cab_sketch
                uv = cab_sketch.pick_sketch_uv_mm(
                    self.renderer, float(x), float(y), dlg.plane)
                if uv is not None:
                    dlg.add_picked_vertex(uv[0], uv[1])
                    self._refresh_sketch_edit_overlay()
                    self.log(
                        f"sketch select[{dlg.points_table.rowCount()}] "
                        f"({uv[0]:g},{uv[1]:g})")
                    self.statusBar().showMessage(
                        f"sketch select[{dlg.points_table.rowCount()}] "
                        f"({uv[0]:g},{uv[1]:g})", 3000)
                    try:
                        obj.SetAbortFlag(1)
                    except Exception:
                        pass
                    return
            except Exception as exc:
                self.log(f"Sketch pick failed: {exc}", "WARN")

        if not hasattr(self, "_cell_picker"):
            return
        target = getattr(self, "_sel_target", "Part")
        if target in ("Part", "Parts", None):
            return
        if target == "DomainBoundary":
            if self.model is None:
                return
            faces = self.model.domain_faces() or []
            if not faces:
                self.log("Domain boundary: no DomainBoundary faces.", "WARN")
                return
            fname = self._domain_boundary_from_pick(float(x), float(y))
            if fname is None:
                fname = faces[0][0]
            self._on_item_selected("domain_face", fname)
            self._mode_label.setText("DomainBoundary")
            self.log(f"Picked DomainBoundary: {fname}")
            try:
                obj.SetAbortFlag(1)
            except Exception:
                pass
            return
        try:
            self._cell_picker.Pick(float(x), float(y), 0.0, self.renderer)
            actor = self._cell_picker.GetActor()
            if actor is None:
                return
            cell = self._cell_picker.GetCellId()
            name = None
            # self.actors is list[(vtkActor, part_name)]
            for act, pname in getattr(self, "actors", []) or []:
                if act is actor:
                    name = pname
                    break
            if name is None and getattr(self, "_selected_kind", None) == "part":
                name = self._selected_name
            if name is None or cell < 0:
                return
            self._picked_face = (name, int(cell))
            self._selected_kind = "part"
            self._selected_name = name
            if target in ("Vertices", "Faces + Vertices", "Vertex"):
                snapped = self._snap_picked_vertex(
                    name, self._cell_picker.GetPickPosition())
                if snapped is not None:
                    self._picked_vertex = snapped
                    self._feed_pick_point(snapped)
                    vx, vy, vz = snapped[2]
                    self.log(
                        f"Picked Vertex: {name} #{snapped[1]} "
                        f"({vx:g},{vy:g},{vz:g})")
                    self.statusBar().showMessage(
                        f"Vertex {name} #{snapped[1]} "
                        f"({vx:g},{vy:g},{vz:g})", 4000)
                    try:
                        obj.SetAbortFlag(1)
                    except Exception:
                        pass
                    return
            if getattr(self, "_paneling_mode", False):
                faces = getattr(self, "_paneling_faces", None)
                if faces is None:
                    self._paneling_faces = []
                    faces = self._paneling_faces
                key = (name, int(cell))
                if key in faces:
                    faces.remove(key)
                    self.log(
                        f"Part Face Paneling: deselected '{name}' "
                        f"cell={cell}")
                else:
                    faces.append(key)
                    self.log(
                        f"Part Face Paneling: selected '{name}' "
                        f"cell={cell} ({len(faces)} face(s))")
            else:
                self.log(f"Picked {target}: part='{name}' cell={cell}")
            self._mode_label.setText(f"{target}")
        except Exception as exc:
            self.log(f"Pick failed: {exc}", "WARN")

    def _snap_picked_vertex(self, name: str, world_xyz) -> Optional[tuple]:
        """Snap a world pick to the nearest tessellation vertex of a part.

        Returns ``(part_name, vertex_idx, (x,y,z))`` or None when no vertex
        lies within the tolerance (2 mm or 5% of the part diagonal).
        """
        if not world_xyz or self.model is None:
            return None
        tess = next((m for m in (self._cad_meshes or [])
                     if getattr(m, "name", None) == name), None)
        if tess is None or getattr(tess, "points", None) is None \
                or len(tess.points) == 0:
            return None
        pts = np.asarray(tess.points, dtype=np.float64)
        transform = ""
        for p in self.model.parts():
            if p.name == name:
                transform = p.transform or ""
                break
        pts = cab_vtk._apply_transform(pts, transform)
        target = np.asarray(world_xyz, dtype=np.float64)
        d = np.linalg.norm(pts - target, axis=1)
        diag = float(np.ptp(pts, axis=0).sum()) if len(pts) > 1 else 1.0
        tol = max(0.002, 0.05 * diag)
        idx = int(np.argmin(d))
        if d[idx] > tol:
            return None
        return (name, idx, tuple(float(v) for v in pts[idx]))

    def _domain_boundary_from_pick(self, x: float, y: float) -> Optional[str]:
        """Spatial pick of a DomainBoundary face (ray vs domain AABB)."""
        if self.model is None or self.renderer is None:
            return None
        base = self.model.domain_base()
        size = self.model.domain_size()
        if base is None or size is None:
            return None
        lo = np.asarray(base, dtype=float) / 1000.0
        hi = lo + np.asarray(size, dtype=float) / 1000.0
        try:
            cam = self.renderer.GetActiveCamera()
            cam_pos = np.asarray(cam.GetPosition(), dtype=float)
            fp = np.asarray(cam.GetFocalPoint(), dtype=float)
            ray = fp - cam_pos
            n = np.linalg.norm(ray)
            if n < 1e-12:
                return None
            ray = ray / n
            picker = vtk.vtkWorldPointPicker()
            picker.Pick(float(x), float(y), 0.0, self.renderer)
            p = np.asarray(picker.GetPickPosition(), dtype=float)
            rd = p - cam_pos
            dn = np.linalg.norm(rd)
            if dn < 1e-12:
                return None
            fname = ray_aabb_face(cam_pos, rd, lo, hi)
            if fname is None:
                return None
            known = {n for n, _e in self.model.domain_faces()}
            if fname in known:
                return fname
            return None
        except Exception as exc:
            self.log(f"Domain boundary pick failed: {exc}", "WARN")
            return None

    def _on_draw_right_click(self, obj, _event) -> None:
        """M35: Draw Window RMB — Layout-style part popup subset."""
        if self.renderer is None or not hasattr(self, "_cell_picker"):
            return
        # In trackball mode RMB is zoom; only show menu with Ctrl held
        try:
            if (getattr(self, "_mouse_mode", "trackball") == "trackball"
                    and not obj.GetControlKey()):
                return
            x, y = obj.GetEventPosition()
            self._cell_picker.Pick(float(x), float(y), 0.0, self.renderer)
            actor = self._cell_picker.GetActor()
            name = None
            for act, pname in getattr(self, "actors", []) or []:
                if act is actor:
                    name = pname
                    break
            if name is None:
                if getattr(self, "_selected_kind", None) == "part":
                    name = self._selected_name
            if not name:
                return
            from PyQt5.QtWidgets import QMenu
            from PyQt5.QtGui import QCursor
            self._on_item_selected("part", name)
            menu = QMenu(self)
            menu.addAction(
                "Refer to Part",
                lambda n=name: self._on_context_action("refer", "part", n))
            menu.addAction(
                "Display Part",
                lambda n=name: self._set_part_visible(n, True))
            menu.addAction(
                "Hide Part",
                lambda n=name: self._set_part_visible(n, False))
            menu.addAction(
                "Property...",
                lambda n=name: self._on_item_activated("part", n))
            menu.addAction(
                "Register to library...",
                lambda n=name: self._on_context_action(
                    "register_library", "part", [n]))
            menu.addAction(
                "Replace from library...",
                lambda n=name: self._on_context_action(
                    "replace_library", "part", [n]))
            menu.addAction(
                "Delete Part",
                lambda n=name: self._on_context_action("delete", "part", [n]))
            menu.exec_(QCursor.pos())
            try:
                obj.SetAbortFlag(1)
            except Exception:
                pass
        except Exception as exc:
            self.log(f"Draw context menu failed: {exc}", "WARN")

    def _view_display_all(self) -> None:
        self._hidden_parts.clear()
        self._material_filter = None
        self._rebuild_scene()
        self.log("View: Display All Parts")

    def _view_hide_selected(self) -> None:
        names = [
            n for k, n in getattr(self, "_selected_items", [])
            if k == "part" and n
        ]
        if not names and getattr(self, "_selected_kind", None) == "part" \
                and self._selected_name:
            names = [self._selected_name]
        if names:
            self._hidden_parts.update(names)
            self._rebuild_scene()
            if len(names) == 1:
                self.log(f"View: Hide '{names[0]}'")
            else:
                self.log(f"View: Hide {len(names)} parts")
        else:
            self.log("View: select a part to hide.", "WARN")

    def _view_clipping_dialog(self) -> None:
        """M25: Clipping plane on Draw Window."""
        if self.renderer is None:
            self.log("Clipping requires 3D view.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QDialog, QFormLayout, QDoubleSpinBox, QPushButton, QHBoxLayout,
            QVBoxLayout, QCheckBox, QComboBox,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Clipping")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        axis = QComboBox(dlg)
        axis.addItems(["X", "Y", "Z"])
        pos = QDoubleSpinBox(dlg)
        pos.setRange(-1e6, 1e6)
        pos.setDecimals(3)
        pos.setValue(0.0)
        en = QCheckBox("Enable clipping", dlg)
        en.setChecked(bool(self._clip_planes))
        if self._clip_planes:
            try:
                o = self._clip_planes[0].GetOrigin()
                n = self._clip_planes[0].GetNormal()
                ax_i = max(range(3), key=lambda i: abs(n[i]))
                axis.setCurrentIndex(ax_i)
                pos.setValue(float(o[ax_i]) * 1000.0)
            except Exception:
                pass
        form.addRow("Axis", axis)
        form.addRow("Position (mm)", pos)
        form.addRow(en)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _apply() -> None:
            if not en.isChecked():
                self._clip_planes = []
                self._apply_clip_planes()
                if self.vtk_widget is not None:
                    self.vtk_widget.GetRenderWindow().Render()
                self.log("Clipping: off")
                dlg.accept()
                return
            plane = vtk.vtkPlane()
            n = [0.0, 0.0, 0.0]
            n[{"X": 0, "Y": 1, "Z": 2}[axis.currentText()]] = 1.0
            plane.SetNormal(*n)
            o = [0.0, 0.0, 0.0]
            o[{"X": 0, "Y": 1, "Z": 2}[axis.currentText()]] = \
                pos.value() / 1000.0
            plane.SetOrigin(*o)
            self._clip_planes = [plane]
            self._apply_clip_planes()
            if self.vtk_widget is not None:
                self.vtk_widget.GetRenderWindow().Render()
            self.log(
                f"Clipping: {axis.currentText()}={pos.value():g} mm "
                "(parts only; Domain/RootBlock frame kept)")
            dlg.accept()

        ok.clicked.connect(_apply)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _apply_clip_planes(self) -> None:
        """Push the active clip planes onto part mappers.

        vtkOpenGLRenderer has no RemoveAllClipPlanes/AddClipPlane in this
        VTK build; per-mapper clipping is the portable way. Domain /
        RootBlock / axis overlays stay unclipped so the outer frame remains
        a closed cuboid (STpre-like).
        """
        if self.renderer is None:
            return
        props = self.renderer.GetViewProps()
        if props is None:
            return
        exempt = self._clip_exempt_actors()
        for i in range(props.GetNumberOfItems()):
            actor = props.GetItemAsObject(i)
            mapper = getattr(actor, "GetMapper", lambda: None)()
            if mapper is None or not hasattr(mapper, "RemoveAllClippingPlanes"):
                continue
            mapper.RemoveAllClippingPlanes()
            if actor in exempt:
                continue
            for plane in self._clip_planes:
                mapper.AddClippingPlane(plane)

    def _view_toggle_virtual(self, on: bool = True) -> None:
        """View → (Setting) → Display Virtual Part."""
        self._hide_virtual_parts = not bool(on)
        if self.model is not None:
            for p in self.model.parts():
                el = self.model.find_part(p.name)
                if el is None:
                    continue
                from cabxml import _first
                virt = _first(el, "virtual")
                is_v = virt is not None and (
                    (virt.text or "").strip().upper() in ("T", "1", "TRUE"))
                if is_v and self._hide_virtual_parts:
                    self._hidden_parts.add(p.name)
                elif is_v and not self._hide_virtual_parts:
                    self._hidden_parts.discard(p.name)
            self._rebuild_scene()
        self.log(
            "View: Display Virtual Part "
            + ("ON" if on else "OFF"))

    def _load_project_part_library(self) -> None:
        """Restore [Project Parts] stubs from project_value JSON."""
        import json
        self.control._project_part_library = []
        if self.model is None:
            return
        raw = self.model.project_value("part_library", "") or ""
        if not raw.strip():
            return
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                self.control._project_part_library = data
        except Exception:
            pass

    def _ctx_replace_from_library(self, names: list[str]) -> None:
        # Replace selected part's attributes from the [Project Parts] library.
        if not names:
            self.log('Replace from library: select a part.', 'WARN')
            return
        lib = getattr(self.control, '_project_part_library', []) or []
        if not lib:
            self.log(
                'Library empty - register parts first (part context menu',
                ' -> Register to library...).', 'WARN')
            return
        import cab_edit_dialogs
        snap = self._snapshot()
        dlg = cab_edit_dialogs.ReplaceFromLibraryDialog(
            self.model, lib, names[0], self)
        dlg.exec_()
        if dlg.applied:
            self._edit_finish(snap, 'Replace from library finished.')

    def _ctx_register_library(self, names: list[str]) -> None:
        """Copy selected part props into Control → Library [Project Parts]."""
        if self.model is None or not names:
            self.log("Register to library: select part(s).", "WARN")
            return
        from cabxml import _first
        import json
        entries = []
        for name in names:
            p = next((x for x in self.model.parts() if x.name == name), None)
            if p is None:
                continue
            el = self.model.find_part(name)
            heat = None
            temp = None
            if el is not None:
                hs = _first(el, "heat_source")
                if hs is not None and hs.text:
                    try:
                        heat = float(hs.text.strip())
                    except ValueError:
                        pass
                te = _first(el, "temperature")
                if te is not None and te.text:
                    try:
                        temp = float(te.text.strip())
                    except ValueError:
                        pass
            params = {}
            if el is not None:
                from cabxml import _first as _f
                b = _f(el, "base")
                s = _f(el, "size")
                if b is not None and b.text:
                    try:
                        params["base"] = tuple(
                            float(x) for x in b.text.replace(",", " ").split())
                    except ValueError:
                        pass
                if s is not None and s.text:
                    try:
                        params["size"] = tuple(
                            float(x) for x in s.text.replace(",", " ").split())
                    except ValueError:
                        pass
            summary = (
                f"kind={p.kind}; attr={p.attribute}; "
                f"mat={p.property or ''}; "
                f"heat={heat}; T={temp}")
            entries.append({
                "name": name,
                "kind": p.kind,
                "attribute": p.attribute,
                "material": p.property or "",
                "heat_source": heat,
                "temperature": temp,
                "params": params,
                "summary": summary,
            })
        n = self.control.register_parts_to_library(entries)
        # Persist stub as project JSON (reload-friendly)
        try:
            lib = getattr(self.control, "_project_part_library", []) or []
            self.model.set_project_value(
                "part_library", json.dumps(lib, ensure_ascii=False))
        except Exception:
            pass
        self.control.populate_library(self.props)
        self.control.tabs.setCurrentWidget(self.control.lib_page)
        self._mark_dirty()
        self.log(f"Register to library: {n} part(s) → [Project Parts]")

    def _view_thermal_condition_display(self) -> None:
        """View → (Setting) → Thermal Condition Display (MVP color tint)."""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QCheckBox, QPushButton, QHBoxLayout, QLabel,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Thermal Condition Display")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "MVP: tint part actors by heat_source / initial temperature "
            "when present (not a full STpre scalar field).", dlg))
        chk_hs = QCheckBox("Heat source distribution", dlg)
        chk_tc = QCheckBox("Temperature / conductivity tint", dlg)
        mode = getattr(self, "_thermal_display", {}) or {}
        chk_hs.setChecked(bool(mode.get("heat_source", True)))
        chk_tc.setChecked(bool(mode.get("temperature", False)))
        lay.addWidget(chk_hs)
        lay.addWidget(chk_tc)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _ok() -> None:
            self._thermal_display = {
                "heat_source": chk_hs.isChecked(),
                "temperature": chk_tc.isChecked(),
            }
            on = chk_hs.isChecked() or chk_tc.isChecked()
            self.log(
                f"Thermal Condition Display: heat_source={chk_hs.isChecked()}, "
                f"temperature={chk_tc.isChecked()} "
                + ("(tint ON)" if on else "(tint OFF)"))
            dlg.accept()
            if self.model is not None:
                self._rebuild_scene(fit=False)

        ok.clicked.connect(_ok)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _thermal_tint_for_part(self, name: str,
                               base_color: tuple) -> tuple:
        """MVP colormap from part heat_source / temperature attributes."""
        mode = getattr(self, "_thermal_display", None) or {}
        if not mode or self.model is None:
            return base_color
        use_hs = bool(mode.get("heat_source"))
        use_t = bool(mode.get("temperature"))
        if not use_hs and not use_t:
            return base_color
        from cabxml import _first
        el = self.model.find_part(name)
        if el is None:
            return base_color
        heat = None
        temp = None
        if use_hs:
            hs = _first(el, "heat_source")
            if hs is not None and hs.text:
                try:
                    heat = abs(float(hs.text.strip()))
                except ValueError:
                    pass
        if use_t:
            te = _first(el, "temperature")
            if te is not None and te.text:
                try:
                    temp = float(te.text.strip())
                except ValueError:
                    pass
        if heat is None and temp is None:
            return base_color
        # Heat → red-yellow; temperature → cyan-magenta band
        if heat is not None and heat > 0:
            t = min(1.0, heat / 100.0)  # 100 W → full
            return (0.55 + 0.45 * t, 0.15 + 0.35 * (1.0 - t), 0.08)
        if temp is not None:
            # Map ~0–80 °C into cool→warm
            t = max(0.0, min(1.0, (temp - 0.0) / 80.0))
            return (0.15 + 0.75 * t, 0.35, 0.85 - 0.55 * t)
        return base_color

    def _view_parts_by_material(self) -> None:
        """View → (Setting) → Display parts by materials."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QComboBox, QPushButton, QHBoxLayout,
            QFormLayout, QLabel,
        )
        mats = sorted({
            (p.property or "").strip() or "(none)"
            for p in self.model.parts()})
        dlg = QDialog(self)
        dlg.setWindowTitle("Display parts")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        combo = QComboBox(dlg)
        combo.addItem("(all materials)")
        combo.addItems(mats)
        form.addRow("Material", combo)
        lay.addLayout(form)
        lay.addWidget(QLabel(
            "Parts with other materials are hidden in the Draw Window.",
            dlg))
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _ok() -> None:
            mat = combo.currentText()
            if mat == "(all materials)":
                self._material_filter = None
                self._view_display_all()
            else:
                self._material_filter = None if mat == "(none)" else mat
                want = "" if mat == "(none)" else mat
                for p in self.model.parts():
                    prop = (p.property or "").strip()
                    if prop == want:
                        self._hidden_parts.discard(p.name)
                    else:
                        self._hidden_parts.add(p.name)
                self._rebuild_scene()
                self.log(f"View: Display parts by material '{mat}'")
            dlg.accept()

        ok.clicked.connect(_ok)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _view_list_of_part(self) -> None:
        """View → (Dialog) → List of Part."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
            QPushButton, QHBoxLayout, QHeaderView,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("List of Part")
        dlg.resize(560, 360)
        lay = QVBoxLayout(dlg)
        parts = list(self.model.parts())
        tbl = QTableWidget(len(parts), 4, dlg)
        tbl.setHorizontalHeaderLabels(
            ["Name", "Attribute", "Material", "Kind"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i, p in enumerate(parts):
            tbl.setItem(i, 0, QTableWidgetItem(p.name))
            tbl.setItem(i, 1, QTableWidgetItem(p.attribute or ""))
            tbl.setItem(i, 2, QTableWidgetItem(p.property or ""))
            tbl.setItem(i, 3, QTableWidgetItem(p.kind or ""))
        lay.addWidget(tbl)

        def _select() -> None:
            row = tbl.currentRow()
            if row < 0:
                return
            name = tbl.item(row, 0).text()
            self._on_item_selected("part", name)
            self.log(f"List of Part: selected '{name}'")

        row = QHBoxLayout()
        sel = QPushButton("Select", dlg)
        close = QPushButton("Close", dlg)
        sel.clicked.connect(_select)
        close.clicked.connect(dlg.accept)
        row.addStretch(1)
        row.addWidget(sel)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec_()

    def _view_editing_part_face(self) -> None:
        """View → (Dialog) → Editing Part Face (chrome + part list)."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QLabel,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Editing Part Face")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Common-control face registry (STpre). Select a part, then use "
            "Edit → Flipping Part Face / Part Face Paneling for geometry.",
            dlg))
        lst = QListWidget(dlg)
        for p in self.model.parts():
            lst.addItem(p.name)
        lay.addWidget(lst, 1)
        row = QHBoxLayout()
        close = QPushButton("Close", dlg)
        close.clicked.connect(dlg.accept)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec_()

    def _view_editing_contact_tr(self) -> None:
        """View → (Dialog) → Editing Contact Thermal Resistance."""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Editing Contact Thermal Resistance")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Opens the common-control contact thermal resistance list.\n"
            "Full pair editing is available in Wizard → Condition Setting → "
            "Thermal Boundary → Between Parts.", dlg))
        row = QHBoxLayout()
        open_w = QPushButton("Open Condition Wizard…", dlg)
        close = QPushButton("Close", dlg)

        def _wiz() -> None:
            dlg.accept()
            self._wizard_condition()

        open_w.clicked.connect(_wiz)
        close.clicked.connect(dlg.accept)
        row.addStretch(1)
        row.addWidget(open_w)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec_()

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
        # Overlay actors were removed with ViewProps; drop stale refs
        self._sketch_edit_actors = []
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
        point_names = {p.name for p in self.model.parts()
                       if (p.kind or "").strip().lower() == "point"}
        self._point_part_names = point_names
        point_on = self.control.layer_on("point")
        for box in boxes:
            if box.name in point_names:
                # Point parts live on the Point layer (STpre Drawing On/Off),
                # independent of the Part layer.
                tree_vis = box.name not in self._hidden_parts
                pd_part = cab_vtk.part_polydata(box, for_part=True)
                if wire:
                    edge = cab_vtk.edges_actor(
                        pd_part,
                        color=self._thermal_tint_for_part(
                            box.name, box.color),
                        line_width=1.35)
                    edge.SetVisibility(1 if (point_on and tree_vis) else 0)
                    self.renderer.AddActor(edge)
                    self.actors.append((edge, box.name))
                    self._layer_actors.setdefault("point", []).append(edge)
                else:
                    mapper = vtk.vtkPolyDataMapper()
                    mapper.SetInputData(pd_part)
                    actor = vtk.vtkActor()
                    actor.SetMapper(mapper)
                    prop = actor.GetProperty()
                    prop.SetColor(*self._thermal_tint_for_part(
                        box.name, box.color))
                    prop.SetOpacity(0.35 if translucent else 1.0)
                    prop.SetInterpolationToGouraud()
                    prop.SetAmbient(0.25)
                    prop.SetDiffuse(0.85)
                    prop.SetSpecular(0.2)
                    prop.SetSpecularPower(18)
                    actor.SetVisibility(1 if (point_on and tree_vis) else 0)
                    self.renderer.AddActor(actor)
                    self.actors.append((actor, box.name))
                    self._layer_actors.setdefault("point", []).append(actor)
                continue
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
                tint = self._thermal_tint_for_part(box.name, box.color)
                edge = cab_vtk.edges_actor(
                    pd_line, color=tint, line_width=1.35)
                edge.SetVisibility(1 if (part_on and tree_vis) else 0)
                self.renderer.AddActor(edge)
                self.actors.append((edge, box.name))
            else:
                mapper = vtk.vtkPolyDataMapper()
                mapper.SetInputData(pd_part)
                actor = vtk.vtkActor()
                actor.SetMapper(mapper)
                prop = actor.GetProperty()
                prop.SetColor(*self._thermal_tint_for_part(
                    box.name, box.color))
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
                    # Face division = surface-only face grids (not the full
                    # occupancy-box wireframe).
                    try:
                        pd_lines = cab_vtk.element_division_lines(
                            self.model, box.name, interior_stride=0,
                            surface_eps=1e-5)
                    except Exception:
                        pd_lines = None
                    if pd_lines is None:
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
        # Drawing→Mesh (post-Gridding face grids) is handled separately below.
        mesh_on = self.control.layer_on("mesh")
        mesh_block_on = self.control.layer_on("mesh_block")
        if element_on or mesh_on:
            for aname in self.model.analysis_names():
                aboxes = self.model.analysis_boxes(aname)
                if not aboxes:
                    continue
                face_mode = aname in self._domain_face_mode
                if face_mode and not wire:
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
                elif not face_mode and element_on:
                    # Occupancy face grids for Domain after Meshing only
                    pd_dom = cab_vtk.element_division_lines(
                        self.model, boxes=aboxes,
                        interior_stride=0, surface_eps=0.0)
                    if pd_dom is not None:
                        dom_edge = cab_vtk.edges_actor(
                            pd_dom, color=(0.42, 0.54, 0.66),
                            line_width=1.0, opacity=0.9)
                        self.renderer.AddActor(dom_edge)
                        self._edge_actors.append((dom_edge, aname))
                        self._layer_actors["element"].append(dom_edge)

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

        # P3/L4: Condition layer - per-face domain-boundary wireframe colored
        # by the condition type bound to each face.
        if self.control.layer_on("condition"):
            frame = cab_vtk.domain_frame(self.model)
            if frame:
                face_types = self._face_condition_types()
                lo3 = frame.bounds[0:3]
                hi3 = frame.bounds[3:6]
                for fname in ("Xmin", "Xmax", "Ymin", "Ymax",
                              "Zmin", "Zmax"):
                    pd = cab_vtk.domain_face_edges(fname, lo3, hi3)
                    mapper = vtk.vtkPolyDataMapper()
                    mapper.SetInputData(pd)
                    actor = vtk.vtkActor()
                    actor.SetMapper(mapper)
                    actor.GetProperty().SetColor(
                        *self._condition_face_color(
                            face_types.get(fname, [])))
                    actor.GetProperty().SetRepresentationToWireframe()
                    actor.GetProperty().SetLineWidth(
                        1.6 if face_types.get(fname) else 1.0)
                    actor.GetProperty().LightingOff()
                    self.renderer.AddActor(actor)
                    self._layer_actors.setdefault(
                        "condition", []).append(actor)

        # P3/L4: Aspect ratio layer - occupancy wireframe colored by the
        # per-box max/min cell-width ratio.
        axes = self.model.mesh_axes() if self.model is not None else {}
        if self.control.layer_on("aspect_ratio") and axes:
            for p in self.model.parts():
                for b6 in self.model.part_boxes(p.name):
                    if len(b6) < 6:
                        continue
                    try:
                        lo = (axes["x"][b6[0] - 1] / 1000.0,
                              axes["y"][b6[2] - 1] / 1000.0,
                              axes["z"][b6[4] - 1] / 1000.0)
                        hi = (axes["x"][b6[1]] / 1000.0,
                              axes["y"][b6[3]] / 1000.0,
                              axes["z"][b6[5]] / 1000.0)
                    except IndexError:
                        continue
                    dx = max(hi[0] - lo[0], 1e-12)
                    dy = max(hi[1] - lo[1], 1e-12)
                    dz = max(hi[2] - lo[2], 1e-12)
                    ratio = max(dx, dy, dz) / min(dx, dy, dz)
                    color = aspect_ratio_color(ratio)
                    line_w = 1.0 if ratio <= 2.0 else (
                        1.5 if ratio <= 5.0 else 2.2)
                    bb = (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])
                    part_box = cab_vtk.PartBox(
                        p.name, bb, color, 1.0, cells=[bb])
                    pd = cab_vtk._make_box_polydata(part_box, wireframe=True)
                    mapper = vtk.vtkPolyDataMapper()
                    mapper.SetInputData(pd)
                    actor = vtk.vtkActor()
                    actor.SetMapper(mapper)
                    actor.GetProperty().SetColor(*part_box.color)
                    actor.GetProperty().SetRepresentationToWireframe()
                    actor.GetProperty().SetLineWidth(line_w)
                    actor.GetProperty().LightingOff()
                    self.renderer.AddActor(actor)
                    self._layer_actors.setdefault(
                        "aspect_ratio", []).append(actor)

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

        # Drawing→Mesh: post-Gridding face grids + translucent shell so rear
        # faces are depth-occluded (STpre Mesh).  Also honour Mesh block when
        # axes exist — Mesh block checkbox alone used to be suppressed by the
        # default Element-division ON state after Gridding-only.
        axes = self.model.mesh_axes() if self.model is not None else {}
        nmax = max((len(v) for v in axes.values()), default=0) if axes else 0
        if (mesh_on or mesh_block_on) and nmax > 2:
            self._ensure_depth_peeling()
            stride = 1 if nmax <= 80 else max(1, nmax // 40)
            try:
                mb_actors = cab_vtk.mesh_block_display_actors(
                    self.model, stride=stride)
            except Exception as exc:
                self.log(f"Mesh face grid draw failed: {exc}", "WARN")
                mb_actors = []
            layer_key = "mesh" if mesh_on else "mesh_block"
            for act in mb_actors:
                self.renderer.AddActor(act)
                self._layer_actors.setdefault(layer_key, []).append(act)

        self._set_orientation_marker(self.control.layer_on("axis_global"))

        if self.control.layer_on("origin"):
            # World-origin hub only. Global XYZ = corner Axis(Global);
            # local UVW = Axis(Sketch) on the sketch plane.
            scale = self._domain_scale()
            for actor in cab_vtk.world_origin_marker_actors(scale):
                self.renderer.AddActor(actor)
                self._layer_actors["origin"].append(actor)

        # Keep in-progress Sketch Part outline after full scene rebuild
        if getattr(self, "_sketch_dlg", None) is not None:
            self._refresh_sketch_edit_overlay()

        self._apply_clip_planes()
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
        self._refresh_camera_clipping()

    def _ensure_depth_peeling(self) -> None:
        """Enable depth peeling so translucent Mesh shells occlude rear grids."""
        if self.renderer is None or self.vtk_widget is None:
            return
        try:
            rw = self.vtk_widget.GetRenderWindow()
            if rw is not None:
                rw.SetAlphaBitPlanes(1)
                try:
                    rw.SetMultiSamples(0)
                except Exception:
                    pass
            self.renderer.SetUseDepthPeeling(1)
            self.renderer.SetMaximumNumberOfPeels(8)
            self.renderer.SetOcclusionRatio(0.1)
        except Exception:
            pass

    def _enable_mesh_layer_after_gridding(self) -> None:
        """Turn on Drawing→Mesh after Gridding so face grids are visible.

        STpre shows all mesh grid lines via Drawing→Mesh; Mesh defaults to
        OFF in Show/Select, so Gridding alone previously left only RootBlock.
        """
        cb = self.control.layer_checks.get("mesh")
        if cb is None or cb.isChecked():
            return
        cb.blockSignals(True)
        cb.setChecked(True)
        cb.blockSignals(False)

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

    def _set_plane(self, plane: str, *, negative: bool = False) -> None:
        """Orthographic view: XY/XZ/YZ from ±Z/±Y/±X (STpre X/Y/Z keys)."""
        if not self._enable_3d or self.renderer is None:
            return
        pos, up = plane_view_camera(plane, negative=negative)
        cam = self.renderer.GetActiveCamera()
        cam.SetFocalPoint(0, 0, 0)
        cam.SetPosition(pos[0], pos[1], pos[2])
        cam.SetViewUp(up[0], up[1], up[2])
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self.renderer.GetRenderWindow().Render()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._enable_3d:
            return
        # showEvent often runs before the native HWND/OpenGL surface is
        # ready; a synchronous rebuild still paints blank. Defer to the
        # event loop (and retry) so Sketch plane / RootBlock appear without
        # requiring a click.
        if getattr(self, "_startup_redraw", True):
            QTimer.singleShot(0, self._finish_startup_view)

    def _finish_startup_view(self) -> None:
        """First visible-frame rebuild + Render after the window is mapped."""
        if not getattr(self, "_startup_redraw", True):
            return
        if not self._enable_3d or self.model is None:
            self._startup_redraw = False
            return
        if not self._vtk_window_ready():
            self._startup_view_tries = getattr(
                self, "_startup_view_tries", 0) + 1
            if self._startup_view_tries < 40:
                QTimer.singleShot(50, self._finish_startup_view)
            else:
                # Last attempt even if readiness checks failed
                self._startup_redraw = False
                self._ensure_interactor(force=True)
                self._rebuild_scene(fit=True)
                self._force_vtk_repaint()
            return
        self._startup_redraw = False
        self._ensure_interactor()
        self._rebuild_scene(fit=True)
        self._force_vtk_repaint()
        # One extra frame after layout settles (splitters / DPI on Win32)
        QTimer.singleShot(100, self._force_vtk_repaint)

    def _force_vtk_repaint(self) -> None:
        if self.vtk_widget is None or self.renderer is None:
            return
        try:
            rw = self.vtk_widget.GetRenderWindow()
            if rw is not None:
                rw.Render()
            self.vtk_widget.update()
        except Exception:
            pass

    # ------------------------------------------------------------ actions

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", "",
            "scSTREAM project (*.cab);;All files (*)")
        if path:
            self.load(path)

    def _import_dialog(self) -> None:
        """File -> Import: add an .x_t file as new parts + cab member."""
        if self.model is None or self.archive is None:
            self.log("No project open.", "WARN")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Geometry", "",
            "Geometry (*.x_t *.xmt_txt *.step *.stp *.stl *.sat *.sab "
            "*.obj *.dxf *.mdl *.ifc *.ecxml);;"
            "IFC Building (*.ifc);;ECXML Components (*.ecxml);;"
            "Parasolid XT (*.x_t *.xmt_txt);;STEP (*.step *.stp);;"
            "OBJ (*.obj);;DXF (*.dxf);;MDL (*.mdl);;"
            "STL (*.stl);;ACIS SAT (*.sat *.sab);;All files (*)")
        if not path:
            return
        snap = self._snapshot()
        try:
            import cab_import
            ext = os.path.splitext(path)[1].lower()
            if ext in (".ifc", ".ecxml"):
                self._import_ifc_ecxml(path, ext)
                return
            if not cab_import.available():
                QMessageBox.warning(
                    self, "Import",
                    "Cradle pskernel.dll not found; cannot import XT/CAD.")
                return

            def _prog(done, total, name):
                if total and (done == 0 or done == total
                              or done % max(1, total // 10) == 0):
                    self.log(f"Import: {done}/{total} {name}")
                QApplication.processEvents()

            bodies, raw, fmt = cab_import.import_file_with_payload(
                path, progress=_prog)
            if not bodies:
                QMessageBox.warning(
                    self, "Import",
                    "No displayable body found in the file.")
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
                [b.tess for b in bodies if b.tess is not None]
            # Tree checkboxes reset to ON — clear stale hide flags so the
            # new CAD is actually drawn (was easy to confuse with Origin).
            self._hidden_parts.clear()
            # STpre: Domain(cuboid) + RootBlock follow CAD bounding box
            try:
                import cab_domain
                fitted = cab_domain.fit_domain_to_parts(
                    self.model, self._cad_meshes)
            except Exception as exc:
                fitted = None
                self.log(f"Domain auto-fit skipped: {exc}", "WARN")
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
            if fitted is not None:
                mn, mx = fitted
                self.log(
                    f"Domain(cuboid) fitted to CAD bbox: "
                    f"min=({mn[0]:.6g},{mn[1]:.6g},{mn[2]:.6g}) "
                    f"max=({mx[0]:.6g},{mx[1]:.6g},{mx[2]:.6g}) "
                    f"[{self.model.domain_unit()}]")
        except OSError as exc:
            QMessageBox.critical(
                self, "Import",
                f"Parasolid kernel fault while importing:\n{exc}")
            self.log(f"Import failed: {exc}", "ERROR")
        except Exception as exc:
            QMessageBox.critical(self, "Import", str(exc))
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
            self, "Save As", "", "scSTREAM project (*.cab)")
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

    def _import_ifc_ecxml(self, path: str, ext: str) -> None:
        """File -> Import for .ifc / .ecxml: create parts directly."""
        try:
            raw = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.log(f"Import failed: {exc}", "WARN")
            return
        if ext == ".ifc":
            import cab_ifc
            try:
                solids = cab_ifc.parse_ifc(raw)
            except Exception as exc:
                QMessageBox.warning(self, "Import",
                                    f"IFC parse failed: {exc}")
                return
            names = cab_ifc.register_ifc_parts(
                self.model, solids, archive=self.archive)
            what = "IFC solid"
        else:
            import ecxml
            try:
                comps = ecxml.parse_ecxml(raw)
            except Exception as exc:
                QMessageBox.warning(self, "Import",
                                    f"ECXML parse failed: {exc}")
                return
            names = ecxml.register_ecxml_parts(self.model, comps)
            what = "ECXML component"
        if not names:
            QMessageBox.warning(self, "Import",
                                f"No {what} found in the file.")
            return
        self._mark_dirty()
        self._update_title()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self._rebuild_scene()
        self.log(f"Imported {len(names)} {what}(s) from "
                 f"{os.path.basename(path)}")

    def _export_dialog(self) -> None:
        if self.model is None or self.props is None:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "Export", self.model.project_name or "export",
            "S File (*.s);;XEMT File (*.xemt);;S + XEMT (*);;"
            "STL (*.stl);;Parasolid XT (*.x_t);;"
            "IFC Building (*.ifc);;ECXML Components (*.ecxml);;"
            "Property XML (*_property.xml);;All files (*)")
        if not path:
            return
        base, ext = os.path.splitext(path)
        if not ext:
            ext = ".s"
        wrote = []
        if "STL" in selected or ext.lower() == ".stl":
            out = base + ".stl"
            self._export_stl(out)
            wrote.append(out)
        elif "IFC" in selected or ext.lower() == ".ifc":
            out = base + ".ifc"
            import cab_ifc
            with open(out, "w", encoding="utf-8", newline="") as fh:
                fh.write(cab_ifc.model_to_ifc(self.model))
            wrote.append(out)
        elif "ECXML" in selected or ext.lower() == ".ecxml":
            out = base + ".ecxml"
            import ecxml
            with open(out, "w", encoding="utf-8", newline="") as fh:
                fh.write(ecxml.parts_to_ecxml(self.model))
            wrote.append(out)
        elif "Parasolid" in selected or ext.lower() == ".x_t":
            out = base + ".x_t"
            self._export_xt(out)
            wrote.append(out)
        elif "Property XML" in selected or "property.xml" in ext.lower() \
                or (ext.lower() == ".xml" and "Property" in selected):
            out = path if path.lower().endswith(".xml") else \
                (base + "_property.xml")
            if not out.lower().endswith("_property.xml") and \
                    not out.lower().endswith(".xml"):
                out = base + "_property.xml"
            raw = None
            if self.props is not None and hasattr(self.props.doc, "serialize"):
                raw = self.props.doc.serialize()
            elif self.archive is not None:
                for m in self.archive.members:
                    if m.name.endswith("_property.xml"):
                        raw = m.data
                        break
            if raw is None:
                raise RuntimeError("no property XML to export")
            with open(out, "wb") as fh:
                fh.write(raw)
            wrote.append(out)
        elif "XEMT" in selected and "S +" not in selected:
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

    def _export_stl(self, path: str) -> None:
        """M26: dump current CAD tessellations as binary STL."""
        import cab_import
        meshes = list(self._cad_meshes or [])
        if not meshes:
            raise RuntimeError("no tessellation to export")
        pts = []
        tris = []
        for m in meshes:
            off = len(pts)
            pts.extend(np.asarray(m.points).tolist())
            for t in np.asarray(m.triangles):
                tris.append([int(t[0]) + off, int(t[1]) + off,
                             int(t[2]) + off])
        raw = cab_import._tris_to_stl_bytes(
            np.asarray(pts), np.asarray(tris), Path(path).stem)
        with open(path, "wb") as fh:
            fh.write(raw)

    def _export_xt(self, path: str) -> None:
        """M26: export XT archive member (prefer first CAD .x_t payload)."""
        if self.archive is not None:
            for m in self.archive.members:
                if m.name.endswith(".x_t") and m.data:
                    Path(path).write_bytes(m.data)
                    return
        # Fallback: try pskernel transmit if session helpers expose tags
        try:
            import cab_ps_ops
            tags = getattr(self, "_ps_body_tags", None) or []
            if tags and cab_ps_ops.available():
                Path(path).write_bytes(cab_ps_ops.transmit_parts(list(tags)))
                return
        except Exception as exc:
            self.log(f"XT transmit fallback failed: {exc}", "WARN")
        raise RuntimeError("no .x_t member available to export")

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

    def _launch_program(self, exe: Optional[str], args: list[str],
                        cwd: Optional[str] = None) -> bool:
        if not exe:
            self.log("Program not found (Cradle CFD 2025.2).", "WARN")
            return False
        try:
            subprocess.Popen([exe] + args, cwd=cwd or None)
            self.log(f"Launched {os.path.basename(exe)}"
                     + (f" cwd={cwd}" if cwd else ""))
            return True
        except Exception as exc:
            self.log(f"Launch failed: {exc}", "ERROR")
            return False

    def _batch_execution(self) -> None:
        # File -> Batch Execution: sequential multi-project solver queue.
        if self.model is None:
            self.log('No project open.', 'WARN')
            return
        import cab_batch
        from cab_options import get_setting
        dlg = cab_batch.BatchExecutionDialog(
            self, find_exe=self._find_program,
            default_workdir=str(get_setting(
                'solver_workdir',
                os.path.dirname(self.current_path or '') or os.getcwd())))
        dlg.exec_()

    def _execute_solver(self) -> None:
        """M31 File -> Execute Solver: cwd / restart / env options."""
        if self.model is None or self.props is None:
            self.log("No project open.", "WARN")
            return
        from cab_options import get_setting, set_setting
        from PyQt5.QtWidgets import (
            QDialog, QFormLayout, QLineEdit, QCheckBox, QVBoxLayout,
            QPushButton, QHBoxLayout, QFileDialog as _FD,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Execute Solver")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        work = QLineEdit(str(get_setting(
            "solver_workdir",
            os.path.dirname(self.current_path or "") or os.getcwd())), dlg)
        envf = QLineEdit(str(get_setting("solver_env", "")), dlg)
        restart = QCheckBox("Restart from previous result", dlg)
        restart.setChecked(
            str(get_setting("solver_restart", "False")) == "True")
        form.addRow("Working directory", work)
        brow = QHBoxLayout()
        brow.addWidget(envf, 1)
        benv = QPushButton("…", dlg)
        benv.clicked.connect(lambda: envf.setText(
            _FD.getOpenFileName(dlg, "Solver env", "", "Env (*.env *.xenv);;All (*.*)")[0]
            or envf.text()))
        brow.addWidget(benv)
        form.addRow("Environment file", brow)
        form.addRow(restart)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton("Execute", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _run() -> None:
            set_setting("solver_workdir", work.text().strip())
            set_setting("solver_env", envf.text().strip())
            set_setting("solver_restart", restart.isChecked())
            sfile = self._export_temp_s_files()
            if sfile is None:
                self.log("Execute Solver: export failed.", "ERROR")
                return
            # R6: 同一时刻只允许一个求解进程, 运行中拒绝重复启动
            if self._solver_proc is not None \
                    and self._solver_proc.is_running():
                self.log("Execute Solver: solver already running; "
                         "start rejected.", "WARN")
                return
            exe = self._find_program(
                ["stsol_Dx64net.exe", "stsol_Sx64net.exe", "stsol.exe"])
            if exe is None:
                # 降级路径: 未找到 stsol, 保留导出的 S 文件供手动执行
                self.log("Program not found (Cradle CFD 2025.2).", "WARN")
                QMessageBox.warning(
                    self, "Execute Solver",
                    "未找到 stsol；S 文件已导出到:\n" + sfile)
                dlg.accept()
                return
            args = [sfile]
            if envf.text().strip():
                args += ["-env", envf.text().strip()]
            if restart.isChecked():
                args += ["-restart"]
            cwd = work.text().strip() or None
            if self._start_solver_monitor(exe, args, cwd, sfile):
                dlg.accept()
            # 启动失败时保留对话框供用户调整 (日志已记 ERROR)

        ok.clicked.connect(_run)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    # ------------------------------------------------- R6 solver monitoring

    def _start_solver_monitor(self, exe: str, args: list,
                              cwd: Optional[str], sfile: str) -> bool:
        """R6: 启动求解器并接管监控闭环 (日志 tail / 退出码 / 异常)。

        返回 False 表示启动失败 (FailedToStart 等, 已记 ERROR 日志)。
        """
        proc = SolverProcess()
        proc.output_line.connect(self._on_solver_output)
        proc.progress.connect(self._on_solver_progress)
        proc.success.connect(self._on_solver_success)
        proc.error.connect(self._on_solver_error)
        if not proc.start(exe, args, cwd):
            return False
        self._solver_proc = proc
        self.log(f"Execute Solver: {sfile} cwd={cwd}")
        self.statusBar().showMessage("Solver running…", 8000)
        return True

    def _on_solver_output(self, line: str) -> None:
        # 按行回显到 Message pane (其自身有 2000 行滚动上限, 不会刷爆)
        self.log(f"[solver] {line}")

    def _on_solver_progress(self, line: str) -> None:
        # 迭代/残差行: 额外刷新状态栏显示运行进度
        self.statusBar().showMessage(f"Solver: {line[:120]}", 8000)

    def _on_solver_success(self) -> None:
        self.log("Solver finished: exitCode=0 (success).")
        self.statusBar().showMessage("Solver finished: success", 8000)

    def _on_solver_error(self, exit_code: int, message: str) -> None:
        self.log(f"Solver failed: {message}", "ERROR")
        self.statusBar().showMessage(
            f"Solver failed (exit={exit_code})", 8000)

    def _shutdown_solver(self) -> None:
        """退出程序时停止仍在运行的求解器进程 (terminate -> kill)。"""
        proc = getattr(self, "_solver_proc", None)
        if proc is not None and proc.is_running():
            self.log("Closing: stopping solver process…", "WARN")
            proc.stop()

    def _execute_post(self) -> None:
        """M31 File -> Execute Post: open cab / field file."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        from cab_options import get_setting, set_setting
        from PyQt5.QtWidgets import (
            QDialog, QFormLayout, QLineEdit, QVBoxLayout, QPushButton,
            QHBoxLayout, QFileDialog as _FD,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Execute Post")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        field = QLineEdit(str(get_setting(
            "post_field", self.current_path or "")), dlg)
        brow = QHBoxLayout()
        brow.addWidget(field, 1)
        bb = QPushButton("…", dlg)
        bb.clicked.connect(lambda: field.setText(
            _FD.getOpenFileName(
                dlg, "Open field / cab", "",
                "Field/CAB (*.fld *.r *.cab);;All (*.*)")[0]
            or field.text()))
        brow.addWidget(bb)
        form.addRow("Field / project", brow)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton("Execute", dlg)
        cancel = QPushButton("Cancel", dlg)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        def _run() -> None:
            set_setting("post_field", field.text().strip())
            exe = self._find_program(
                ["scPOST_Dx64net.exe", "scPOST_Sx64net.exe", "scPOST.exe"])
            args = [field.text().strip()] if field.text().strip() else []
            if not self._launch_program(exe, args):
                QMessageBox.warning(
                    self, "Execute Post", "未找到 scPOST 后处理。")
            dlg.accept()

        ok.clicked.connect(_run)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def _wizard_initial(self) -> None:
        """Wizard → Initial Setting (also auto-shown on startup / File→New).

        User may Finish the 6-step setup, Open Existing Project (.cab), or
        Cancel to keep the current empty/default workspace.
        """
        if self.model is None or self.props is None:
            self.log("No project open.", "WARN")
            return
        import cab_wizards
        snap = self._snapshot()
        dlg = cab_wizards.InitialWizard(
            self.model, self.props, self._cad_meshes,
            archive=self.archive, parent=self)
        result = dlg.exec_()
        if result == cab_wizards.InitialWizard.RESULT_OPEN_EXISTING:
            path = getattr(dlg, "opened_existing_path", None)
            if path:
                if self.load(path):
                    self.log(f"Initial Setting: opened existing project "
                             f"{path}")
            return
        if result:
            # Sync CAD tessellations imported in the wizard (may have been
            # None on the viewer before Import CAD).
            meshes = getattr(dlg, "_cad_meshes", None)
            if meshes is not None:
                self._cad_meshes = list(meshes)
            self._hidden_parts.clear()
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
            self._ensure_sketch_plane(force_fit=True)
            self.control.load_sketch(self.model)
            self._rebuild_scene(fit=True)
            self.log("Initial Setting finished; save the cab to persist.")
        else:
            self.log("Initial Setting cancelled — default workspace kept.",
                     "INFO")

    def _domain_dialog(self) -> None:
        """[Edit Computational Domain] — tree Reference / double-click Domain.

        Menu [Edit]→[Reset Computational Domain] uses
        :meth:`_reset_domain_dialog` (different STpre dialog).
        """
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
        """Wizard -> Condition Setting: STpre Condition Wizard UI."""
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
        part = next((p for p in self.model.parts() if p.name == name), None)
        if part is not None and part.kind == "sketch":
            self._edit_sketch_part(name)
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
        """Regenerate primitive / sketch previews (replace same-name meshes)."""
        try:
            import cab_parts
            prim = cab_parts.primitives_from_model(self.model)
        except Exception:
            prim = []
        try:
            import cab_sketch
            sket = cab_sketch.sketch_parts_from_model(self.model)
        except Exception:
            sket = []
        extras = list(prim) + list(sket)
        if not extras:
            return
        by_name = {getattr(m, "name", None): m
                   for m in (self._cad_meshes or [])}
        for m in extras:
            by_name[getattr(m, "name", None)] = m
        self._cad_meshes = [m for k, m in by_name.items() if k]

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
                layer=spec.get("layer", "1"),
                monitor=spec.get("monitor"),
                virtual=spec.get("virtual")):
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
        extras = []
        if spec.get("params", {}).get("heat_source") is not None:
            extras.append(f"Q={spec['params']['heat_source']}")
        if spec["kind"] in ("peltier", "two_resistor", "plate_fin",
                            "pin_fin", "enclosure"):
            extras.append("thermal attrs")
        self.log(
            f"Created {spec['kind']} part '{spec['name']}' "
            f"(attribute={spec['attribute']}, material={spec['material']}"
            + ("; " + ", ".join(extras) if extras else "") + ")")

    def _sketch_part_dialog(self, edit_name: Optional[str] = None) -> None:
        """Part -> Sketch Part: non-modal so Draw Window can receive picks."""
        if self.model is None:
            self.log("No project open.", "WARN")
            return
        try:
            import cab_sketch
        except Exception:
            self.log("cab_sketch unavailable.", "ERROR")
            return
        existing = getattr(self, "_sketch_dlg", None)
        if existing is not None and existing.isVisible():
            if edit_name and getattr(existing, "edit_name", None) == edit_name:
                existing.raise_()
                existing.activateWindow()
                return
            existing.close()
        # Ensure sketch plane is visible for picking
        self._ensure_sketch_plane(force_fit=False)
        cb = self.control.layer_checks.get("sketch_plane")
        if cb is not None and not cb.isChecked():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self.control.load_sketch(self.model)
        self._rebuild_scene(fit=False)

        dlg = cab_sketch.SketchPartDialog(
            self.model, self.props, parent=self, edit_name=edit_name)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.accepted.connect(lambda: self._commit_sketch_part(dlg))
        dlg.rejected.connect(self._on_sketch_dialog_closed)
        dlg.finished.connect(lambda _r: self._on_sketch_dialog_closed())
        if getattr(dlg, "preview_requested", None) is not None:
            dlg.preview_requested.connect(self._preview_sketch_part)
        if getattr(dlg, "vertex_added", None) is not None:
            dlg.vertex_added.connect(
                lambda *_a: self._refresh_sketch_edit_overlay())
        # Table edits / Reset / Delete also refresh the Draw Window
        try:
            dlg.points_table.itemChanged.connect(
                lambda *_a: self._refresh_sketch_edit_overlay())
            dlg.btn_reset.clicked.connect(
                lambda: self._refresh_sketch_edit_overlay())
            dlg.btn_del.clicked.connect(
                lambda: self._refresh_sketch_edit_overlay())
            dlg.geometry_type.currentIndexChanged.connect(
                lambda *_a: self._refresh_sketch_edit_overlay())
            dlg.close_chk.toggled.connect(
                lambda *_a: self._refresh_sketch_edit_overlay())
        except Exception:
            pass
        self._sketch_dlg = dlg
        self._sketch_edit_actors = []
        dlg.show()
        self._refresh_sketch_edit_overlay()
        if edit_name:
            self.log(f"Edit Sketch Part '{edit_name}'.")
        else:
            self.log(
                "Sketch Part: click the sketch plane to add vertices "
                "(Point sequence), then OK.")

    def _edit_sketch_part(self, name: str) -> None:
        """Tree double-click / Refer → open Sketch Part definition dialog."""
        self._sketch_part_dialog(edit_name=name)

    def _on_sketch_dialog_closed(self) -> None:
        self._sketch_dlg = None
        self._clear_sketch_edit_overlay()
        if self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

    def _clear_sketch_edit_overlay(self) -> None:
        if self.renderer is None:
            self._sketch_edit_actors = []
            return
        for actor in getattr(self, "_sketch_edit_actors", []) or []:
            try:
                self.renderer.RemoveActor(actor)
            except Exception:
                pass
        self._sketch_edit_actors = []

    def _refresh_sketch_edit_overlay(self) -> None:
        """Draw current Sketch Part vertices/edges on the sketch plane."""
        if self.renderer is None:
            return
        self._clear_sketch_edit_overlay()
        dlg = getattr(self, "_sketch_dlg", None)
        if dlg is None or not dlg.isVisible():
            if self.vtk_widget is not None:
                self.vtk_widget.GetRenderWindow().Render()
            return
        try:
            import cab_vtk
            profile = dlg._profile()
            # Rectangle / Circle: show derived polygon; Point sequence: table
            uv = list(profile.polygon())
            if profile.geometry_type == "point_sequence":
                uv = list(profile.points)
                close = bool(profile.close)
            else:
                close = True
            actors = cab_vtk.sketch_profile_actors(
                dlg.plane, uv, close=close and len(uv) >= 3)
            for a in actors:
                self.renderer.AddActor(a)
                self._sketch_edit_actors.append(a)
        except Exception as exc:
            self.log(f"Sketch outline draw failed: {exc}", "WARN")
        if self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

    def _preview_sketch_part(self, spec: dict) -> None:
        """Live preview tessellation without committing the part."""
        try:
            import cab_sketch
        except Exception:
            return
        profile = spec.get("profile")
        if profile is None:
            return
        plane = cab_sketch.plane_from_xml(self.model)
        try:
            tess = cab_sketch.sketch_tess(
                plane, profile, spec.get("model_type", "extrusion"),
                float(spec.get("thickness", 5.0)))
        except Exception as exc:
            self.log(f"Sketch preview failed: {exc}", "WARN")
            return
        tess.name = (spec.get("name") or "preview") + "__preview"
        # Replace previous preview mesh
        meshes = [m for m in (self._cad_meshes or [])
                  if not str(getattr(m, "name", "")).endswith("__preview")]
        meshes.append(tess)
        self._cad_meshes = meshes
        self._rebuild_scene(fit=False)
        self._refresh_sketch_edit_overlay()
        self.log(f"Sketch preview: {len(profile.polygon())} outline pts")

    def _commit_sketch_part(self, dlg) -> None:
        """Finalize Sketch Part after non-modal OK (create or update)."""
        self._clear_sketch_edit_overlay()
        self._sketch_dlg = None
        if self.model is None:
            return
        try:
            import cab_sketch
        except Exception:
            self.log("cab_sketch unavailable.", "ERROR")
            return
        spec = dlg.spec()
        name = spec["name"]
        edit_name = getattr(dlg, "edit_name", None)
        if not name:
            self.log("Sketch Part: a part name is required.", "WARN")
            return
        if edit_name is None and self.model.find_part(name) is not None:
            QMessageBox.warning(
                self, "Sketch Part", f"Part '{name}' already exists.")
            return
        if edit_name and name != edit_name and \
                self.model.find_part(name) is not None:
            QMessageBox.warning(
                self, "Sketch Part", f"Part '{name}' already exists.")
            return
        if spec["profile"].geometry_type == "point_sequence":
            need = 3 if spec["profile"].close else 2
            n_unique = len(spec["profile"].points)
            if n_unique < need:
                QMessageBox.warning(
                    self, "Sketch Part",
                    "Point sequence needs >= 3 vertices (closed) "
                    "or >= 2 (open).")
                return
        snap = self._snapshot()
        plane = cab_sketch.plane_from_xml(self.model)
        common = dict(
            plane=plane, profile=spec["profile"],
            model_type=spec["model_type"],
            thickness_mm=spec["thickness"], material=spec["material"],
            attribute=spec["attribute"],
            color=spec.get("color", "120,160,220,255"),
            layer=spec.get("layer", "1"),
            orientation=spec.get("orientation", "W-Axis(Positive)"),
            scale_type=spec.get("scale_type", "Solid"),
            cutout_target=spec.get("cutout_target", ""),
            monitor=bool(spec.get("monitor", True)),
            virtual=bool(spec.get("virtual", False)),
            initial_temperature=spec.get("initial_temperature"),
            heat_source=spec.get("heat_source"),
            heat_source_unit=spec.get("heat_source_unit", "W"))
        if edit_name:
            ok = cab_sketch.update_sketch_part(
                self.model, name=edit_name, new_name=name, **common)
        else:
            ok = cab_sketch.register_sketch_part(
                self.model, name=name, **common)
        if not ok:
            self.log("Sketch Part: registration failed.", "ERROR")
            return
        tess = cab_sketch.sketch_tess(
            plane, spec["profile"], spec["model_type"], spec["thickness"])
        tess.name = name
        # Replace prior mesh for this part + drop temporary previews
        drop = {edit_name, name, None}
        meshes = [
            m for m in (self._cad_meshes or [])
            if not str(getattr(m, "name", "")).endswith("__preview")
            and getattr(m, "name", None) not in drop]
        meshes.append(tess)
        self._cad_meshes = meshes
        self._push_undo(snap)
        self._mark_dirty()
        self._update_title()
        self.tree_view.populate(
            self.model, self.archive.members if self.archive else [])
        self._rebuild_scene()
        verb = "Updated" if edit_name else "Created"
        self.log(
            f"{verb} sketch part '{name}' "
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
        self._shutdown_solver()  # R6: 退出前停止仍在运行的求解器
        self._close_stpre_session()
        super().closeEvent(event)

    def _run_stpre_api(self, action: str,
                       params: Optional[list] = None,
                       method: str = "detail",
                       block_params: Optional[list] = None,
                       grid_spec=None) -> str:
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
            if block_params is None and grid_spec is not None:
                block_params = cab_stpre_api.build_block_params_from_gridspec(
                    grid_spec)
            if block_params is None and action == "grid":
                block_params = cab_stpre_api.build_block_params_from_model(
                    self.model)
            if not cab_stpre_api.build_relay_cab(
                    self.model, self.archive, src, keep_mesh=keep_mesh,
                    block_params=block_params, grid_spec=grid_spec):
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
                if run_grid and not session.grid(
                        params, method, block_params=block_params):
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
            if action == "grid" or "mesh_block" in merged:
                self._enable_mesh_layer_after_gridding()
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
            block_params = cab_stpre_api.build_block_params_from_gridspec(
                spec)
            method = dict((p[0], p[1]) for p in params)[
                "division_method"]
            return self._run_stpre_api(
                "grid", params=params, method=method,
                block_params=block_params, grid_spec=spec) == "stpre"
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

            part_kinds = {p.name: p.kind for p in self.model.parts()}
            part_attrs = {p.name: p.attribute for p in self.model.parts()}
            coord = "cartesian"
            try:
                import cab_domain
                d = cab_domain.domain_from_xml(self.model)
                if d is not None and (d.coordinate or "").strip():
                    coord = d.coordinate.strip().lower()
            except Exception:
                pass

            def _mc(tag: str, default: float) -> float:
                try:
                    return float(self.model.mesh_control_value(tag)
                                 or default)
                except (TypeError, ValueError):
                    return default

            edge_eps = _mc("edge_eps", 0.0001)
            face_search = _mc("face_search", 1.0)
            elem_thr = _mc("element_threshold", 0.5)
            samples = ("corners" if (self.model.mesh_control_value("samples")
                                     or "").strip().lower() == "corners"
                       else "center")
            try:
                workers = max(1, int(
                    self.model.mesh_control_value("parallel_degree") or 1))
            except (TypeError, ValueError):
                workers = 1
            analysis_box, part_boxes = cab_mesh.classify_cells(
                axes, meshes, transforms=transforms, progress=tick,
                part_kinds=part_kinds, part_attrs=part_attrs,
                edge_eps=edge_eps, face_search=face_search,
                element_threshold=elem_thr, samples=samples,
                workers=workers, coordinate=coord)
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
        if (self.model.mesh_control_value("check_scheme") or "0") == "1":
            import cab_mesh
            dups = cab_mesh.find_flux_face_duplicates(self.model)
            if dups:
                self.log(
                    "Flux face duplication check: "
                    + "; ".join(f"{f}: {','.join(ns)}"
                                for f, ns in dups), "WARN")
            else:
                self.log("Flux face duplication check: none.", "INFO")
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
    # Install before QApplication so early Qt platform warnings (EUDC font,
    # off-screen geometry clamping) are filtered as well.
    _install_startup_message_filter()
    app = QApplication(argv or sys.argv)
    path = None
    args = argv if argv is not None else sys.argv
    if len(args) > 1 and os.path.isfile(args[1]):
        path = args[1]
    win = CabViewer(path)
    win.show()
    _clamp_to_visible_screen(win)
    # Interactor + first paint are deferred in showEvent/_finish_startup_view
    # (early Initialize here still races the native window on Windows).
    if win._enable_3d and win.model is not None:
        QTimer.singleShot(0, win._finish_startup_view)
    # STpre: Initial Wizard appears automatically when creating a new
    # session (not when opening a .cab from the command line).
    if getattr(win, "_offer_initial_wizard", False):
        QTimer.singleShot(100, win._wizard_initial)
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

"""STpre Initial Wizard pages (5-step flow aligned with Pre_eng + STpreIwiz)."""

from __future__ import annotations

import os
from typing import Optional

import cab_domain
import cab_import
from cab_dialogs import MaterialListDialog
from cabxml import StpreModel
from cab_wizard_icons import iwiz_atype_icon, purpose_icon

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt, QSize
    from PyQt5.QtGui import QPainter, QPen, QColor
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
        QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
        QRadioButton, QSizePolicy, QStackedWidget, QTabWidget, QTableWidget,
        QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
    )
    _HAS_GUI = True
except Exception:  # pragma: no cover
    _HAS_GUI = False
    QWidget = object  # type: ignore

_UNIT_FACTOR = {"mm": 1.0, "m": 1000.0, "cm": 10.0}
_CW_GRAVITY_DIRS = [
    ("X-Axis(Positive)", (1.0, 0.0, 0.0)),
    ("X-Axis(Negative)", (-1.0, 0.0, 0.0)),
    ("Y-Axis(Positive)", (0.0, 1.0, 0.0)),
    ("Y-Axis(Negative)", (0.0, -1.0, 0.0)),
    ("Z-Axis(Positive)", (0.0, 0.0, 1.0)),
    ("Z-Axis(Negative)", (0.0, 0.0, -1.0)),
    ("User-defined", None),
]

PURPOSE_LABELS = [
    ("No specification (Settings are considered in Condition Wizard)", "none"),
    ("Internal flow (enclosure heat release)", "internal_enclosure"),
    ("External flow (natural convection)", "external_natural"),
    ("External flow (forced convection)", "external_forced"),
    ("External flow (winds blowing through buildings)", "external_buildings"),
]

PURPOSE_BC = {
    "none": "Boundary conditions are set in the Condition Wizard.",
    "external_forced": (
        "Inflow side   : Fixed velocity condition\n"
        "Outflow side  : Static pressure condition\n"
        "Side faces    : Free slip + Adiabatic\n"
        "(writes flux/wall/heat_transfer values on Xmin/Xmax/Y±/Z± sides)"),
    "external_natural": (
        "Top face      : Natural outflow condition\n"
        "Bottom face   : Total pressure condition\n"
        "Side faces    : Free slip + Adiabatic"),
    "internal_enclosure": (
        "Top boundary  : Enclosure heat release (A=1.3 B=0.25 eps=0.9)\n"
        "Bottom boundary: Enclosure heat release (A=0.65 B=0.25 eps=0.9)\n"
        "Side boundary : Enclosure heat release (A=1.4 B=0.25 eps=0.9)\n"
        "(phase 1: informational only — not written to the cab)"),
    "external_buildings": (
        "Power-law inflow boundary on the inflow side.\n"
        "(phase 1: informational only — not written to the cab)"),
}


def _note(text: str, parent=None) -> QLabel:
    lab = QLabel(text, parent)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #555;")
    return lab


def _row(layout, label, widget, stretch=1):
    r = QHBoxLayout()
    r.addWidget(QLabel(label))
    r.addWidget(widget, stretch)
    layout.addLayout(r)


def _pair_row(layout, label, widget, unit=""):
    r = QHBoxLayout()
    r.addWidget(QLabel(label))
    r.addWidget(widget, 1)
    if unit:
        r.addWidget(QLabel(unit))
    r.addStretch(1)
    layout.addLayout(r)


def _stpre_user_roots() -> tuple[str, str]:
    """STpre-style Work / Library roots under the user Documents folder."""
    home = os.path.expanduser("~")
    for brand in ("STwin", "Stwin2025", "Stwin"):
        base = os.path.join(home, "Documents", "Cradle", brand)
        work = os.path.join(base, "Work")
        lib = os.path.join(base, "Library")
        if os.path.isdir(base) or os.path.isdir(work) or os.path.isdir(lib):
            return work, lib + ("" if lib.endswith(("\\", "/")) else os.sep)
    base = os.path.join(home, "Documents", "Cradle", "STwin")
    work = os.path.join(base, "Work")
    lib = os.path.join(base, "Library") + os.sep
    return work, lib


def _stpre_standard_files() -> tuple[str, str]:
    """Paths to standard_property_ENG.xml / standard_default_ENG.xml."""
    from cab_materials import standard_property_path
    prop = standard_property_path()
    prop_s = str(prop) if prop is not None else ""
    default_s = ""
    if prop is not None:
        cand = prop.with_name("standard_default_ENG.xml")
        if cand.is_file():
            default_s = str(cand)
        else:
            # Same Programs_x64 folder as property file
            sib = prop.parent / "standard_default_ENG.xml"
            if sib.is_file():
                default_s = str(sib)
    if not default_s:
        for p in (
                r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64"
                r"\standard_default_ENG.xml",
                os.path.join(os.path.dirname(__file__), "data",
                             "standard_default_ENG.xml")):
            if os.path.isfile(p):
                default_s = p
                break
    return prop_s, default_s


def _vec16(loc_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
           scale: float = 1.0) -> str:
    dx, dy, dz = loc_m
    return ",".join(f"{v:.17g}" for v in
                    (scale, 0, 0, 0,
                     0, scale, 0, 0,
                     0, 0, scale, 0,
                     dx, dy, dz, 1.0))


class _DomainWireframe(QWidget if _HAS_GUI else object):
    """Compact domain wireframe (STpre: beside Min/Max, not full-width)."""

    def __init__(self, owner: "_IwDomainPage"):
        super().__init__()
        self._owner = owner
        self.setFixedSize(120, 72)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("background: #fafafa; border: 1px solid #ccc;")

    def paintEvent(self, _event) -> None:
        if not _HAS_GUI:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        try:
            xmin = self._owner.spins["xmin"].value()
            xmax = self._owner.spins["xmax"].value()
            ymin = self._owner.spins["ymin"].value()
            ymax = self._owner.spins["ymax"].value()
            zmin = self._owner.spins["zmin"].value()
            zmax = self._owner.spins["zmax"].value()
        except Exception:
            xmin, xmax, ymin, ymax, zmin, zmax = -1, 1, -1, 1, -1, 1
        dx = max(abs(xmax - xmin), 1e-6)
        dy = max(abs(ymax - ymin), 1e-6)
        dz = max(abs(zmax - zmin), 1e-6)
        # Fit cube in the fixed tile with padding for axes badge.
        scale = min((w - 36) / dx, (h - 28) / max(dy, dz)) * 0.55
        cx, cy = w * 0.42, h * 0.58
        hw = dx * scale / 2
        hh = dy * scale / 2
        hd = dz * scale / 2
        pen = QPen(QColor(60, 110, 200), 1.4)
        p.setPen(pen)
        x0, y0 = cx - hw, cy - hh
        x1, y1 = cx + hw, cy + hh
        p.drawRect(int(x0), int(y0), int(max(2 * hw, 1)), int(max(2 * hh, 1)))
        off = max(hd * 0.45, 8.0)
        p.drawRect(int(x0 + off), int(y0 - off),
                   int(max(2 * hw, 1)), int(max(2 * hh, 1)))
        for fx, fy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            p.drawLine(int(fx), int(fy), int(fx + off), int(fy - off))
        # Small XYZ triad (STpre corner axes)
        ax, ay = w - 28, h - 14
        p.setPen(QPen(QColor(200, 60, 60), 1.5))
        p.drawLine(ax, ay, ax + 16, ay)
        p.setPen(QPen(QColor(40, 160, 60), 1.5))
        p.drawLine(ax, ay, ax, ay - 14)
        p.setPen(QPen(QColor(40, 90, 200), 1.5))
        p.drawLine(ax, ay, ax + 10, ay - 8)
        p.end()


class _IwProjectPage(QWidget if _HAS_GUI else object):
    """Project management + optional Import CAD Data."""

    def __init__(self, model: StpreModel, archive, cad_meshes):
        super().__init__()
        self.model = model
        self.archive = archive
        # Shared list with InitialWizard / Domain page (never None).
        self.cad_meshes = cad_meshes if cad_meshes is not None else []
        self._entries: list[tuple[str, bytes, list]] = []
        self._config: dict[int, tuple[tuple[float, float, float], float]] = {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Sets project name.", self))
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        brow = QHBoxLayout()
        self.btn_new = QPushButton("New", self)
        brow.addWidget(self.btn_new)
        brow.addWidget(QLabel("Creates a new project.", self))
        brow.addStretch(1)
        root.addLayout(brow)
        orow = QHBoxLayout()
        self.btn_open = QPushButton("Open Existing Project...", self)
        self.btn_open.clicked.connect(self._open_project)
        orow.addWidget(self.btn_open)
        orow.addWidget(QLabel("Reads a project file.", self))
        orow.addStretch(1)
        root.addLayout(orow)

        work_def, lib_def = _stpre_user_roots()
        prop_def, default_def = _stpre_standard_files()

        pname = (model.project_name or "").strip() or "Untitled"
        self.name = QLineEdit(pname, self)
        _row(root, "Project name", self.name)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Path to save files", self))
        self.path = QLineEdit(
            model.project_value("save_path") or work_def, self)
        path_row.addWidget(self.path, 1)
        btn_path = QPushButton("...", self)
        btn_path.setFixedWidth(28)
        btn_path.clicked.connect(self._pick_path)
        path_row.addWidget(btn_path)
        root.addLayout(path_row)

        self.create_folder = QCheckBox(
            "Create project folder under the above directory", self)
        # STpre new-project default: unchecked
        cf = model.project_value("create_folder", "")
        self.create_folder.setChecked(cf == "1")
        root.addWidget(self.create_folder)

        lib_row = QHBoxLayout()
        lib_row.addWidget(QLabel("Library", self))
        self.library = QLineEdit(
            model.project_value("library") or lib_def, self)
        lib_row.addWidget(self.library, 1)
        btn_lib = QPushButton("...", self)
        btn_lib.setFixedWidth(28)
        btn_lib.clicked.connect(self._pick_library)
        lib_row.addWidget(btn_lib)
        root.addLayout(lib_row)

        prop_row = QHBoxLayout()
        prop_row.addWidget(QLabel("Property file", self))
        self.property_file = QLineEdit(
            model.project_value("property_file") or prop_def, self)
        prop_row.addWidget(self.property_file, 1)
        btn_prop = QPushButton("...", self)
        btn_prop.setFixedWidth(28)
        btn_prop.clicked.connect(self._pick_property)
        prop_row.addWidget(btn_prop)
        root.addLayout(prop_row)

        def_row = QHBoxLayout()
        self.default_chk = QCheckBox("Default file", self)
        # STpre: Default file is on for a new project
        self.default_chk.setChecked(True)
        self.default_path = QLineEdit(
            model.project_value("default_file") or default_def, self)
        btn_def = QPushButton("...", self)
        btn_def.setFixedWidth(28)
        btn_def.clicked.connect(self._pick_default_file)
        def_row.addWidget(self.default_chk)
        def_row.addWidget(self.default_path, 1)
        def_row.addWidget(btn_def)
        root.addLayout(def_row)
        self.default_chk.toggled.connect(self.default_path.setEnabled)
        self.default_path.setEnabled(self.default_chk.isChecked())

        comment = (model.project_value("comment") or "").strip()
        self.comment = QLineEdit(comment or "project no.1", self)
        _row(root, "Comments", self.comment)

        self.import_cad = QCheckBox("Import CAD data", self)
        self.import_cad.toggled.connect(self._toggle_cad)
        root.addWidget(self.import_cad)

        self.cad_panel = QWidget(self)
        cp = QVBoxLayout(self.cad_panel)
        cp.setContentsMargins(0, 0, 0, 0)
        self.cad_table = QTableWidget(0, 6, self.cad_panel)
        self.cad_table.setHorizontalHeaderLabels(
            ["No", "CAD file name", "Scale", "Location", "Min", "Max"])
        self.cad_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        cp.addWidget(self.cad_table, 1)
        cad_btns = QHBoxLayout()
        self.btn_read = QPushButton("Read From File...", self.cad_panel)
        self.btn_read.clicked.connect(self._read)
        self.btn_remove = QPushButton("Remove", self.cad_panel)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_configure = QPushButton("Configure", self.cad_panel)
        self.btn_configure.clicked.connect(self._configure)
        for b in (self.btn_read, self.btn_remove, self.btn_configure):
            cad_btns.addWidget(b)
        cad_btns.addStretch(1)
        cp.addLayout(cad_btns)
        cp.addWidget(_note(
            "XT files are imported as new parts and cab members on Finish. "
            "Configure sets Location (mm) and Scale.", self.cad_panel))
        root.addWidget(self.cad_panel)
        self.cad_panel.hide()
        root.addStretch(1)

    def _toggle_cad(self, on: bool) -> None:
        self.cad_panel.setVisible(on)

    def _pick_path(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Path to save files", self.path.text() or "")
        if d:
            self.path.setText(d)

    def _pick_library(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Library", self.library.text() or "")
        if d:
            if not d.endswith(("\\", "/")):
                d += os.sep
            self.library.setText(d)

    def _pick_property(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Property file", self.property_file.text() or "",
            "Property XML (*.xml);;All files (*)")
        if path:
            self.property_file.setText(path)

    def _pick_default_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Default file", self.default_path.text() or "",
            "Default XML (*.xml);;All files (*)")
        if path:
            self.default_path.setText(path)
            self.default_chk.setChecked(True)

    def _open_project(self) -> None:
        start = self.path.text().strip() or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Existing Project", start,
            "scSTREAM project (*.cab);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".cab"):
            QMessageBox.warning(
                self, "Open Existing Project",
                "Please select a .cab project file.")
            return
        wiz = self.parent()
        while wiz is not None and not hasattr(wiz, "open_existing_project"):
            wiz = wiz.parent()
        if wiz is None:
            self._log(f"Initial Wizard: cannot open project — {path}",
                      "WARN")
            return
        wiz.open_existing_project(path)

    def _read(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import CAD Data", "", "Parasolid XT (*.x_t *.xmt_txt);;"
                                         "All files (*)")
        if not path:
            return
        if not cab_import.available():
            QMessageBox.warning(
                self, "Import CAD Data",
                "Cradle pskernel.dll not found — cannot read the x_t file.")
            return
        bodies = cab_import.import_xt_file(path)
        if not bodies:
            QMessageBox.warning(self, "Import CAD Data",
                                "No drawable body in the file.")
            return
        with open(path, "rb") as fh:
            raw = fh.read()
        self._entries.append((path, raw, bodies))
        row = self.cad_table.rowCount()
        self.cad_table.insertRow(row)
        self.cad_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.cad_table.setItem(row, 1,
                               QTableWidgetItem(os.path.basename(path)))
        self.cad_table.setItem(row, 2, QTableWidgetItem("1"))
        self.cad_table.setItem(row, 3, QTableWidgetItem("0,0,0"))
        self.cad_table.setItem(row, 4, QTableWidgetItem("-"))
        self.cad_table.setItem(row, 5, QTableWidgetItem("-"))

    def _remove(self) -> None:
        row = self.cad_table.currentRow()
        if row < 0:
            return
        self.cad_table.removeRow(row)
        self._entries.pop(row)
        for i in range(self.cad_table.rowCount()):
            it = self.cad_table.item(i, 0)
            if it is not None:
                it.setText(str(i + 1))

    def _configure(self) -> None:
        row = self.cad_table.currentRow()
        if row < 0 or row >= len(self._entries):
            QMessageBox.information(self, "Configure",
                                    "Select a CAD component first.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Configure position/scale")
        lay = QVBoxLayout(dlg)
        loc = {a: QDoubleSpinBox() for a in "xyz"}
        for a in "xyz":
            loc[a].setRange(-1.0e9, 1.0e9)
            loc[a].setDecimals(3)
            _row(lay, f"Location {a.upper()} (mm)", loc[a])
        scale = QDoubleSpinBox()
        scale.setRange(1.0e-6, 1.0e6)
        scale.setValue(1.0)
        scale.setDecimals(4)
        _row(lay, "Scale conversion from CAD scale", scale)
        row_b = QHBoxLayout()
        row_b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        row_b.addWidget(ok)
        row_b.addWidget(cancel)
        lay.addLayout(row_b)
        if dlg.exec_():
            loc_mm = tuple(loc[a].value() for a in "xyz")
            self._config[row] = (
                tuple(v / 1000.0 for v in loc_mm), scale.value())
            self.cad_table.setItem(
                row, 2, QTableWidgetItem(f"{scale.value():g}"))
            self.cad_table.setItem(
                row, 3, QTableWidgetItem(
                    ",".join(f"{v:g}" for v in loc_mm)))

    def apply_to_model(self) -> None:
        if not self.import_cad.isChecked():
            return
        added: list[str] = []
        for raw in {e[1] for e in self._entries}:
            if self.archive is not None:
                member = cab_import.add_xt_member(self.archive, raw)
                self.model.add_body_file(member.name)
        if self.cad_meshes is None:
            self.cad_meshes = []
        for _path, _raw, bodies in self._entries:
            added += cab_import.register_parts(self.model, bodies)
            for b in bodies:
                if b.tess is not None:
                    self.cad_meshes.append(b.tess)
        for row, (loc, scale) in self._config.items():
            if 0 <= row < len(self._entries):
                bodies = self._entries[row][2]
                if bodies:
                    self.model.set_part_transform(
                        bodies[0].name, _vec16(loc, scale))
        self._log(f"Initial Wizard: imported {len(self._entries)} file(s) "
                  f"-> {', '.join(added) or '(duplicates)'}")

    def apply_project_fields(self) -> None:
        self.model.set_project_name(self.name.text().strip() or "Untitled")
        self.model.set_project_value("comment", self.comment.text().strip())
        self.model.set_project_value("save_path", self.path.text().strip())
        self.model.set_project_value(
            "create_folder", "1" if self.create_folder.isChecked() else "0")
        self.model.set_project_value("library", self.library.text().strip())
        self.model.set_project_value(
            "property_file", self.property_file.text().strip())
        if self.default_chk.isChecked():
            self.model.set_project_value(
                "default_file", self.default_path.text().strip())
        else:
            self.model.set_project_value("default_file", "")

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)


class _IwDomainPage(QWidget if _HAS_GUI else object):
    def __init__(self, model: StpreModel, props, cad_meshes):
        super().__init__()
        self.model = model
        self.props = props
        self.cad_meshes = cad_meshes if cad_meshes is not None else []
        spec = cab_domain.domain_from_xml(model) or cab_domain.DomainSpec()
        self.spec = spec
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Sets coordinate system, unit, and computational domain.", self))
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        coord = QHBoxLayout()
        coord.addWidget(QLabel("Coordinate system", self))
        self.coordinate = QComboBox(self)
        self.coordinate.addItems(
            ["Cartesian coordinate", "Cylindrical coordinate",
             "Axial symmetry"])
        coord.addWidget(self.coordinate, 1)
        lay.addLayout(coord)

        urow = QHBoxLayout()
        urow.addWidget(QLabel("Coordinate value unit (display only)", self))
        self.unit = QComboBox(self)
        self.unit.addItems(["mm", "m", "cm"])
        self.unit.setMaximumWidth(80)
        urow.addWidget(self.unit)
        urow.addWidget(QLabel("Note) S file is output in meters.", self))
        urow.addStretch(1)
        lay.addLayout(urow)

        # Rectangular box + CAD Data Size (STpre row)
        cad_row = QHBoxLayout()
        cad_row.addWidget(QLabel("Rectangular box subdomain", self))
        self.btn_cad = QPushButton("CAD Data Size", self)
        self.btn_cad.clicked.connect(self._cad_size)
        cad_row.addWidget(self.btn_cad)
        cad_row.addStretch(1)
        lay.addLayout(cad_row)

        # One grid: Min/Max spins | Preview + wireframe on the right
        # (STpre: cube sits beside Minimum/Maximum value, not a full row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, ax in enumerate("xyz"):
            lab = QLabel(ax.upper(), self)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 0, i + 1)
        grid.addWidget(QLabel("Minimum value", self), 1, 0)
        grid.addWidget(QLabel("Maximum value", self), 2, 0)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            for row, side in ((1, "min"), (2, "max")):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1.0e9, 1.0e9)
                sb.setDecimals(3)
                sb.setMaximumWidth(96)
                sb.valueChanged.connect(self._refresh_wireframe)
                grid.addWidget(sb, row, i + 1)
                self.spins[f"{ax}{side}"] = sb

        self.btn_preview = QPushButton("Preview", self)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_preview.setFixedWidth(72)
        grid.addWidget(self.btn_preview, 0, 4, Qt.AlignLeft | Qt.AlignVCenter)

        self.wireframe = _DomainWireframe(self)
        # Span Minimum + Maximum rows, top-aligned to the right of spins
        grid.addWidget(self.wireframe, 1, 4, 2, 1,
                       Qt.AlignLeft | Qt.AlignTop)
        grid.setColumnStretch(5, 1)
        lay.addLayout(grid)

        self.extend_chk = QCheckBox("Extend surroundings", self)
        self.extend_chk.toggled.connect(self._toggle_extend)
        lay.addWidget(self.extend_chk)
        ext_grid = QGridLayout()
        ext_grid.setHorizontalSpacing(6)
        for i, ax in enumerate("xyz"):
            lab = QLabel(ax.upper(), self)
            lab.setAlignment(Qt.AlignCenter)
            ext_grid.addWidget(lab, 0, i + 1)
        ext_grid.addWidget(QLabel("Minimum side", self), 1, 0)
        ext_grid.addWidget(QLabel("Maximum side", self), 2, 0)
        self.extend_min: dict[str, QDoubleSpinBox] = {}
        self.extend_max: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            for row, store in ((1, self.extend_min), (2, self.extend_max)):
                sb = QDoubleSpinBox(self)
                sb.setRange(0.0, 1.0e9)
                sb.setDecimals(3)
                sb.setMaximumWidth(96)
                sb.setEnabled(False)
                ext_grid.addWidget(sb, row, i + 1)
                store[ax] = sb
        lay.addLayout(ext_grid)

        mat_row = QHBoxLayout()
        mat_row.addWidget(QLabel("Material of computational domain", self))
        self.material = QLineEdit(self)
        self.material.setReadOnly(True)
        mat_row.addWidget(self.material, 1)
        self.btn_mat = QPushButton("Configure...", self)
        self.btn_mat.clicked.connect(self._pick_material)
        mat_row.addWidget(self.btn_mat)
        lay.addLayout(mat_row)
        self.mat_label = QLabel("< Incompressible fluid >", self)
        self.mat_label.setStyleSheet("color: #555; margin-left: 8px;")
        lay.addWidget(self.mat_label)

        self.sketch_grid = QCheckBox(
            "Grid of the sketch plane is automatically adjusted", self)
        self.sketch_grid.setChecked(True)
        lay.addWidget(self.sketch_grid)

        iu_row = QHBoxLayout()
        iu_row.addWidget(QLabel("Save geometry data internally in", self))
        self.internal_unit = QComboBox(self)
        self.internal_unit.addItems(["m", "mm", "cm"])
        self.internal_unit.setMaximumWidth(72)
        iu_row.addWidget(self.internal_unit)
        iu_row.addStretch(1)
        lay.addLayout(iu_row)
        lay.addStretch(1)
        self._load()

    def _toggle_extend(self, on: bool) -> None:
        for sb in list(self.extend_min.values()) + list(self.extend_max.values()):
            sb.setEnabled(on)

    def _refresh_wireframe(self, *_a) -> None:
        self.wireframe.update()

    def _load(self) -> None:
        spec = self.spec
        self.unit.setCurrentText(spec.unit if spec.unit in _UNIT_FACTOR
                                 else "mm")
        self.internal_unit.setCurrentText(self.unit.currentText())
        self.material.setText(spec.material)
        for i, ax in enumerate("xyz"):
            self.spins[f"{ax}min"].setValue(spec.xyz_min[i])
            self.spins[f"{ax}max"].setValue(spec.xyz_max[i])
            self.extend_min[ax].setValue(spec.extend_min[i])
            self.extend_max[ax].setValue(spec.extend_max[i])

    def _pick_material(self) -> None:
        dlg = MaterialListDialog(self.props, self,
                                 current=self.material.text())
        if dlg.exec_() and dlg.selected_material():
            self.material.setText(dlg.selected_material())

    def _cad_size(self) -> None:
        import numpy as np
        lo, hi = cab_domain.part_bounds(self.model, self.cad_meshes)
        if not np.isfinite(lo).all():
            self._log("CAD Data Size: no tessellated parts.", "WARN")
            return
        unit = self.unit.currentText()
        scale = 1000.0 / _UNIT_FACTOR.get(unit, 1.0)
        for i, ax in enumerate("xyz"):
            self.spins[f"{ax}min"].setValue(lo[i] * scale)
            self.spins[f"{ax}max"].setValue(hi[i] * scale)

    def _current_spec(self) -> cab_domain.DomainSpec:
        unit = self.unit.currentText()
        coord = ("cylindrical" if self.coordinate.currentIndex() == 1
                 else "axial" if self.coordinate.currentIndex() == 2
                 else "cartesian")
        return cab_domain.DomainSpec(
            coordinate=coord, unit=unit,
            xyz_min=tuple(self.spins[f"{ax}min"].value() for ax in "xyz"),
            xyz_max=tuple(self.spins[f"{ax}max"].value() for ax in "xyz"),
            extend_min=tuple(self.extend_min[a].value() for a in "xyz"),
            extend_max=tuple(self.extend_max[a].value() for a in "xyz"),
            material=self.material.text().strip(),
            name=self.model.domain_name() or "Domain(cuboid)",
            color=self.model.domain_color() or (0, 255, 255, 255),
        )

    def _preview(self) -> None:
        cab_domain.apply_domain(self.model, self._current_spec())
        self._rebuild()
        self._log("Initial Wizard: computational domain preview.")

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)

    def _rebuild(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()


class _IwInitialGravityPage(QWidget if _HAS_GUI else object):
    """Initial Value/Gravity step (STpre Initial Wizard)."""

    _UNDEF_TEXT = (
        "*Wall (Computational domain boundary/Face of part)\n"
        "    Consider wall resistance\n"
        "*Heat transfer (Computational domain boundary "
        "including face of obstacle)\n"
        "    Adiabatic\n"
        "*Boundary between fluid and solid\n"
        "    Heat transfer\n"
        "*Boundary between solid and solid\n"
        "    Heat transfer\n"
        "*Radiation boundary\n"
        "    Default emissivity"
    )

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Sets default value of heat and gravity in Initial Wizard.", self))
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        body = QHBoxLayout()
        left = QVBoxLayout()

        g = QGroupBox("Heat", self)
        gl = QVBoxLayout(g)
        self.temp_unit = QComboBox(g)
        self.temp_unit.addItems(["C", "K", "F", "R"])
        self.temp_unit.currentTextChanged.connect(self._sync_temp_units)
        _pair_row(gl, "Unit of reference temperature", self.temp_unit)
        self.temp_default = QDoubleSpinBox(g)
        self.temp_default.setRange(-273.15, 1.0e6)
        self.temp_default.setDecimals(2)
        self._temp_unit_lab = QLabel("C", g)
        tr = QHBoxLayout()
        tr.addWidget(QLabel("Default value of temperature", g))
        tr.addWidget(self.temp_default, 1)
        tr.addWidget(self._temp_unit_lab)
        gl.addLayout(tr)
        srow = QHBoxLayout()
        self.solid_chk = QCheckBox("Initial temperature of solid", g)
        self.solid_chk.setChecked(True)
        self.solid_temp = QDoubleSpinBox(g)
        self.solid_temp.setRange(-273.15, 1.0e6)
        self.solid_temp.setDecimals(2)
        self._solid_unit_lab = QLabel("C", g)
        srow.addWidget(self.solid_chk)
        srow.addWidget(self.solid_temp, 1)
        srow.addWidget(self._solid_unit_lab)
        gl.addLayout(srow)
        self.solid_chk.toggled.connect(self.solid_temp.setEnabled)
        self.emissivity = QDoubleSpinBox(g)
        self.emissivity.setRange(0.0, 1.0)
        self.emissivity.setDecimals(2)
        self.emissivity.setSingleStep(0.1)
        _pair_row(gl, "Default value of emissivity", self.emissivity)
        left.addWidget(g)

        gg = QGroupBox("Gravity", self)
        ggl = QVBoxLayout(gg)
        arow = QHBoxLayout()
        arow.addWidget(QLabel("Acceleration due to gravity", gg))
        self.gravity_acc = QDoubleSpinBox(gg)
        self.gravity_acc.setRange(0.0, 1000.0)
        self.gravity_acc.setDecimals(2)
        arow.addWidget(self.gravity_acc, 1)
        self.gravity_unit = QComboBox(gg)
        self.gravity_unit.addItems(["m/s2", "mm/s2", "cm/s2", "ft/s2"])
        arow.addWidget(self.gravity_unit)
        ggl.addLayout(arow)
        dirrow = QHBoxLayout()
        dirrow.addWidget(QLabel("Direction of gravity", gg))
        self.gravity_dir = QComboBox(gg)
        for label, _v in _CW_GRAVITY_DIRS:
            self.gravity_dir.addItem(label)
        dirrow.addWidget(self.gravity_dir, 1)
        ggl.addLayout(dirrow)
        crow = QHBoxLayout()
        self.grav_comp: dict[str, QDoubleSpinBox] = {}
        for ax in "XYZ":
            crow.addWidget(QLabel(ax, gg))
            sb = QDoubleSpinBox(gg)
            sb.setRange(-1.0e6, 1.0e6)
            sb.setDecimals(4)
            sb.setMaximumWidth(72)
            self.grav_comp[ax.lower()] = sb
            crow.addWidget(sb)
        crow.addStretch(1)
        ggl.addLayout(crow)
        self.gravity_dir.currentIndexChanged.connect(self._on_grav_dir)
        for sb in self.grav_comp.values():
            sb.valueChanged.connect(self._on_grav_comp_edited)
        self.gravity_chk = QCheckBox(self)
        self.gravity_chk.setChecked(True)
        self.gravity_chk.hide()
        left.addWidget(gg)
        left.addStretch(1)
        body.addLayout(left, 1)

        ug = QGroupBox("Undefined region", self)
        ul = QVBoxLayout(ug)
        self.undef_chk = QCheckBox(
            "Set the following conditions for undefined region", ug)
        self.undef_chk.setChecked(True)
        ul.addWidget(self.undef_chk)
        self.undef_text = QLabel(self._UNDEF_TEXT, ug)
        self.undef_text.setWordWrap(True)
        self.undef_text.setStyleSheet(
            "color: #333; background: #f7f7f7; padding: 6px; "
            "border: 1px solid #ddd;")
        ul.addWidget(self.undef_text, 1)
        body.addWidget(ug, 1)
        root.addLayout(body, 1)

        self.btn_reset = QPushButton(
            "Reset Conditions for Computational Domain Boundary", self)
        self.btn_reset.clicked.connect(self._reset_domain_bc)
        root.addWidget(self.btn_reset)
        root.addWidget(_note(
            "Note) Clicking this button deletes all condition on "
            "computational domain boundary.", self))
        self._load()

    def _sync_temp_units(self, unit: str) -> None:
        self._temp_unit_lab.setText(unit or "C")
        self._solid_unit_lab.setText(unit or "C")

    def _on_grav_dir(self, _idx: int = 0) -> None:
        _label, vec = _CW_GRAVITY_DIRS[self.gravity_dir.currentIndex()]
        if vec is None:
            return
        for ax, sb in self.grav_comp.items():
            sb.blockSignals(True)
            sb.setValue({"x": vec[0], "y": vec[1], "z": vec[2]}[ax])
            sb.blockSignals(False)

    def _on_grav_comp_edited(self, *_a) -> None:
        vec = tuple(self.grav_comp[a].value() for a in "xyz")
        for i, (_lab, v) in enumerate(_CW_GRAVITY_DIRS):
            if v is not None and v == vec:
                self.gravity_dir.blockSignals(True)
                self.gravity_dir.setCurrentIndex(i)
                self.gravity_dir.blockSignals(False)
                return
        self.gravity_dir.blockSignals(True)
        self.gravity_dir.setCurrentIndex(len(_CW_GRAVITY_DIRS) - 1)
        self.gravity_dir.blockSignals(False)

    def _grav_vec(self) -> tuple[float, float, float]:
        _lab, vec = _CW_GRAVITY_DIRS[self.gravity_dir.currentIndex()]
        if vec is not None:
            return vec
        return tuple(self.grav_comp[a].value() for a in "xyz")  # type: ignore

    def _reset_domain_bc(self) -> None:
        from cabxml import _first, DOMAIN_FACE_NAMES
        faces = set(DOMAIN_FACE_NAMES)
        removed = 0
        for c in list(self.model.conditions()):
            t = _first(c, "region")
            if t is None:
                continue
            if (t.text or "").strip() in faces:
                self.model.root.remove(c)
                removed += 1
        QMessageBox.information(
            self, "Reset Conditions for Computational Domain Boundary",
            f"Removed {removed} condition(s) on computational "
            f"domain boundaries.")

    def _load(self) -> None:
        unit = self.model.units.get("temperature", "C") or "C"
        if unit in ("C", "K", "F", "R"):
            self.temp_unit.setCurrentText(unit)
        try:
            ambient = float(self.model.project_value(
                "ambient_temperature", "20"))
        except ValueError:
            ambient = 20.0
        self.temp_default.setValue(ambient)
        try:
            solid = float(self.model.project_value(
                "solid_init_temperature", "20"))
        except ValueError:
            solid = 20.0
        self.solid_temp.setValue(solid)
        try:
            self.emissivity.setValue(float(
                self.model.project_value("default_emissivity", "0.9")))
        except ValueError:
            self.emissivity.setValue(0.9)
        try:
            self.gravity_acc.setValue(float(
                self.model.analysis_set_value("grav_abs", "9.8")))
        except ValueError:
            self.gravity_acc.setValue(9.8)
        grav = self.model.analysis_set_value("grav_vec", "0,0,-1").split(",")
        try:
            vec = (float(grav[0]), float(grav[1]), float(grav[2]))
        except (ValueError, IndexError):
            vec = (0.0, 0.0, -1.0)
        matched = False
        for i, (_label, v) in enumerate(_CW_GRAVITY_DIRS):
            if v is not None and v == vec:
                self.gravity_dir.setCurrentIndex(i)
                matched = True
                break
        if not matched:
            self.gravity_dir.setCurrentIndex(len(_CW_GRAVITY_DIRS) - 1)
            for ax, val in zip("xyz", vec):
                self.grav_comp[ax].setValue(val)
        else:
            self._on_grav_dir()
        self._sync_temp_units(self.temp_unit.currentText())

    def apply(self) -> None:
        from cabxml import _first
        self.model.set_project_value(
            "ambient_temperature", f"{self.temp_default.value():g}")
        if self.solid_chk.isChecked():
            self.model.set_project_value(
                "solid_init_temperature", f"{self.solid_temp.value():g}")
        self.model.set_project_value(
            "default_emissivity", f"{self.emissivity.value():g}")
        unit_root = _first(self.model.root, "unit")
        if unit_root is not None:
            tel = _first(unit_root, "temperature")
            if tel is not None:
                tel.text = f" {self.temp_unit.currentText()} "
        self.model.set_gravity(self.gravity_acc.value(), self._grav_vec())
        self.model.set_project_value(
            "undef_region_defaults",
            "1" if self.undef_chk.isChecked() else "0")


class _IwAnalysisTypePage(QWidget if _HAS_GUI else object):
    """Analysis Type step (STpre Initial Wizard) with schematic toggles."""

    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        al = QVBoxLayout(self)
        al.addWidget(QLabel("Sets analysis type.", self))
        sep_at = QFrame(self)
        sep_at.setFrameShape(QFrame.HLine)
        sep_at.setFrameShadow(QFrame.Sunken)
        al.addWidget(sep_at)
        al.addWidget(QLabel("Fluid type", self))
        al.addWidget(_note("Solves incompressible fluid.", self))

        cols = QHBoxLayout()
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()

        flow_g = QGroupBox("Flow analysis", self)
        fl = QVBoxLayout(flow_g)
        self.flow_solve = QComboBox(self)
        self.flow_solve.addItems(["Solve", "Do not solve"])
        self.flow_solve.hide()
        self.flow_solve_yes, self.flow_solve_no = self._pair_toggles(
            fl, "Solve", "Do not solve",
            lambda i: self._set_combo(self.flow_solve, i),
            "flow_solve", "flow_nosolve")
        ft_g = QGroupBox("Flow type", self)
        ftl = QVBoxLayout(ft_g)
        self.flow_type = QComboBox(self)
        self.flow_type.addItems(["Laminar flow", "Turbulent flow"])
        self.flow_type.hide()
        self._flow_type_btns = self._pair_toggles(
            ftl, "Laminar flow", "Turbulent flow",
            lambda i: self._set_combo(self.flow_type, i),
            "laminar", "turbulent")
        tm_row = QHBoxLayout()
        tm_row.addWidget(QLabel("Turbulence model", ft_g))
        self.turb_model = QComboBox(ft_g)
        self.turb_model.addItems([
            "Standard k-eps model", "RNG k-eps model", "MP k-eps model",
            "Linear low-Re model", "Non-linear low-Re model",
            "Improved LK k-eps model", "LES"])
        tm_row.addWidget(self.turb_model, 1)
        ftl.addLayout(tm_row)
        left_col.addWidget(flow_g)
        left_col.addWidget(ft_g)
        left_col.addStretch(1)

        heat_g = QGroupBox("Heat", self)
        hl = QVBoxLayout(heat_g)
        self.heat_solve = QComboBox(self)
        self.heat_solve.addItems(["Solve", "Do not solve"])
        self.heat_solve.hide()
        self._heat_btns = self._pair_toggles(
            hl, "Solve", "Do not solve",
            lambda i: self._set_combo(self.heat_solve, i),
            "heat_solve", "heat_nosolve")
        rad_g = QGroupBox("Radiation", self)
        rl = QVBoxLayout(rad_g)
        self.radiation = QComboBox(self)
        self.radiation.addItems(["Ignore", "Consider"])
        self.radiation.hide()
        self._rad_btns = self._pair_toggles(
            rl, "Consider", "Ignore",
            lambda i: self._set_combo(
                self.radiation, 1 if i == 0 else 0),
            "rad_consider", "rad_ignore")
        sol_g = QGroupBox("Solar radiation", self)
        sl = QVBoxLayout(sol_g)
        self.solar = QComboBox(self)
        self.solar.addItems(["Ignore", "Consider"])
        self.solar.hide()
        self._solar_btns = self._pair_toggles(
            sl, "Consider", "Ignore",
            lambda i: self._set_combo(self.solar, 1 if i == 0 else 0),
            "solar_consider", "solar_ignore")
        right_col.addWidget(heat_g)
        right_col.addWidget(rad_g)
        right_col.addWidget(sol_g)
        self.high_speed = QCheckBox("High-speed calculation", self)
        right_col.addWidget(self.high_speed)
        conv_row = QHBoxLayout()
        conv_row.addWidget(QLabel("Convection Setting", self))
        self.convection = QComboBox(self)
        self.convection.addItems([
            "Forced convection", "Natural convection", "Mixed convection"])
        conv_row.addWidget(self.convection, 1)
        right_col.addLayout(conv_row)
        right_col.addStretch(1)

        cols.addLayout(left_col, 1)
        cols.addLayout(right_col, 1)
        al.addLayout(cols, 1)
        al.addWidget(_note(
            "Note) More detailed settings will be available in "
            "Condition Wizard.", self))
        self._load()

    @staticmethod
    def _pair_toggles(layout, yes: str, no: str, on_pick,
                      yes_icon: str = "", no_icon: str = ""):
        row = QHBoxLayout()
        row.setSpacing(8)
        b_yes = QToolButton()
        b_no = QToolButton()
        style = (
            "QToolButton { text-align: left; padding: 4px 8px; "
            "border: 1px solid #c5ccd6; border-radius: 5px; "
            "background: #f7f9fc; }"
            "QToolButton:checked { border: 2px solid #3a78c8; "
            "background: #e8f1fc; font-weight: 600; }"
            "QToolButton:!checked { color: #888; }"
            "QToolButton:hover { background: #eef3fa; }"
        )

        def _make(idx: int):
            def _slot(_checked=False):
                b_yes.setChecked(idx == 0)
                b_no.setChecked(idx == 1)
                on_pick(idx)
            return _slot

        for btn, text, idx, ikind in (
                (b_yes, yes, 0, yes_icon), (b_no, no, 1, no_icon)):
            btn.setText(text)
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            if ikind:
                btn.setIcon(iwiz_atype_icon(ikind, 44))
                btn.setIconSize(QSize(44, 44))
            btn.setMinimumHeight(56)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(style)
            btn.clicked.connect(_make(idx))
            row.addWidget(btn)
        layout.addLayout(row)
        b_yes.setChecked(True)
        b_no.setChecked(False)
        return b_yes, b_no

    @staticmethod
    def _set_combo(combo: "QComboBox", idx: int) -> None:
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    @staticmethod
    def _sync_pair(btns, idx: int) -> None:
        yes, no = btns
        yes.setChecked(idx == 0)
        no.setChecked(idx == 1)

    def _load(self) -> None:
        heat = self.model.analysis_set_value("heat", "0")
        heat_i = 0 if heat == "1" else 1
        self._set_combo(self.heat_solve, heat_i)
        self._sync_pair(self._heat_btns, heat_i)
        turb = self.model.analysis_set_value("turbulence", "0")
        flow_i = 1 if turb == "1" else 0
        self._set_combo(self.flow_type, flow_i)
        self._sync_pair(self._flow_type_btns, flow_i)
        model_idx = int(self.model.analysis_set_value(
            "turbulence_model", "0") or 0)
        if 0 <= model_idx < self.turb_model.count():
            self.turb_model.setCurrentIndex(model_idx)
        self._set_combo(self.flow_solve, 0)
        self.flow_solve_yes.setChecked(True)
        self.flow_solve_no.setChecked(False)
        # Radiation / solar defaults: Ignore selected (combo idx 0)
        self._sync_pair(self._rad_btns, 1)   # Ignore is second button
        self._sync_pair(self._solar_btns, 1)
        rad = self.model.analysis_set_value("radiation", "0")
        if rad in ("1", "T"):
            self._set_combo(self.radiation, 1)
            self._sync_pair(self._rad_btns, 0)
        sol = self.model.analysis_set_value("solar", "0")
        if sol in ("1", "T"):
            self._set_combo(self.solar, 1)
            self._sync_pair(self._solar_btns, 0)

    def apply(self) -> None:
        heat = "1" if self.heat_solve.currentIndex() == 0 else "0"
        self.model.set_analysis_set_value("heat", heat)
        self.model.set_analysis_set_value("type", "incompressive")
        turb = "1" if self.flow_type.currentIndex() == 1 else "0"
        self.model.set_analysis_set_value("turbulence", turb)
        self.model.set_analysis_set_value(
            "turbulence_model", str(self.turb_model.currentIndex()))
        rad = "1" if self.radiation.currentIndex() == 1 else "0"
        self.model.set_analysis_set_value("radiation", rad)
        sol = "1" if self.solar.currentIndex() == 1 else "0"
        self.model.set_analysis_set_value("solar", sol)
        flow = "1" if self.flow_solve.currentIndex() == 0 else "0"
        self.model.set_analysis_set_value("flow", flow)


class _IwPurposePage(QWidget if _HAS_GUI else object):
    def __init__(self, model: StpreModel, log_fn=None):
        super().__init__()
        self.model = model
        self._log_fn = log_fn
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Sets basic types of computational domain boundary.", self))
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        lay.addWidget(sep)

        self.purpose: dict[str, QRadioButton] = {}
        radio_box = QVBoxLayout()
        for label, key in PURPOSE_LABELS:
            row = QHBoxLayout()
            rb = QRadioButton(label, self)
            rb.setIcon(purpose_icon(key, 48))
            rb.setIconSize(QSize(48, 48))
            row.addWidget(rb)
            radio_box.addLayout(row)
            self.purpose[key] = rb
        lay.addLayout(radio_box)

        self.boundary_stack = QStackedWidget(self)
        self._panels: dict[str, QWidget] = {}
        self._panels["none"] = _note(
            "Boundary conditions are set in the Condition Wizard.", self)
        self.boundary_stack.addWidget(self._panels["none"])

        forced = QWidget()
        fl = QVBoxLayout(forced)
        fd_row = QHBoxLayout()
        fd_row.addWidget(QLabel("Flow direction", forced))
        self.forced_dir = QComboBox(forced)
        self.forced_dir.addItems(["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
        fd_row.addWidget(self.forced_dir)
        fd_row.addStretch(1)
        fl.addLayout(fd_row)
        self.forced_vel = QDoubleSpinBox(forced)
        self.forced_vel.setRange(0.0, 1.0e6)
        self.forced_vel.setValue(1.0)
        _pair_row(fl, "Inflow velocity", self.forced_vel, "m/s")
        fl.addWidget(QLabel("Outlet static pressure: 0 Pa", forced))
        self.open_space = QComboBox(forced)
        self.open_space.addItems(["Open space", "Closed space"])
        _pair_row(fl, "Space type", self.open_space)
        fl.addWidget(_note(PURPOSE_BC["external_forced"], forced))
        fl.addStretch(1)
        self._panels["external_forced"] = forced
        self.boundary_stack.addWidget(forced)

        natural = QWidget()
        nl = QVBoxLayout(natural)
        nl.addWidget(QLabel("Top: Natural outflow condition", natural))
        nl.addWidget(QLabel(
            "4 sides: Free slip + Adiabatic", natural))
        nl.addWidget(QLabel("Bottom: Total pressure condition", natural))
        nl.addWidget(_note(PURPOSE_BC["external_natural"], natural))
        nl.addStretch(1)
        self._panels["external_natural"] = natural
        self.boundary_stack.addWidget(natural)

        enclosure = QWidget()
        el = QVBoxLayout(enclosure)
        face_row = QHBoxLayout()
        face_row.addWidget(QLabel("Top face", enclosure))
        self.enc_top = QComboBox(enclosure)
        self.enc_top.addItems(["Enclosure I"])
        face_row.addWidget(self.enc_top)
        el.addLayout(face_row)
        self.enc_nat = QCheckBox("Natural convection formula", enclosure)
        self.enc_rad = QCheckBox("Radiation formula", enclosure)
        el.addWidget(self.enc_nat)
        el.addWidget(self.enc_rad)
        el.addWidget(_note(PURPOSE_BC["internal_enclosure"], enclosure))
        el.addStretch(1)
        self._panels["internal_enclosure"] = enclosure
        self.boundary_stack.addWidget(enclosure)

        buildings = QWidget()
        bl = QVBoxLayout(buildings)
        bl.addWidget(_note(PURPOSE_BC["external_buildings"], buildings))
        bl.addStretch(1)
        self._panels["external_buildings"] = buildings
        self.boundary_stack.addWidget(buildings)

        lay.addWidget(self.boundary_stack, 1)
        for rb in self.purpose.values():
            rb.toggled.connect(self.refresh_boundary)
        self.purpose["none"].setChecked(True)
        self.refresh_boundary()

    def select(self, key: str) -> None:
        rb = self.purpose.get(key)
        if rb is not None:
            rb.setChecked(True)

    def current(self) -> str:
        for key, rb in self.purpose.items():
            if rb.isChecked():
                return key
        return "none"

    def refresh_boundary(self, *_a) -> None:
        key = self.current()
        panel = self._panels.get(key, self._panels["none"])
        self.boundary_stack.setCurrentWidget(panel)

    def _log(self, msg: str, level: str = "INFO") -> None:
        if self._log_fn is not None:
            self._log_fn(msg, level)
        else:
            parent = self.parent()
            if parent is not None and hasattr(parent, "log"):
                parent.log(msg, level)

    def apply_boundary(self, model: StpreModel) -> None:
        purpose = self.current()
        if purpose == "none":
            return
        if purpose == "external_forced":
            self._apply_forced(model)
        elif purpose == "external_natural":
            self._apply_natural(model)
        elif purpose in ("internal_enclosure", "external_buildings"):
            self._log(
                f"Initial Wizard: boundary auto-setting for '{purpose}' "
                f"not written (phase 1).", "WARN")

    def _apply_forced(self, model: StpreModel) -> None:
        ambient = model.project_value("ambient_temperature", "20")
        dirs = {"+X": ("Xmin", "Xmax", (1, 0, 0)),
                "-X": ("Xmax", "Xmin", (-1, 0, 0)),
                "+Y": ("Ymin", "Ymax", (0, 1, 0)),
                "-Y": ("Ymax", "Ymin", (0, -1, 0)),
                "+Z": ("Zmin", "Zmax", (0, 0, 1)),
                "-Z": ("Zmax", "Zmin", (0, 0, -1))}
        in_face, out_face, vdir = dirs.get(
            self.forced_dir.currentText(), ("Xmin", "Xmax", (1, 0, 0)))
        speed = self.forced_vel.value()
        vel_str = ",".join(f"{speed * c:g}" for c in vdir)
        model.upsert_value("flux", "inlet", [
            ("kind", "fixed_vel", None),
            ("velocity", vel_str, None),
            ("temperature", ambient, "C"),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        model.bind_condition("region", in_face, "inlet")
        model.upsert_value("flux", "outlet", [
            ("kind", "total_pres", None),
            ("pressure", "0", "Pa"),
            ("temperature", ambient, "C"),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        model.bind_condition("region", out_face, "outlet")
        model.upsert_value("wall", "side_wall", [
            ("kind", "free_slip", None),
            ("option", "1", None),
        ])
        model.upsert_value("heat_transfer", "side_adiabatic", [
            ("kind", "adiabatic", None),
            ("temperature", ambient, "C"),
            ("use", "2", None),
        ])
        side_faces = {"Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"}
        side_faces.discard(in_face)
        side_faces.discard(out_face)
        for face in side_faces:
            model.bind_condition("region", face, "side_wall")
            model.bind_condition("region", face, "side_adiabatic")
        self._log("Initial Wizard: external forced-convection boundary "
                  "conditions written (inlet/outlet/side walls).")

    def _apply_natural(self, model: StpreModel) -> None:
        ambient = model.project_value("ambient_temperature", "20")
        model.upsert_value("flux", "natural_top", [
            ("kind", "natural_outflow", None),
            ("temperature", ambient, "C"),
        ])
        model.bind_condition("region", "Zmax", "natural_top")
        model.upsert_value("flux", "total_bottom", [
            ("kind", "total_pres", None),
            ("pressure", "0", "Pa"),
            ("temperature", ambient, "C"),
        ])
        model.bind_condition("region", "Zmin", "total_bottom")
        model.upsert_value("wall", "side_wall", [
            ("kind", "free_slip", None),
            ("option", "1", None),
        ])
        model.upsert_value("heat_transfer", "side_adiabatic", [
            ("kind", "adiabatic", None),
            ("temperature", ambient, "C"),
            ("use", "2", None),
        ])
        for face in ("Xmin", "Xmax", "Ymin", "Ymax"):
            model.bind_condition("region", face, "side_wall")
            model.bind_condition("region", face, "side_adiabatic")
        self._log("Initial Wizard: external natural-convection boundary "
                  "conditions written.")


class _IwConfirmPage(QWidget if _HAS_GUI else object):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Items", "Conditions"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        lay.addWidget(self.table, 1)
        brow = QHBoxLayout()
        self.btn_clip = QPushButton("Clipboard", self)
        self.btn_clip.clicked.connect(self._clipboard)
        self.btn_file = QPushButton("File Output...", self)
        self.btn_file.clicked.connect(self._file_output)
        brow.addWidget(self.btn_clip)
        brow.addWidget(self.btn_file)
        brow.addStretch(1)
        lay.addLayout(brow)
        lay.addWidget(_note(
            "Starts creating and placing analysis model after clicking "
            "[Finish].", self))
        self._rows: list[tuple[str, str]] = []

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        from PyQt5.QtGui import QBrush, QColor, QFont
        self._rows = list(rows)
        self.table.setRowCount(0)
        row_h = 22
        sec_bg = QBrush(QColor(230, 238, 248))
        for i, (item, cond) in enumerate(rows):
            self.table.insertRow(i)
            it = QTableWidgetItem(item)
            cd = QTableWidgetItem(cond)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            cd.setFlags(cd.flags() & ~Qt.ItemIsEditable)
            if item.startswith("* "):
                f = QFont(it.font())
                f.setBold(True)
                it.setFont(f)
                cd.setFont(f)
                it.setBackground(sec_bg)
                cd.setBackground(sec_bg)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, cd)
            self.table.setRowHeight(i, row_h)

    def _as_text(self) -> str:
        lines = ["Items\tConditions"]
        for item, cond in self._rows:
            lines.append(f"{item}\t{cond}")
        return "\n".join(lines)

    def _clipboard(self) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(self._as_text())
        except Exception:
            pass

    def _file_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "File Output", "wizard_settings.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._as_text())

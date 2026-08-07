"""M6: Initial Wizard and Condition Wizard (STpre [Wizard] menu).

Aligned with the Pre_eng manual pages and the STpre binary strings:

- STpreIwiz_Bx64.dll steps: Project / Solution / Import CAD Data /
  Computational Domain / Analysis Type / Initial Value/Gravity /
  Purpose of Analysis / Condition for Computational Domain Boundary /
  Confirm Settings; buttons ``Finish/Cancel/Next >>/<< Back`` and a
  step counter ``%s %s ( %d/%d ) step``;
- STpreCwiz_Bx64.dll pages: Analysis Types / Basic Settings / Fluid
  Region / Flow / Heat / Initial Condition / Boundary Condition
  (Flow, Wall, Thermal, Symmetrical) / Analysis Control /
  File Specification / Condition List / Setting Confirmation, with a
  left navigation tree where undefined steps are grey and defined
  steps orange.

Both wizards write back to the ``<analysis_set>`` / ``<project>`` /
``<condition>`` / ``<value>`` sections through ``cabxml.StpreModel`` so the
changes persist in the cab and reach the ``.s`` exporter.

Phase-1 approximations (documented in DEV_SUMMARY):
- wizard pages whose cab equivalent does not exist yet (building-affected
  winds, enclosure heat release detail) log a WARN and are not written;
- Condition Wizard covers the Basic-Exercise-1 page set only.
"""

from __future__ import annotations

import os
from typing import Optional

import cab_domain
import cab_import
from cabxml import PropertyModel, StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
        QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
        QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
        QWidget,
    )
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless environments
    _HAS_GUI_DEPS = False
    QDialog = object  # type: ignore
    QWidget = object  # type: ignore

from cab_dialogs import DialogHeader, MaterialListDialog

_UNIT_FACTOR = {"mm": 1.0, "m": 1000.0, "cm": 10.0}  # value -> mm
_GRAVITY_DIRS = [("X+", (1, 0, 0)), ("X-", (-1, 0, 0)),
                 ("Y+", (0, 1, 0)), ("Y-", (0, -1, 0)),
                 ("Z+", (0, 0, 1)), ("Z-", (0, 0, -1))]


def _row(layout, label, widget, stretch=1):
    """Label + widget row helper."""
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


def _vec16(loc_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
           scale: float = 1.0) -> str:
    """Column-major 4x4 with uniform scale + translation."""
    dx, dy, dz = loc_m
    return ",".join(f"{v:.17g}" for v in
                    (scale, 0, 0, 0,
                     0, scale, 0, 0,
                     0, 0, scale, 0,
                     dx, dy, dz, 1.0))


# ============================================================== framework


class WizardBase(QDialog if _HAS_GUI_DEPS else object):
    """Shared wizard chrome: step label, optional left nav tree, ordered
    page stack and ``<< Back`` / ``Next >>`` / ``Finish`` / ``Cancel``."""

    def __init__(self, title: str, *, parent=None, show_tree: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._keys: list[str] = []
        self._index: dict[str, int] = {}
        self._titles: dict[str, str] = {}
        self._parents: dict[str, str] = {}
        self._items: dict[str, QTreeWidgetItem] = {}
        self._current = 0

        root = QVBoxLayout(self)
        self.header = DialogHeader(title, "wizard", self)
        root.addWidget(self.header)

        self.step_label = QLabel(self)
        self.step_label.setStyleSheet("color: #666;")
        root.addWidget(self.step_label)

        mid = QHBoxLayout()
        self.nav = None
        if show_tree:
            self.nav = QTreeWidget(self)
            self.nav.setHeaderHidden(True)
            self.nav.itemClicked.connect(self._on_nav)
            mid.addWidget(self.nav)
        self.stack = QStackedWidget(self)
        mid.addWidget(self.stack, 1)
        root.addLayout(mid, 1)

        blay = QHBoxLayout()
        self.btn_back = QPushButton("<< Back", self)
        self.btn_next = QPushButton("Next >>", self)
        self.btn_finish = QPushButton("Finish", self)
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_finish.clicked.connect(self._finish)
        self.btn_cancel.clicked.connect(self._cancel)
        blay.addStretch(1)
        for b in (self.btn_back, self.btn_next, self.btn_finish,
                  self.btn_cancel):
            blay.addWidget(b)
        root.addLayout(blay)
        self.resize(760, 560)

    # -- page management --------------------------------------------------

    def _add_page(self, key: str, title: str, widget: Optional[QWidget],
                  parent_key: Optional[str] = None) -> None:
        """Register a page; ``widget=None`` creates a nav-group node only."""
        self._titles[key] = title
        if parent_key:
            self._parents[key] = parent_key
        if self.nav is not None:
            parent_item = self._items.get(parent_key) if parent_key \
                else None
            item = QTreeWidgetItem(
                parent_item or self.nav.invisibleRootItem(), [title])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            self._items[key] = item
            if parent_item is None:
                self.nav.addTopLevelItem(item)
            else:
                parent_item.setExpanded(True)
        if widget is not None:
            self._index[key] = len(self._keys)
            self._keys.append(key)
            self.stack.addWidget(widget)

    def _mark_defined(self, key: str, defined: bool) -> None:
        item = self._items.get(key)
        if item is not None:
            item.setCheckState(0, Qt.Checked if defined else Qt.Unchecked)

    def _show_page(self, idx: int) -> None:
        self._current = max(0, min(idx, len(self._keys) - 1))
        key = self._keys[self._current]
        self.stack.setCurrentIndex(self._index[key])
        self.step_label.setText(
            f"{self._titles[key]}   ( {self._current + 1}/{len(self._keys)} ) step")
        self.btn_back.setEnabled(self._current > 0)
        self.btn_next.setEnabled(self._current < len(self._keys) - 1)
        if self.nav is not None:
            self.nav.setCurrentItem(self._items.get(key))

    def _on_nav(self, item, _col) -> None:
        for key, it in self._items.items():
            if it is item and key in self._index:
                self._show_page(self._index[key])
                return

    def _go_back(self) -> None:
        self._show_page(self._current - 1)

    def _go_next(self) -> None:
        self._show_page(self._current + 1)

    def _finish(self) -> None:
        self._on_finish()
        self.accept()

    def _cancel(self) -> None:
        self._on_cancel()
        self.reject()

    # subclass hooks --------------------------------------------------------

    def _on_finish(self) -> None:
        """Write the wizard settings to the model (override)."""

    def _on_cancel(self) -> None:
        """Restore the pre-wizard state (override)."""

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)

    def _rebuild(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()


# ========================================================== Initial Wizard

_PURPOSES = [
    ("Internal flow (enclosure heat release)", "internal_enclosure"),
    ("External flow (natural convection)", "external_natural"),
    ("External flow (forced convection)", "external_forced"),
    ("External flow (winds blowing through buildings)", "external_buildings"),
]

# purpose -> auto boundary-condition summary (manual tables)
_PURPOSE_BC = {
    "external_forced": (
        "Inflow side   : Fixed velocity condition\n"
        "Outflow side  : Static pressure condition\n"
        "Side faces    : Free slip + Adiabatic\n"
        "(writes flux/wall/heat_transfer values on Xmin/Xmax/Z± sides)"),
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


class _IwProjectPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        lay = QVBoxLayout(self)
        self.name = QLineEdit(model.project_name, self)
        _row(lay, "Project name", self.name)
        self.comment = QLineEdit(
            model.project_value("comment"), self)
        _row(lay, "Comments", self.comment)
        info = QLabel(
            "The project and S file are saved with the folder selected via "
            "File -> Save As.  The property file is the project's "
            "property library member.", self)
        info.setWordWrap(True)
        info.setStyleSheet("color: #555;")
        lay.addWidget(info)
        lay.addStretch(1)


class _IwImportPage(QWidget if _HAS_GUI_DEPS else object):
    """Import CAD data: each read x_t file becomes one cab member on Finish."""

    def __init__(self, model: StpreModel, archive, cad_meshes):
        super().__init__()
        self.model = model
        self.archive = archive
        self.cad_meshes = cad_meshes
        # one entry per read file: (path, raw_bytes, [ImportedBody])
        self._entries: list[tuple[str, bytes, list]] = []
        self._config: dict[int, tuple[tuple[float, float, float], float]] = {}
        lay = QVBoxLayout(self)
        self.list = QListWidget(self)
        lay.addWidget(self.list, 1)
        brow = QHBoxLayout()
        self.btn_read = QPushButton("Read From File", self)
        self.btn_read.clicked.connect(self._read)
        self.btn_remove = QPushButton("Remove", self)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_configure = QPushButton("Configure", self)
        self.btn_configure.clicked.connect(self._configure)
        for b in (self.btn_read, self.btn_remove, self.btn_configure):
            brow.addWidget(b)
        brow.addStretch(1)
        lay.addLayout(brow)
        note = QLabel("XT files are imported as new parts and cab members "
                      "on Finish. Configure sets Location (mm) and Scale.",
                      self)
        note.setStyleSheet("color: #555;")
        lay.addWidget(note)

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
        names = ", ".join(b.name for b in bodies)
        QListWidgetItem(f"{os.path.basename(path)}  [{names}]", self.list)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.list.takeItem(row)
        self._entries.pop(row)
        self._config = {i: v for i, v in self._config.items() if i < row} \
            if row < len(self._entries) else {k: v for k, v in
                                              self._config.items()
                                              if k != row}
        # shift config rows above the removed one
        shifted: dict[int, tuple] = {}
        for i, (k, v) in enumerate(self._config.items()):
            shifted[i] = v
        self._config = shifted

    def _configure(self) -> None:
        row = self.list.currentRow()
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
            self._config[row] = (
                tuple(loc[a].value() / 1000.0 for a in "xyz"),
                scale.value())

    def apply_to_model(self) -> None:
        """Register each read file as a cab member + parts (idempotent)."""
        added: list[str] = []
        for raw in {e[1] for e in self._entries}:
            if self.archive is not None:
                member = cab_import.add_xt_member(self.archive, raw)
                self.model.add_body_file(member.name)
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

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)


class _IwDomainPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel, props, cad_meshes):
        super().__init__()
        self.model = model
        self.props = props
        self.cad_meshes = cad_meshes
        spec = cab_domain.domain_from_xml(model) or cab_domain.DomainSpec()
        self.spec = spec
        lay = QVBoxLayout(self)

        coord = QHBoxLayout()
        coord.addWidget(QLabel("Coordinate system", self))
        self.coordinate = QComboBox(self)
        self.coordinate.addItems(
            ["Cartesian coordinate", "Cylindrical coordinate",
             "Axial symmetry"])
        coord.addWidget(self.coordinate, 1)
        lay.addLayout(coord)

        urow = QHBoxLayout()
        urow.addWidget(QLabel("Coordinate value unit", self))
        self.unit = QComboBox(self)
        self.unit.addItems(["mm", "m", "cm"])
        urow.addWidget(self.unit, 1)
        urow.addWidget(QLabel("Material", self))
        self.material = QLineEdit(self)
        self.material.setReadOnly(True)
        urow.addWidget(self.material, 1)
        self.btn_mat = QPushButton("...", self)
        self.btn_mat.setFixedWidth(28)
        self.btn_mat.clicked.connect(self._pick_material)
        urow.addWidget(self.btn_mat)
        lay.addLayout(urow)

        grid = QGridLayout()
        grid.addWidget(QLabel("Minimum", self), 0, 0)
        grid.addWidget(QLabel("Maximum", self), 1, 0)
        for i, ax in enumerate("xyz"):
            lab = QLabel(ax.upper(), self)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 2, i + 1)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            for row, side in ((0, "min"), (1, "max")):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1.0e9, 1.0e9)
                sb.setDecimals(6)
                grid.addWidget(sb, row, i + 1)
                self.spins[f"{ax}{side}"] = sb
        lay.addLayout(grid)

        brow = QHBoxLayout()
        self.btn_cad = QPushButton("CAD Data Size", self)
        self.btn_cad.clicked.connect(self._cad_size)
        self.btn_preview = QPushButton("Preview", self)
        self.btn_preview.clicked.connect(self._preview)
        brow.addWidget(self.btn_cad)
        brow.addWidget(self.btn_preview)
        brow.addStretch(1)
        lay.addLayout(brow)

        chk = QCheckBox(
            "Grid of the sketch plane is automatically adjusted", self)
        chk.setChecked(True)
        lay.addWidget(chk)
        lay.addStretch(1)
        self._load()

    def _load(self) -> None:
        spec = self.spec
        self.unit.setCurrentText(spec.unit if spec.unit in _UNIT_FACTOR
                                 else "mm")
        self.material.setText(spec.material)
        for i, ax in enumerate("xyz"):
            self.spins[f"{ax}min"].setValue(spec.xyz_min[i])
            self.spins[f"{ax}max"].setValue(spec.xyz_max[i])

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


class _IwAnalysisTypePage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        g = QGroupBox("Flow analysis", self)
        gl = QHBoxLayout(g)
        self.flow_solve = QComboBox(g)
        self.flow_solve.addItems(["Solve", "Do not solve"])
        gl.addWidget(self.flow_solve)
        gl.addWidget(QLabel("Flow type", g))
        self.flow_type = QComboBox(g)
        self.flow_type.addItems(["Laminar flow", "Turbulent flow"])
        gl.addWidget(self.flow_type)
        gl.addWidget(QLabel("Turbulence model", g))
        self.turb_model = QComboBox(g)
        self.turb_model.addItems([
            "Standard k-eps model", "RNG k-eps model", "MP k-eps model",
            "Linear low-Re model", "Non-linear low-Re model",
            "Improved LK k-eps model", "LES"])
        gl.addWidget(self.turb_model, 1)
        lay.addWidget(g)

        h = QGroupBox("Heat", self)
        hl = QHBoxLayout(h)
        self.heat_solve = QComboBox(h)
        self.heat_solve.addItems(["Solve", "Do not solve"])
        hl.addWidget(self.heat_solve)
        hl.addWidget(QLabel("Radiation", h))
        self.radiation = QComboBox(h)
        self.radiation.addItems(["Ignore", "Consider"])
        hl.addWidget(self.radiation)
        hl.addWidget(QLabel("Solar radiation", h))
        self.solar = QComboBox(h)
        self.solar.addItems(["Ignore", "Consider"])
        hl.addWidget(self.solar)
        hl.addStretch(1)
        lay.addWidget(h)

        self.high_speed = QCheckBox("High-speed calculation", self)
        lay.addWidget(self.high_speed)
        lay.addStretch(1)
        self._load()

    def _load(self) -> None:
        heat = self.model.analysis_set_value("heat", "0")
        self.heat_solve.setCurrentIndex(1 if heat == "1" else 0)
        turb = self.model.analysis_set_value("turbulence", "0")
        self.flow_type.setCurrentIndex(1 if turb == "1" else 0)
        model_idx = int(self.model.analysis_set_value(
            "turbulence_model", "0") or 0)
        if 0 <= model_idx < self.turb_model.count():
            self.turb_model.setCurrentIndex(model_idx)

    def apply(self) -> None:
        heat = "1" if self.heat_solve.currentIndex() == 0 else "0"
        self.model.set_analysis_set_value("heat", heat)
        self.model.set_analysis_set_value("type", "incompressive")
        turb = "1" if self.flow_type.currentIndex() == 1 else "0"
        self.model.set_analysis_set_value("turbulence", turb)
        self.model.set_analysis_set_value(
            "turbulence_model", str(self.turb_model.currentIndex()))


class _IwInitialGravityPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        g = QGroupBox("Heat", self)
        gl = QVBoxLayout(g)
        self.temp_unit = QComboBox(g)
        self.temp_unit.addItems(["C", "K", "F", "R"])
        _pair_row(gl, "Unit of reference temperature", self.temp_unit)
        self.temp_default = QDoubleSpinBox(g)
        self.temp_default.setRange(-273.15, 1.0e6)
        self.temp_default.setDecimals(2)
        _pair_row(gl, "Default value of temperature", self.temp_default, "C")
        self.solid_temp = QDoubleSpinBox(g)
        self.solid_temp.setRange(-273.15, 1.0e6)
        self.solid_temp.setDecimals(2)
        _pair_row(gl, "Initial temperature of solid", self.solid_temp, "C")
        self.emissivity = QDoubleSpinBox(g)
        self.emissivity.setRange(0.0, 1.0)
        self.emissivity.setDecimals(2)
        _pair_row(gl, "Default value of emissivity", self.emissivity)
        lay.addWidget(g)

        gg = QGroupBox("Gravity", self)
        ggl = QVBoxLayout(gg)
        self.gravity_chk = QCheckBox("Consider gravity", gg)
        ggl.addWidget(self.gravity_chk)
        dirrow = QHBoxLayout()
        dirrow.addWidget(QLabel("Direction of gravity", gg))
        self.gravity_dir = QComboBox(gg)
        for label, _v in _GRAVITY_DIRS:
            self.gravity_dir.addItem(label)
        dirrow.addWidget(self.gravity_dir, 1)
        ggl.addLayout(dirrow)
        self.gravity_acc = QDoubleSpinBox(gg)
        self.gravity_acc.setRange(0.0, 1000.0)
        self.gravity_acc.setDecimals(2)
        _pair_row(ggl, "Acceleration due to gravity", self.gravity_acc,
                  "m/s2")
        lay.addWidget(gg)
        lay.addStretch(1)
        self._load()

    def _load(self) -> None:
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
        grav = self.model.analysis_set_value("grav_vec", "0,0,-1").split(",")
        vec = (float(grav[0]), float(grav[1]), float(grav[2]))
        for i, (_label, v) in enumerate(_GRAVITY_DIRS):
            if v == vec:
                self.gravity_dir.setCurrentIndex(i)
                break
        try:
            self.gravity_acc.setValue(float(
                self.model.analysis_set_value("grav_abs", "9.8")))
        except ValueError:
            pass

    def apply(self) -> None:
        self.model.set_project_value(
            "ambient_temperature", f"{self.temp_default.value():g}")
        self.model.set_project_value(
            "solid_init_temperature", f"{self.solid_temp.value():g}")
        if self.gravity_chk.isChecked():
            _label, vec = _GRAVITY_DIRS[self.gravity_dir.currentIndex()]
            self.model.set_gravity(self.gravity_acc.value(), vec)


class _IwPurposePage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        self.purpose: dict[str, QRadioButton] = {}
        for label, key in _PURPOSES:
            rb = QRadioButton(label, self)
            lay.addWidget(rb)
            self.purpose[key] = rb
        self.purpose["external_forced"].setChecked(True)
        lay.addStretch(1)

    def current(self) -> str:
        for key, rb in self.purpose.items():
            if rb.isChecked():
                return key
        return "external_forced"


class _IwBoundaryPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.info = QLabel("", self)
        self.info.setWordWrap(True)
        self.info.setStyleSheet("font-family: monospace;")
        lay.addWidget(self.info)
        self.btn_apply = QPushButton(
            "Apply boundary conditions for this purpose", self)
        self.btn_apply.clicked.connect(self._apply)
        lay.addWidget(self.btn_apply)
        note = QLabel("Conditions are written as <value>/<condition> "
                      "entries (fixed velocity / static pressure / free "
                      "slip / adiabatic).", self)
        note.setStyleSheet("color: #555;")
        lay.addWidget(note)
        lay.addStretch(1)

    def set_purpose(self, purpose: str) -> None:
        self._purpose = purpose
        self.info.setText(_PURPOSE_BC.get(purpose, ""))
        self.btn_apply.setEnabled(purpose in (
            "external_forced", "external_natural"))

    def _apply(self) -> None:
        self._on_apply(self._purpose)

    def _on_apply(self, purpose: str) -> None:
        """Subclass hook: write the boundary values for the purpose."""


class _IwConfirmPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        lay.addWidget(self.text, 1)
        brow = QHBoxLayout()
        self.btn_clip = QPushButton("Clipboard", self)
        self.btn_clip.clicked.connect(self._clipboard)
        self.btn_file = QPushButton("File Output", self)
        self.btn_file.clicked.connect(self._file_output)
        brow.addWidget(self.btn_clip)
        brow.addWidget(self.btn_file)
        brow.addStretch(1)
        lay.addLayout(brow)

    def set_summary(self, text: str) -> None:
        self.text.setPlainText(text)

    def _clipboard(self) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(self.text.toPlainText())
        except Exception:
            pass

    def _file_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "File Output", "wizard_settings.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.text.toPlainText())


class InitialWizard(WizardBase):
    """[Wizard] - [Initial Setting]: the STpre Initial Wizard."""

    def __init__(self, model: StpreModel, props: Optional[PropertyModel],
                 cad_meshes, archive=None, parent=None):
        super().__init__("Initial Setting", parent=parent, show_tree=False)
        self.model = model
        self.props = props
        self.archive = archive
        self._snapshot = model.doc.serialize()
        self._cad_meshes = cad_meshes

        self.p_project = _IwProjectPage(model)
        self.p_import = _IwImportPage(model, archive, self._cad_meshes)
        self.p_domain = _IwDomainPage(model, props, self._cad_meshes)
        self.p_analysis = _IwAnalysisTypePage(model)
        self.p_initgrav = _IwInitialGravityPage(model)
        self.p_purpose = _IwPurposePage(model)
        self.p_boundary = _IwBoundaryPage()
        self.p_boundary._on_apply = self._apply_boundary
        self.p_confirm = _IwConfirmPage()

        self._add_page("project", "Project", self.p_project)
        self._add_page("import", "Import CAD Data", self.p_import)
        self._add_page("domain", "Computational Domain", self.p_domain)
        self._add_page("analysis", "Analysis Type", self.p_analysis)
        self._add_page("initgrav", "Initial Value/Gravity", self.p_initgrav)
        self._add_page("purpose", "Purpose of Analysis", self.p_purpose)
        self._add_page("boundary", "Conditions for Computational Domain "
                       "Boundary", self.p_boundary)
        self._add_page("confirm", "Confirm Settings", self.p_confirm)
        self._show_page(0)

    def _mark_domain_defined(self) -> None:
        self._mark_defined("domain", True)
        self._mark_defined("analysis", True)
        self._mark_defined("initgrav", True)
        self._mark_defined("purpose", True)
        self._mark_defined("boundary", True)
        self._mark_defined("import", bool(self.p_import._entries))
        self._mark_defined("project", True)

    def _go_next(self) -> None:
        if self._keys[self._current] == "purpose":
            self.p_boundary.set_purpose(self.p_purpose.current())
        if self._keys[self._current] == "confirm":
            self.p_confirm.set_summary(self._summary())
        super()._go_next()

    def _go_back(self) -> None:
        if self._keys[self._current] == "boundary":
            self.p_boundary.set_purpose(self.p_purpose.current())
        super()._go_back()

    def _summary(self) -> str:
        m = self.model
        spec = cab_domain.domain_from_xml(m) or cab_domain.DomainSpec()
        lines = [
            f"Project: {m.project_name}",
            f"Comments: {m.project_value('comment')}",
            f"CAD data: {len(self.p_import._entries)} file(s) read",
            f"Computational domain: {spec.coordinate} {spec.xyz_min} ~ "
            f"{spec.xyz_max} [{spec.unit}]",
            f"Domain material: {spec.material or '-'}",
            f"Analysis: heat={m.analysis_set_value('heat')}, "
            f"turbulence={m.analysis_set_value('turbulence')}, "
            f"model={m.analysis_set_value('turbulence_model')}",
            f"Initial value: ambient={m.project_value('ambient_temperature')}"
            f" C, solid={m.project_value('solid_init_temperature')} C",
            f"Gravity: {m.analysis_set_value('grav_vec')} x "
            f"{m.analysis_set_value('grav_abs')} m/s2",
            f"Purpose of analysis: {self.p_purpose.current()}",
            "",
            _PURPOSE_BC.get(self.p_purpose.current(), ""),
        ]
        return "\n".join(lines)

    def _apply_boundary(self, purpose: str) -> None:
        """Auto-set the computational-domain boundary conditions."""
        from cabxml import _first
        if purpose != "external_forced":
            self._log(
                f"Initial Wizard: boundary auto-setting for '{purpose}' "
                f"not written (phase 1).", "WARN")
            return
        ambient = self.model.project_value("ambient_temperature", "20")
        # inflow: fixed velocity on Xmin (into +X)
        self.model.upsert_value("flux", "inlet", [
            ("kind", "fixed_vel", None),
            ("velocity", "1,0,0", None),
            ("temperature", ambient, "C"),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        self.model.bind_condition("region", "Xmin", "inlet")
        # outflow: static pressure on Xmax
        self.model.upsert_value("flux", "outlet", [
            ("kind", "total_pres", None),
            ("pressure", "0", "Pa"),
            ("temperature", ambient, "C"),
            ("turbulence_type", "none", None),
            ("panel_option", "none", None),
        ])
        self.model.bind_condition("region", "Xmax", "outlet")
        # side walls: free slip (momentum) + adiabatic (heat)
        self.model.upsert_value("wall", "side_wall", [
            ("kind", "free_slip", None),
            ("option", "1", None),
        ])
        self.model.upsert_value("heat_transfer", "side_adiabatic", [
            ("kind", "adiabatic", None),
            ("temperature", ambient, "C"),
            ("use", "2", None),
        ])
        for face in ("Ymin", "Ymax", "Zmin", "Zmax"):
            self.model.bind_condition("region", face, "side_wall")
            self.model.bind_condition("region", face, "side_adiabatic")
        self._mark_defined("boundary", True)
        self._log("Initial Wizard: external forced-convection boundary "
                  "conditions written (inlet/outlet/side walls).")

    def _on_finish(self) -> None:
        self.model.set_project_name(self.p_project.name.text().strip()
                                    or "Untitled")
        self.model.set_project_value("comment",
                                     self.p_project.comment.text().strip())
        self.p_import.apply_to_model()
        cab_domain.apply_domain(self.model, self.p_domain._current_spec())
        self.p_analysis.apply()
        self.p_initgrav.apply()
        self.model.set_analysis_set_value(
            "purpose", self.p_purpose.current())
        self._apply_boundary(self.p_purpose.current())
        self._mark_domain_defined()
        self._rebuild()
        self._log("Initial Wizard finished; settings written to the "
                  "project (save the cab to persist).")

    def _on_cancel(self) -> None:
        import cabxml
        self.model.doc = cabxml.StpreDoc(self._snapshot)


# ======================================================== Condition Wizard

_CW_PAGES = [
    ("analysis", "Analysis Types", None),
    ("basic", "Basic Settings", None),
    ("fluid", "Fluid Region", None),
    ("flow", "Flow", None),
    ("heat", "Heat", None),
    ("initial", "Initial Condition", None),
    ("bc", "Boundary Condition", None),
    ("bc_flow", "Flow Boundary", "bc"),
    ("bc_wall", "Wall Boundary", "bc"),
    ("bc_thermal", "Thermal Boundary", "bc"),
    ("bc_symm", "Symmetrical Boundary", "bc"),
    ("control", "Analysis Control", None),
    ("file", "File Specification", None),
    ("condlist", "Condition List", None),
    ("confirm", "Setting Confirmation", None),
]


class _CwAnalysisTypesPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        flow = QGroupBox("Flow field", self)
        fl = QVBoxLayout(flow)
        self.flow_chk = QCheckBox("Flow", flow)
        fl.addWidget(self.flow_chk)
        trow = QHBoxLayout()
        self.laminar = QRadioButton("Laminar flow", flow)
        self.turbulent = QRadioButton("Turbulent flow", flow)
        trow.addWidget(self.laminar)
        trow.addWidget(self.turbulent)
        self.turb_model = QComboBox(flow)
        self.turb_model.addItems([
            "Standard k-eps model", "RNG k-eps model", "MP k-eps model",
            "Linear low-Re model", "Non-linear low-Re model",
            "Improved LK k-eps model", "LES"])
        trow.addWidget(self.turb_model, 1)
        fl.addLayout(trow)
        lay.addWidget(flow)

        self.types: dict[str, QCheckBox] = {}
        tg = QGroupBox("Analysis types", self)
        tl = QVBoxLayout(tg)
        for label, key in (("Heat", "heat"), ("Humidity", "humidity"),
                           ("Particle", "particle"), ("Radiation", "rad")):
            cb = QCheckBox(label, tg)
            tl.addWidget(cb)
            self.types[key] = cb
        lay.addWidget(tg)

        st = QHBoxLayout()
        st.addWidget(QLabel("Analysis mode", self))
        self.steady = QRadioButton("Steady-state analysis", self)
        self.transient = QRadioButton("Transient analysis", self)
        st.addWidget(self.steady)
        st.addWidget(self.transient)
        st.addStretch(1)
        lay.addLayout(st)
        lay.addStretch(1)
        self._load()

    def _load(self) -> None:
        heat = self.model.analysis_set_value("heat", "0")
        self.types["heat"].setChecked(heat == "1")
        turb = self.model.analysis_set_value("turbulence", "0")
        self.flow_chk.setChecked(True)
        self.turbulent.setChecked(turb == "1")
        self.laminar.setChecked(turb != "1")
        calc = self.model.analysis_set_value("calculation", "steady")
        self.transient.setChecked(calc == "transient")
        self.steady.setChecked(calc != "transient")

    def apply(self) -> None:
        self.model.set_analysis_set_value(
            "type", "incompressive")
        heat = "1" if self.types["heat"].isChecked() else "0"
        self.model.set_analysis_set_value("heat", heat)
        turb = "1" if self.turbulent.isChecked() else "0"
        self.model.set_analysis_set_value("turbulence", turb)
        self.model.set_analysis_set_value(
            "turbulence_model", str(self.turb_model.currentIndex()))
        self.model.set_cycles(
            1, 100, transient=self.transient.isChecked())


class _CwBasicSettingsPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        gg = QGroupBox("Gravity", self)
        ggl = QVBoxLayout(gg)
        self.gravity_chk = QCheckBox("Consider gravity", gg)
        ggl.addWidget(self.gravity_chk)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Direction of gravity", gg))
        self.gravity_dir = QComboBox(gg)
        for label, _v in _GRAVITY_DIRS:
            self.gravity_dir.addItem(label)
        drow.addWidget(self.gravity_dir, 1)
        ggl.addLayout(drow)
        self.gravity_acc = QDoubleSpinBox(gg)
        self.gravity_acc.setRange(0.0, 1000.0)
        self.gravity_acc.setDecimals(2)
        _pair_row(ggl, "Acceleration due to gravity", self.gravity_acc,
                  "m/s2")
        self.btn_check = QPushButton("Check Direction", gg)
        self.btn_check.clicked.connect(lambda: self._log(
            "Gravity direction shown at the domain Zmin center "
            "(cab viewer: see analysis_set grav_vec)."))
        ggl.addWidget(self.btn_check)
        lay.addWidget(gg)

        self.ambient = QDoubleSpinBox(self)
        self.ambient.setRange(-273.15, 1.0e6)
        self.ambient.setDecimals(2)
        _pair_row(lay, "Ambient temperature", self.ambient, "C")
        self.periodic = QCheckBox("Consider periodic boundary", self)
        lay.addWidget(self.periodic)
        lay.addStretch(1)
        self._load()

    def _load(self) -> None:
        try:
            self.ambient.setValue(float(self.model.project_value(
                "ambient_temperature", "20")))
        except ValueError:
            pass
        grav = self.model.analysis_set_value("grav_vec", "0,0,-1").split(",")
        vec = (float(grav[0]), float(grav[1]), float(grav[2]))
        self.gravity_chk.setChecked(any(v != 0 for v in vec))
        for i, (_label, v) in enumerate(_GRAVITY_DIRS):
            if v == vec:
                self.gravity_dir.setCurrentIndex(i)
                break
        try:
            self.gravity_acc.setValue(float(
                self.model.analysis_set_value("grav_abs", "9.8")))
        except ValueError:
            pass

    def apply(self) -> None:
        self.model.set_project_value(
            "ambient_temperature", f"{self.ambient.value():g}")
        if self.gravity_chk.isChecked():
            _label, vec = _GRAVITY_DIRS[self.gravity_dir.currentIndex()]
            self.model.set_gravity(self.gravity_acc.value(), vec)

    def _log(self, msg: str) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg)


class _CwFluidRegionPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel, props):
        super().__init__()
        self.model = model
        self.props = props
        lay = QVBoxLayout(self)
        self.fluid_combo = QComboBox(self)
        self.fluid_combo.addItems(props.material_names() if props else [])
        _pair_row(lay, "Material of Fluid 1 (domain)", self.fluid_combo)
        row = QHBoxLayout()
        self.btn_set = QPushButton("Set Fluid Material", self)
        self.btn_set.clicked.connect(self._apply)
        row.addWidget(self.btn_set)
        row.addStretch(1)
        lay.addLayout(row)
        note = QLabel("The computational domain is the fluid region; its "
                      "material is written to analysis_region/property.",
                      self)
        note.setStyleSheet("color: #555;")
        lay.addWidget(note)
        lay.addStretch(1)
        cur = self.model.domain_material()
        idx = self.fluid_combo.findText(cur)
        if idx >= 0:
            self.fluid_combo.setCurrentIndex(idx)

    def _apply(self) -> None:
        self.model.set_domain_material(self.fluid_combo.currentText())
        self._log(f"Fluid Region: domain material = "
                  f"{self.fluid_combo.currentText()}")

    def _log(self, msg: str) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg)


class _CwFlowPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        g = QGroupBox("Components of velocity", self)
        gl = QHBoxLayout(g)
        self.vel: dict[str, QCheckBox] = {}
        for ax in "xyz":
            cb = QCheckBox(ax.upper(), g)
            gl.addWidget(cb)
            self.vel[ax] = cb
        gl.addStretch(1)
        lay.addWidget(g)
        note = QLabel("Wall correction / adaptive wall function options "
                      "apply only with cut-cell parts or low-Re turbulence "
                      "(not shown in the cab viewer).", self)
        note.setStyleSheet("color: #555;")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        comps = self.model.analysis_set_value("velocity_components", "xyz")
        for ax in "xyz":
            self.vel[ax].setChecked(ax in comps)

    def apply(self) -> None:
        comps = "".join(a for a in "xyz" if self.vel[a].isChecked()) or "x"
        self.model.set_analysis_set_value("velocity_components", comps)


class _CwHeatPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        self.temp_unit = QComboBox(self)
        self.temp_unit.addItems(["C", "K", "F", "R"])
        _pair_row(lay, "Unit of temperature", self.temp_unit)
        self.shear = QCheckBox("Shear dissipation", self)
        lay.addWidget(self.shear)
        lay.addStretch(1)
        unit = model.units.get("temperature", "C")
        idx = self.temp_unit.findText(unit)
        self.temp_unit.setCurrentIndex(idx if idx >= 0 else 0)

    def apply(self) -> None:
        from cabxml import _first
        u = _first(self.model.root, "unit")
        if u is not None:
            el = _first(u, "temperature")
            if el is not None:
                from cabxml import set_text
                set_text(el, self.temp_unit.currentText())


class _CwInitialPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        self.fluid_temp = QDoubleSpinBox(self)
        self.fluid_temp.setRange(-273.15, 1.0e6)
        self.fluid_temp.setDecimals(2)
        _pair_row(lay, "Initial temperature of fluid", self.fluid_temp, "C")
        self.solid_temp = QDoubleSpinBox(self)
        self.solid_temp.setRange(-273.15, 1.0e6)
        self.solid_temp.setDecimals(2)
        _pair_row(lay, "Initial temperature of a solid part",
                  self.solid_temp, "C")
        btn = QPushButton("New initial value condition", self)
        btn.clicked.connect(self._new_condition)
        lay.addWidget(btn)
        lay.addStretch(1)
        try:
            self.fluid_temp.setValue(float(self.model.project_value(
                "ambient_temperature", "20")))
        except ValueError:
            pass
        try:
            self.solid_temp.setValue(float(self.model.project_value(
                "solid_init_temperature", "20")))
        except ValueError:
            pass

    def _new_condition(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Condition (Initial Value)", "Condition name:",
            text="FluidTemp1")
        if not ok or not name.strip():
            return
        self.model.upsert_value("initial", name.strip(), [
            ("type", "TEMP", None),
            ("param", f"{self.fluid_temp.value():g}", "C"),
        ])
        ar = self.model.analysis_region()
        if ar is not None:
            from cabxml import _first
            n = _first(ar, "name")
            target = n.text.strip() if n is not None and n.text else "Domain"
            self.model.bind_condition("analysis", target, name.strip())
        self._log(f"Initial Condition: created '{name.strip()}'.")

    def apply(self) -> None:
        self.model.set_project_value(
            "ambient_temperature", f"{self.fluid_temp.value():g}")
        self.model.set_project_value(
            "solid_init_temperature", f"{self.solid_temp.value():g}")

    def _log(self, msg: str) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg)


class _BoundaryPageBase(QWidget if _HAS_GUI_DEPS else object):
    """Common region list + New condition machinery for the BC pages."""

    def __init__(self, model: StpreModel, value_type: str):
        super().__init__()
        self.model = model
        self.value_type = value_type
        self._faces = ["Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"]
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Regions (computational domain faces)", self))
        self.region = QListWidget(self)
        self.region.addItems(self._faces)
        lay.addWidget(self.region, 1)
        row = QHBoxLayout()
        self.btn_new = QPushButton("New", self)
        self.btn_new.clicked.connect(self._new)
        row.addWidget(self.btn_new)
        row.addStretch(1)
        lay.addLayout(row)
        self.current = QLabel("", self)
        self.current.setWordWrap(True)
        self.current.setStyleSheet("color: #555;")
        lay.addWidget(self.current)
        self.region.currentRowChanged.connect(self._show_current)

    def _show_current(self) -> None:
        face = self._current_face()
        vname = self.model.condition_value("region", face)
        self.current.setText(
            f"{face}: {vname or '(no condition set)'}")

    def _current_face(self) -> str:
        row = self.region.currentRow()
        return self._faces[row] if 0 <= row < len(self._faces) else "Xmin"

    def _new(self) -> None:
        raise NotImplementedError

    def _log(self, msg: str) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg)


class _CwFlowBoundaryPage(_BoundaryPageBase):
    def __init__(self, model: StpreModel):
        super().__init__(model, "flux")
        self._show_current()

    def _build_opening_widgets(self) -> QDialog:
        """Build the [Condition (Opening)] dialog widgets (test-friendly:
        no exec_)."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Condition (Opening) on {self._current_face()}")
        lay = QVBoxLayout(dlg)
        self._cname = QLineEdit(dlg)
        _row(lay, "Condition name", self._cname)
        self._ctype = QComboBox(dlg)
        self._ctype.addItems(["Fixed velocity", "Fixed static pressure",
                              "Natural outflow"])
        _row(lay, "Condition type", self._ctype)
        self._vel = {a: QDoubleSpinBox() for a in "xyz"}
        for a in "xyz":
            self._vel[a].setRange(-1.0e6, 1.0e6)
            self._vel[a].setDecimals(3)
            _row(lay, f"Velocity component {a.upper()} (m/s)", self._vel[a])
        self._temp = QDoubleSpinBox()
        self._temp.setRange(-273.15, 1.0e6)
        self._temp.setDecimals(2)
        _row(lay, "Inflow temperature (C)", self._temp)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        return dlg

    def _new(self) -> None:
        dlg = self._build_opening_widgets()
        if dlg.exec_():
            self._commit(self._current_face())

    def _commit(self, face: str) -> None:
        name = self._cname.text().strip() or f"Opening_{face}"
        ctype = self._ctype.currentIndex()
        kind = ("fixed_vel" if ctype == 0
                else "total_pres" if ctype == 1 else "out")
        children = [("kind", kind, None)]
        if kind == "fixed_vel":
            children.append((
                "velocity", ",".join(f"{self._vel[a].value():g}"
                                     for a in "xyz"), None))
            children.append(("temperature",
                             f"{self._temp.value():g}", "C"))
        elif kind == "total_pres":
            children.append(("pressure", "0", "Pa"))
            children.append(("temperature",
                             f"{self._temp.value():g}", "C"))
        children += [("turbulence_type", "none", None),
                     ("panel_option", "none", None)]
        self.model.upsert_value("flux", name, children)
        self.model.bind_condition("region", face, name)
        self._show_current()
        self._log(f"Flow Boundary: {face} <- '{name}' ({kind})")

    def apply(self) -> None:
        pass


class _CwWallBoundaryPage(_BoundaryPageBase):
    def __init__(self, model: StpreModel):
        super().__init__(model, "wall")
        self._show_current()

    def _new(self) -> None:
        face = self._current_face()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Condition (Wall) on {face}")
        lay = QVBoxLayout(dlg)
        name = QLineEdit(f"Wall_{face}", dlg)
        _row(lay, "Condition name", name)
        kind = QComboBox(dlg)
        kind.addItems(["Freeslip", "Noslip", "Rough"])
        _row(lay, "Wall condition", kind)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        if dlg.exec_():
            k = ("free_slip" if kind.currentIndex() == 0
                 else "no_slip" if kind.currentIndex() == 1 else "rough")
            self.model.upsert_value("wall", name.text().strip(), [
                ("kind", k, None), ("option", "1", None)])
            self.model.bind_condition("region", face, name.text().strip())
            self._show_current()
            self._log(f"Wall Boundary: {face} <- '{name.text().strip()}'"
                      f" ({k})")

    def apply(self) -> None:
        pass


class _CwThermalBoundaryPage(_BoundaryPageBase):
    def __init__(self, model: StpreModel):
        super().__init__(model, "heat_transfer")
        self._show_current()

    def _new(self) -> None:
        face = self._current_face()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Condition (Heat transfer) on {face}")
        lay = QVBoxLayout(dlg)
        name = QLineEdit(f"Heat_{face}", dlg)
        _row(lay, "Condition name", name)
        kind = QComboBox(dlg)
        kind.addItems(["Adiabatic", "Fixed temperature",
                       "Heat transfer coefficient"])
        _row(lay, "Thermal boundary", kind)
        temp = QDoubleSpinBox()
        temp.setRange(-273.15, 1.0e6)
        temp.setDecimals(2)
        _row(lay, "External temperature (C)", temp)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        b.addWidget(ok)
        b.addWidget(cancel)
        lay.addLayout(b)
        if dlg.exec_():
            k = ("adiabatic" if kind.currentIndex() == 0
                 else "fixed" if kind.currentIndex() == 1 else "transfer")
            children = [("kind", k, None),
                        ("temperature", f"{temp.value():g}", "C")]
            if k == "transfer":
                children.append(("transfer", "10", None))
            children.append(("use", "2", None))
            self.model.upsert_value("heat_transfer", name.text().strip(),
                                    children)
            self.model.bind_condition("region", face, name.text().strip())
            self._show_current()
            self._log(f"Thermal Boundary: {face} <- "
                      f"'{name.text().strip()}' ({k})")

    def apply(self) -> None:
        pass


class _CwSymmetricalPage(_BoundaryPageBase):
    def __init__(self, model: StpreModel):
        super().__init__(model, "wall")
        self._show_current()

    def _new(self) -> None:
        face = self._current_face()
        name = f"Symmetry_{face}"
        # symmetrical = free-slip wall + adiabatic + emissivity 0
        self.model.upsert_value("wall", name, [
            ("kind", "free_slip", None), ("option", "1", None)])
        self.model.bind_condition("region", face, name)
        heat = f"SymmetryHeat_{face}"
        self.model.upsert_value("heat_transfer", heat, [
            ("kind", "adiabatic", None),
            ("temperature", "20", "C"), ("use", "2", None)])
        self.model.bind_condition("region", face, heat)
        self._show_current()
        self._log(f"Symmetrical Boundary: {face} <- '{name}' + '{heat}' "
                  f"(free-slip + adiabatic, emissivity 0.0)")

    def apply(self) -> None:
        pass


class _CwControlPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        self.transient = QRadioButton("Transient analysis", self)
        self.steady = QRadioButton("Steady-state analysis", self)
        st = QHBoxLayout()
        st.addWidget(self.transient)
        st.addWidget(self.steady)
        st.addStretch(1)
        lay.addLayout(st)

        cyc = QGroupBox("Cycle", self)
        cl = QVBoxLayout(cyc)
        row = QHBoxLayout()
        row.addWidget(QLabel("Start cycle no.", cyc))
        self.start_cycle = QDoubleSpinBox(cyc)
        self.start_cycle.setDecimals(0)
        self.start_cycle.setRange(1, 1.0e9)
        row.addWidget(self.start_cycle)
        row.addWidget(QLabel("Last cycle no.", cyc))
        self.last_cycle = QDoubleSpinBox(cyc)
        self.last_cycle.setDecimals(0)
        self.last_cycle.setRange(1, 1.0e9)
        row.addWidget(self.last_cycle)
        cl.addLayout(row)
        lay.addWidget(cyc)

        ts = QGroupBox("Time step", self)
        tsl = QVBoxLayout(ts)
        self.ts_fixed = QRadioButton("Fixed time step", ts)
        self.ts_var = QRadioButton(
            "Variable time step (automatically calculated)", ts)
        tsl.addWidget(self.ts_fixed)
        tsl.addWidget(self.ts_var)
        self.init_dt = QDoubleSpinBox(ts)
        self.init_dt.setDecimals(6)
        self.init_dt.setRange(1.0e-9, 1.0e9)
        _pair_row(tsl, "Initial time step", self.init_dt, "s")
        self.courant = QDoubleSpinBox(ts)
        self.courant.setDecimals(2)
        self.courant.setRange(0.01, 100.0)
        _pair_row(tsl, "Courant number", self.courant)
        lay.addWidget(ts)
        lay.addStretch(1)
        self._load()

    def _load(self) -> None:
        calc = self.model.analysis_set_value("calculation", "steady")
        self.transient.setChecked(calc == "transient")
        self.steady.setChecked(calc != "transient")
        cycle = self.model.analysis_set_value("cycle", "1,100").split(",")
        try:
            self.start_cycle.setValue(float(cycle[0]))
            self.last_cycle.setValue(float(cycle[1]))
        except (ValueError, IndexError):
            pass
        try:
            self.init_dt.setValue(float(
                self.model.analysis_set_value("init_time_step", "0.01")))
            self.courant.setValue(float(
                self.model.analysis_set_value("courant", "0.9")))
        except ValueError:
            pass
        self.ts_var.setChecked(True)
        self.ts_fixed.setChecked(False)

    def apply(self) -> None:
        self.model.set_cycles(
            int(self.start_cycle.value()), int(self.last_cycle.value()),
            transient=self.transient.isChecked())
        self.model.set_analysis_set_value(
            "init_time_step", f"{self.init_dt.value():g}")
        self.model.set_analysis_set_value(
            "courant", f"{self.courant.value():g}")


class _CwFilePage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        self.fname = QLineEdit(model.project_name, self)
        _pair_row(lay, "File Name", self.fname)
        note = QLabel("Field file output timing (phase 1: informational).",
                      self)
        note.setStyleSheet("color: #555;")
        lay.addWidget(note)
        self.out_cycle = QDoubleSpinBox(self)
        self.out_cycle.setDecimals(0)
        self.out_cycle.setRange(1, 1.0e9)
        _pair_row(lay, "Field file output cycle", self.out_cycle)
        lay.addStretch(1)

    def apply(self) -> None:
        name = self.fname.text().strip()
        if name:
            self.model.set_project_name(name)


class _CwConditionListPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self, model: StpreModel):
        super().__init__()
        self.model = model
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Condition", "Type", "Target"])
        self.tree.setRootIsDecorated(False)
        lay.addWidget(self.tree, 1)
        note = QLabel("Right-click a condition to Rename / Copy + add / "
                      "Delete.  Deleting removes the value definition.",
                      self)
        note.setStyleSheet("color: #555;")
        lay.addWidget(note)
        from PyQt5.QtCore import Qt as _Qt
        self.tree.setContextMenuPolicy(_Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)

    def refresh(self) -> None:
        self.tree.clear()
        values = [v for v in self.model.values()
                  if v.attrib.get("type")]
        for v in values:
            name = ""
            for ch in v:
                if ch.tag == "name":
                    name = ch.text.strip() if ch.text else ""
                    break
            targets = []
            for c in self.model.conditions():
                tname = None
                for ch in c:
                    if ch.tag in ("region", "parts", "analysis"):
                        tname = ch.text.strip() if ch.text else ""
                val = None
                for ch in c:
                    if ch.tag == "value":
                        val = ch.text.strip() if ch.text else ""
                if val == name and tname:
                    targets.append(tname)
            QTreeWidgetItem(self.tree, [
                name, v.attrib.get("type", ""), ", ".join(targets)])
        self.tree.resizeColumnToContents(0)

    def _menu(self, pos) -> None:
        from PyQt5.QtWidgets import QMenu
        item = self.tree.itemAt(pos)
        if item is None:
            return
        name = item.text(0)
        menu = QMenu(self)
        menu.addAction("Rename", lambda: self._rename(name))
        menu.addAction("Copy + add", lambda: self._copy(name))
        menu.addAction("Delete", lambda: self._delete(name))
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _rename(self, old: str) -> None:
        new, ok = QtWidgets.QInputDialog.getText(
            self, "Rename", "New name:", text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        val = self.model.find_value(old)
        if val is not None:
            for ch in val:
                if ch.tag == "name":
                    from cabxml import set_text
                    set_text(ch, new.strip())
        for c in self.model.conditions():
            for ch in c:
                if ch.tag == "value" and (ch.text or "").strip() == old:
                    from cabxml import set_text
                    set_text(ch, new.strip())
        self.refresh()

    def _copy(self, old: str) -> None:
        val = self.model.find_value(old)
        if val is None:
            return
        import xml.etree.ElementTree as ET
        new_name = old + "_copy"
        copy = ET.fromstring(ET.tostring(val))
        for ch in copy:
            if ch.tag == "name":
                ch.text = f" {new_name} "
        self.model.root.append(copy)
        self.refresh()

    def _delete(self, name: str) -> None:
        val = self.model.find_value(name)
        if val is not None:
            self.model.root.remove(val)
        for c in list(self.model.conditions()):
            for ch in c:
                if ch.tag == "value" and (ch.text or "").strip() == name:
                    self.model.root.remove(c)
                    break
        self.refresh()


class _CwConfirmPage(QWidget if _HAS_GUI_DEPS else object):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        lay.addWidget(self.text, 1)
        brow = QHBoxLayout()
        clip = QPushButton("Clipboard", self)
        clip.clicked.connect(self._clipboard)
        fout = QPushButton("File Output", self)
        fout.clicked.connect(self._file_output)
        brow.addWidget(clip)
        brow.addWidget(fout)
        brow.addStretch(1)
        lay.addLayout(brow)

    def set_summary(self, text: str) -> None:
        self.text.setPlainText(text)

    def _clipboard(self) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(self.text.toPlainText())
        except Exception:
            pass

    def _file_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "File Output", "condition_settings.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.text.toPlainText())


class ConditionWizard(WizardBase):
    """[Wizard] - [Condition Setting]: STpre Condition Wizard subset.

    Navigation tree mirrors the STpreCwiz page list; undefined steps stay
    grey (unchecked), defined steps turn orange (checked) as you work
    through them.
    """

    def __init__(self, model: StpreModel, props: Optional[PropertyModel],
                 parent=None):
        super().__init__("Condition Setting", parent=parent, show_tree=True)
        self.model = model
        self.props = props
        self._snapshot = model.doc.serialize()

        self.p_analysis = _CwAnalysisTypesPage(model)
        self.p_basic = _CwBasicSettingsPage(model)
        self.p_fluid = _CwFluidRegionPage(model, props)
        self.p_flow = _CwFlowPage(model)
        self.p_heat = _CwHeatPage(model)
        self.p_initial = _CwInitialPage(model)
        self.p_bc_flow = _CwFlowBoundaryPage(model)
        self.p_bc_wall = _CwWallBoundaryPage(model)
        self.p_bc_thermal = _CwThermalBoundaryPage(model)
        self.p_bc_symm = _CwSymmetricalPage(model)
        self.p_control = _CwControlPage(model)
        self.p_file = _CwFilePage(model)
        self.p_list = _CwConditionListPage(model)
        self.p_confirm = _CwConfirmPage()

        page_map = {
            "analysis": self.p_analysis, "basic": self.p_basic,
            "fluid": self.p_fluid, "flow": self.p_flow,
            "heat": self.p_heat, "initial": self.p_initial,
            "bc": None,  # nav-group node without its own page
            "bc_flow": self.p_bc_flow, "bc_wall": self.p_bc_wall,
            "bc_thermal": self.p_bc_thermal, "bc_symm": self.p_bc_symm,
            "control": self.p_control, "file": self.p_file,
            "condlist": self.p_list, "confirm": self.p_confirm,
        }
        for key, title, parent_key in _CW_PAGES:
            self._add_page(key, title, page_map[key], parent_key)
        # keep the steady/transient choice in sync between Analysis Types
        # and Analysis Control pages
        self.p_analysis.transient.toggled.connect(
            self.p_control.transient.setChecked)
        self.p_control.transient.toggled.connect(
            self.p_analysis.transient.setChecked)
        self.p_analysis.steady.toggled.connect(
            self.p_control.steady.setChecked)
        self.p_control.steady.toggled.connect(
            self.p_analysis.steady.setChecked)
        self._mark_defined("analysis", True)
        self._show_page(0)

    def _show_page(self, idx: int) -> None:
        key = self._keys[idx]
        if key == "condlist":
            self.p_list.refresh()
        elif key == "confirm":
            self.p_confirm.set_summary(self._summary())
        super()._show_page(idx)

    def _summary(self) -> str:
        m = self.model
        lines = [
            f"Project: {m.project_name}",
            f"Fluid region material: {m.domain_material() or '-'}",
            f"Analysis: heat={m.analysis_set_value('heat')}, "
            f"turbulence={m.analysis_set_value('turbulence')}, "
            f"mode={m.analysis_set_value('calculation')}",
            f"Gravity: {m.analysis_set_value('grav_vec')} "
            f"x {m.analysis_set_value('grav_abs')} m/s2",
            f"Ambient temperature: "
            f"{m.project_value('ambient_temperature')} C",
            "",
            "Conditions:",
        ]
        for v in m.values():
            if not v.attrib.get("type"):
                continue
            name = ""
            for ch in v:
                if ch.tag == "name":
                    name = ch.text.strip() if ch.text else ""
            lines.append(f"  [{v.attrib.get('type')}] {name}")
        return "\n".join(lines)

    def _on_finish(self) -> None:
        page_map = {
            "analysis": self.p_analysis, "basic": self.p_basic,
            "fluid": self.p_fluid, "flow": self.p_flow,
            "heat": self.p_heat, "initial": self.p_initial,
            "bc_flow": self.p_bc_flow, "bc_wall": self.p_bc_wall,
            "bc_thermal": self.p_bc_thermal, "bc_symm": self.p_bc_symm,
            "control": self.p_control, "file": self.p_file,
        }
        for key, page in page_map.items():
            if hasattr(page, "apply"):
                page.apply()
            self._mark_defined(key, True)
        self.p_list.refresh()
        self._rebuild()
        self._log("Condition Wizard finished; conditions written to the "
                  "project (save the cab to persist).")

    def _on_cancel(self) -> None:
        import cabxml
        self.model.doc = cabxml.StpreDoc(self._snapshot)


def initial_wizard_dialog(model: StpreModel, props, cad_meshes, parent=None
                          ) -> InitialWizard:
    return InitialWizard(model, props, cad_meshes, parent)


def condition_wizard_dialog(model: StpreModel, props, parent=None
                            ) -> ConditionWizard:
    return ConditionWizard(model, props, parent)

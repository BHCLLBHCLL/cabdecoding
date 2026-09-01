"""F3: non-Condition dialogs from the Pre_eng manual (§25 batch).

Seven dialogs that STpre exposes outside the Condition Wizard:

- Chemical Material — species property rows (viscosity / thermal
  conductivity / mutual diffusion coefficient with temperature-dependent
  coefficient records);
- Compressible Fluid — viscosity definition mode (direct / script /
  property table);
- Cloth Model Characteristics — Choi / Rheology calculation model with
  spring constants and damping coefficients;
- Check Time Step — read-only viewer of the transient time-step settings
  (geometric-ratio cycles);
- Calculate conductivity from heat transmission — U, h1, h2, thickness
  -> equivalent thermal conductivity;
- Calculation of Heat Transfer Coefficient — conductivity + thickness
  -> heat transfer coefficient;
- Calculation of Humidity Absorption and Desorption Characteristics —
  fourth-order equilibrium moisture content (phi-h) polynomial.

The dialogs persist their settings through ``analysis_set`` records so a
save/reload round-trip restores them.
"""
from __future__ import annotations

from typing import Optional

if __import__("importlib").util.find_spec("PyQt5") is not None:
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
        QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
        QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
        QVBoxLayout, QWidget)
    _HAS_GUI = True
else:  # pragma: no cover - headless import
    _HAS_GUI = False

    class _Stub:  # minimal placeholders so class bodies parse
        def __init__(self, *a, **k):
            pass
    QDialog = _Stub
    QWidget = object


def _row(lay, label, widget) -> None:
    if isinstance(lay, QFormLayout):
        lay.addRow(QLabel(label), widget)
        return
    row = QHBoxLayout()
    row.addWidget(QLabel(label))
    row.addWidget(widget, 1)
    lay.addLayout(row)


def _num_edit(value: float, lo: float = -1e30, hi: float = 1e30,
              dec: int = 6):
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(dec)
    sb.setValue(value)
    return sb


def _button_box(dlg: QDialog) -> None:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    lay = dlg.layout()
    lay.addWidget(box)


class _ModelDialog(QDialog):
    """Shared chrome: builds around a model reference + Apply/Close."""

    def __init__(self, model, title: str, parent=None):
        if not _HAS_GUI:
            raise RuntimeError("PyQt5 not available")
        super().__init__(parent)
        self.model = model
        self.setWindowTitle(title)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 8)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.accepted.connect(self.apply_settings)
        buttons.rejected.connect(self.close)
        self._buttons = buttons

    def _finish(self) -> None:
        self._lay.addWidget(self._buttons)

    def apply_settings(self) -> None:
        """Default no-op for read-only dialogs."""


class ChemicalMaterialDialog(_ModelDialog):
    """[Chemical Material] — per-species property coefficient records."""

    _KINDS = ("viscosity", "thermal_conductivity",
              "mutual_diffusion_coefficient")

    def __init__(self, model, parent=None):
        super().__init__(model, "Chemical Material", parent)
        self._lay.addWidget(QLabel(
            "Chemical species properties with temperature-dependent "
            "coefficient records (a1,a2,t1[,a3,a4,t2,...]).", self))
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(
            ["Species", "Property", "Coefficients", "Unit"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.sp_name = QLineEdit(self)
        _row(row, "Species", self.sp_name)
        self._lay.addLayout(row)
        row2 = QHBoxLayout()
        self.sp_kind = QComboBox(self)
        self.sp_kind.addItems(list(self._KINDS))
        _row(row2, "Property", self.sp_kind)
        self._lay.addLayout(row2)
        row3 = QHBoxLayout()
        self.sp_coeffs = QLineEdit(self)
        _row(row3, "Coefficients (a1,a2,t1,...)", self.sp_coeffs)
        self._lay.addLayout(row3)
        add_row = QHBoxLayout()
        btn_add = QPushButton("Add / update", self)
        btn_add.clicked.connect(self._add_row)
        add_row.addWidget(btn_add)
        btn_del = QPushButton("Delete selected", self)
        btn_del.clicked.connect(self._delete_selected)
        add_row.addWidget(btn_del)
        add_row.addStretch(1)
        self._lay.addLayout(add_row)
        self._finish()
        self._load()

    # storage: analysis_set "chemical_material" = "species|kind|coeffs;..."

    @staticmethod
    def _dump(records) -> str:
        return ";".join(
            f"{r[0]}|{r[1]}|{r[2]}" for r in records)

    @staticmethod
    def _load_records(model) -> list:
        raw = model.analysis_set_value("chemical_material", "")
        out = []
        for rec in raw.split(";"):
            bits = [b.strip() for b in rec.split("|")]
            if len(bits) == 3 and all(bits):
                out.append(tuple(bits))
        return out

    def records(self) -> list:
        rows = []
        for r in range(self.table.rowCount()):
            vals = [(self.table.item(r, c).text() if self.table.item(r, c)
                     else "") for c in range(3)]
            if vals[0] and vals[1]:
                rows.append((vals[0], vals[1], vals[2]))
        return rows

    def _add_row(self) -> None:
        name = self.sp_name.text().strip()
        coeffs = self.sp_coeffs.text().strip()
        if not name or not coeffs:
            return
        # replace an existing (species, property) row
        for r in range(self.table.rowCount()):
            it0 = self.table.item(r, 0)
            it1 = self.table.item(r, 1)
            if it0 and it1 and it0.text() == name \
                    and it1.text() == self.sp_kind.currentText():
                self.table.setItem(r, 2, QTableWidgetItem(coeffs))
                break
        else:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate((name, self.sp_kind.currentText(),
                                   coeffs)):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def _delete_selected(self) -> None:
        rows = sorted({r.row() for r in self.table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _load(self) -> None:
        for species, kind, coeffs in self._load_records(self.model):
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate((species, kind, coeffs)):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def apply_settings(self) -> None:
        self.model.set_analysis_set_value(
            "chemical_material", self._dump(self.records()))


class CompressibleFluidDialog(_ModelDialog):
    """[Compressible Fluid] — viscosity definition (direct/script/table)."""

    _MODES = ("direct", "script", "property_table")

    def __init__(self, model, parent=None):
        super().__init__(model, "Compressible Fluid", parent)
        form = QFormLayout()
        self.mode = QComboBox(self)
        self.mode.addItems(["Direct value", "Script", "Property table"])
        form.addRow("Viscosity", self.mode)
        self.viscosity = _num_edit(1.8e-5, 0.0, 1.0, 12)
        form.addRow("Viscosity coefficient (Pa.s)", self.viscosity)
        self.script = QLineEdit(self)
        form.addRow("Script name", self.script)
        self._lay.addLayout(form)
        self._finish()
        self._load()

    def _load(self) -> None:
        mode = self.model.analysis_set_value("compressible_mode", "direct")
        self.mode.setCurrentIndex(
            self._MODES.index(mode) if mode in self._MODES else 0)
        try:
            self.viscosity.setValue(float(
                self.model.analysis_set_value(
                    "compressible_viscosity", "1.8e-5")))
        except ValueError:
            pass
        self.script.setText(
            self.model.analysis_set_value("compressible_script", ""))

    def apply_settings(self) -> None:
        mode = self._MODES[self.mode.currentIndex()]
        self.model.set_analysis_set_value("compressible_mode", mode)
        self.model.set_analysis_set_value(
            "compressible_viscosity", f"{self.viscosity.value():g}")
        self.model.set_analysis_set_value(
            "compressible_script", self.script.text().strip())


class ClothModelDialog(_ModelDialog):
    """[Cloth Model Characteristics] — Choi / Rheology model params."""

    def __init__(self, model, parent=None):
        super().__init__(model, "Cloth Model Characteristics", parent)
        form = QFormLayout()
        self.calc_model = QComboBox(self)
        self.calc_model.addItems(["Choi model", "Rheology model"])
        form.addRow("Calculation model", self.calc_model)
        self.stretch_k = _num_edit(1.0, 0.0, 1e9, 6)
        form.addRow("Stretch spring constant", self.stretch_k)
        self.stretch_c = _num_edit(1.0, 0.0, 1e9, 6)
        form.addRow("Stretch damping coefficient", self.stretch_c)
        self.bend_k = _num_edit(1.0, 0.0, 1e9, 6)
        form.addRow("Bending spring constant", self.bend_k)
        self.bend_c = _num_edit(1.0, 0.0, 1e9, 6)
        form.addRow("Bending damping coefficient", self.bend_c)
        self._lay.addLayout(form)
        self._finish()
        self._load()

    def _load(self) -> None:
        model = self.model.analysis_set_value("cloth_model", "choi")
        self.calc_model.setCurrentIndex(
            1 if model == "rheology" else 0)
        for key, widget in (
                ("cloth_stretch_k", self.stretch_k),
                ("cloth_stretch_c", self.stretch_c),
                ("cloth_bend_k", self.bend_k),
                ("cloth_bend_c", self.bend_c)):
            try:
                widget.setValue(float(
                    self.model.analysis_set_value(key, "1")))
            except ValueError:
                pass

    def apply_settings(self) -> None:
        self.model.set_analysis_set_value(
            "cloth_model",
            "rheology" if self.calc_model.currentIndex() == 1 else "choi")
        for key, widget in (
                ("cloth_stretch_k", self.stretch_k),
                ("cloth_stretch_c", self.stretch_c),
                ("cloth_bend_k", self.bend_k),
                ("cloth_bend_c", self.bend_c)):
            self.model.set_analysis_set_value(
                key, f"{widget.value():g}")


class CheckTimeStepDialog(_ModelDialog):
    """[Check Time Step] — read-only viewer of the transient cycle
    settings (STpre shows the geometric-ratio cycle list)."""

    def __init__(self, model, parent=None):
        super().__init__(model, "Check Time Step", parent)
        self._lay.addWidget(QLabel(
            "Time step settings (from Steady-State Analysis / Cycle).",
            self))
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(
            ["Type", "Start cycle", "Last cycle", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._lay.addWidget(self.table, 1)
        self._finish()
        self._load()

    def _load(self) -> None:
        rows = self.build_rows(self.model)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))

    @staticmethod
    def build_rows(model) -> list:
        calc = model.analysis_set_value("calculation", "")
        start = model.analysis_set_value("cycle", "").split(":")[0] \
            or "1"
        last = model.analysis_set_value("cycle", "").split(":")[-1] \
            or "1"
        dt = model.analysis_set_value("init_time_step", "")
        dt_type = model.analysis_set_value("time_step_type", "")
        detail = dt or "—"
        if dt_type:
            detail = f"{dt} ({dt_type})"
        return [(("Transient" if calc == "transient" else "Steady-state"),
                 start, last, detail)]


class CalculateConductivityDialog(QDialog):
    """[Calculate conductivity from heat transmission] — U, h1, h2,
    thickness -> equivalent thermal conductivity (pure calculator)."""

    def __init__(self, parent=None):
        if not _HAS_GUI:
            raise RuntimeError("PyQt5 not available")
        super().__init__(parent)
        self.setWindowTitle(
            "Calculate conductivity from heat transmission")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.heat_trans = _num_edit(1.0, 1e-12, 1e9, 8)
        _row(form, "Heat transmission U (W/(m2.K))", self.heat_trans)
        self.h1 = _num_edit(10.0, 1e-12, 1e9, 8)
        _row(form, "Heat transfer coefficient 1", self.h1)
        self.h2 = _num_edit(10.0, 1e-12, 1e9, 8)
        _row(form, "Heat transfer coefficient 2", self.h2)
        self.thickness = _num_edit(0.01, 1e-12, 100.0, 8)
        _row(form, "Thickness (m)", self.thickness)
        lay.addLayout(form)
        out = QHBoxLayout()
        out.addWidget(QLabel("Equivalent thermal conductivity (W/(m.K))"))
        self.result = QLineEdit(self)
        self.result.setReadOnly(True)
        out.addWidget(self.result, 1)
        lay.addLayout(out)
        btn = self._calc_button()
        lay.addWidget(btn)
        _button_box(self)

    def _calc_button(self):
        from PyQt5.QtWidgets import QPushButton
        btn = QPushButton("Calculate", self)
        btn.clicked.connect(self.calculate)
        return btn

    @staticmethod
    def compute(u: float, h1: float, h2: float, thickness: float
                ) -> Optional[float]:
        """lambda = t / (1/U - 1/h1 - 1/h2); None when non-physical."""
        denom = 1.0 / u - 1.0 / h1 - 1.0 / h2
        if denom <= 0 or thickness <= 0:
            return None
        return thickness / denom

    def calculate(self) -> None:
        lam = self.compute(self.heat_trans.value(), self.h1.value(),
                           self.h2.value(), self.thickness.value())
        self.result.setText("" if lam is None else f"{lam:.8g}")


class HeatTransferCoefficientDialog(QDialog):
    """[Calculation of Heat Transfer Coefficient] — conductivity +
    thickness -> heat transfer coefficient h = lambda / t."""

    def __init__(self, parent=None):
        if not _HAS_GUI:
            raise RuntimeError("PyQt5 not available")
        super().__init__(parent)
        self.setWindowTitle("Calculation of Heat Transfer Coefficient")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.mat_name = QLineEdit(self)
        _row(form, "Material", self.mat_name)
        self.conductivity = _num_edit(1.0, 1e-12, 1e6, 8)
        _row(form, "Thermal conductivity (W/(m.K))", self.conductivity)
        self.thickness = _num_edit(0.001, 1e-12, 100.0, 8)
        _row(form, "Thickness (m)", self.thickness)
        lay.addLayout(form)
        out = QHBoxLayout()
        out.addWidget(QLabel("Heat transfer coefficient (W/(m2.K))"))
        self.result = QLineEdit(self)
        self.result.setReadOnly(True)
        out.addWidget(self.result, 1)
        lay.addLayout(out)
        btn = QPushButton("Calculate", self)
        btn.clicked.connect(self.calculate)
        lay.addWidget(btn)
        _button_box(self)

    @staticmethod
    def compute(conductivity: float, thickness: float
                ) -> Optional[float]:
        if thickness <= 0:
            return None
        return conductivity / thickness

    def calculate(self) -> None:
        h = self.compute(self.conductivity.value(),
                         self.thickness.value())
        self.result.setText("" if h is None else f"{h:.8g}")


class HumidityAbsorptionDialog(_ModelDialog):
    """[Calculation of Humidity Absorption and Desorption
    Characteristics] — fourth-order phi-h polynomial coefficients."""

    def __init__(self, model, parent=None):
        super().__init__(model,
                         "Calculation of Humidity Absorption and "
                         "Desorption Characteristics", parent)
        self._lay.addWidget(QLabel(
            "Fourth order polynomial equation of the equilibrium "
            "moisture content curve (phi-h): "
            "phi = a0 + a1*h + a2*h^2 + a3*h^3 + a4*h^4", self))
        form = QFormLayout()
        self.coeffs = []
        for i in range(5):
            sb = QDoubleSpinBox(self)
            sb.setRange(-1e9, 1e9)
            sb.setDecimals(8)
            sb.setValue(0.0)
            self.coeffs.append(sb)
            form.addRow(f"a{i}", sb)
        self._lay.addLayout(form)
        self._finish()
        self._load()

    def _load(self) -> None:
        raw = self.model.analysis_set_value("humidity_phih_coeffs", "")
        for i, tok in enumerate(raw.split(",")[:5]):
            try:
                self.coeffs[i].setValue(float(tok))
            except ValueError:
                pass

    def apply_settings(self) -> None:
        self.model.set_analysis_set_value(
            "humidity_phih_coeffs",
            ",".join(f"{sb.value():.8g}" for sb in self.coeffs))

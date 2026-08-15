"""M5: STpre-style dialog framework for cab_gui.

Chrome reverse-engineered from Cradle STpre (CradleCFD2025.2):

- Screenshot of the [Edit Computational Domain] dialog (double-click
  ``Domain(cuboid)`` in [Layout of Parts]);
- Pre_eng manual dialog pages ([Edit Computational Domain] dialog,
  [Part] - [Cuboid], [Gridding] dialog, ...);
- UI label strings extracted from ``STpreParts_Bx64.dll``
  ("Calculate Part Region", "<Rectangular box subdomain>",
  "Reference coordinate system", "Attribute/Condition",
  "Output temperature to Monitor", "Configure...", ...).

Framework pieces (reusable for every other settings dialog):

- :class:`DialogHeader`     — icon + caption band on top of a dialog;
- :class:`ColorButton`      — ``[Color...]`` button with RGBA swatch;
- :class:`AttributePanel`   — the [Attribute/Condition] group:
  Attribute / Material+[Configure...] / Initial temperature /
  Heat source / Output temperature to Monitor / Virtual part;
- :class:`CuboidSchematic`  — isometric box sketch with axis arrows,
  drawn in the [Scale] group of STpre part dialogs;
- :class:`StpreDialogBase`  — common QDialog chrome: header, optional
  [Part Name + Color] row, left/right column body and the bottom
  button row ``[Preview] [Apply] [OK] [Cancel]``;
- :class:`MaterialListDialog` — [List of Materials] chooser opened by
  [Configure...].

Concrete dialogs:

- :class:`DomainDialog`   — [Edit Computational Domain], STpre layout;
- :class:`MeshBlockDialog` — [Mesh:block] RootBlock editor (Layout tree);
- :class:`PartDialog`     — [Part] - [Cuboid]-style part editor;
- :class:`GriddingDialog` — [Gridding] Basic Settings on the framework.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

import cab_domain
from cab_icons import AppIcons
from cabxml import PropertyModel, StpreModel

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QPolygon
    from PyQt5.QtCore import QPoint, QPointF
    from PyQt5.QtWidgets import (
        QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame,
        QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
        QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
        QSlider, QSpinBox, QTabWidget, QTextEdit, QTreeWidget,
        QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless environments
    _HAS_GUI_DEPS = False
    QtWidgets = None
    QDialog = object  # type: ignore
    QWidget = object  # type: ignore
    QGroupBox = object  # type: ignore

try:  # strip insignificant trailing zeros on coordinate spin boxes
    from cab_widgets import CoordSpinBox
    QDoubleSpinBox = CoordSpinBox
except Exception:
    pass

_UNIT_FACTOR = {"mm": 1.0, "m": 1000.0, "cm": 10.0}  # value -> mm


# ---------------------------------------------------------------- framework


class DialogHeader(QWidget if _HAS_GUI_DEPS else object):
    """Icon + bold caption + separator line (STpre dialog header band)."""

    def __init__(self, caption: str, icon: str = "domain", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(2, 2, 2, 0)
        if icon:
            ic = QLabel(self)
            ic.setPixmap(AppIcons.get(icon, 20).pixmap(20, 20))
            row.addWidget(ic)
        text = QLabel(caption, self)
        text.setStyleSheet("font-weight: bold; font-size: 12px;")
        row.addWidget(text)
        row.addStretch(1)
        lay.addLayout(row)
        self.caption_label = text
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)

    def set_caption(self, caption: str) -> None:
        self.caption_label.setText(caption)


class ColorButton(QWidget if _HAS_GUI_DEPS else object):
    """``[Color...]`` button followed by an RGBA color swatch."""

    color_changed = pyqtSignal(tuple)   # (r, g, b, a) 0-255

    def __init__(self, rgba=(0, 255, 255, 255), parent=None):
        super().__init__(parent)
        self._rgba = tuple(int(v) for v in rgba)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.button = QPushButton("Color...", self)
        self.button.clicked.connect(self._pick)
        lay.addWidget(self.button)
        self.swatch = QFrame(self)
        self.swatch.setFixedSize(22, 22)
        self.swatch.setFrameShape(QFrame.Box)
        self.swatch.setAutoFillBackground(True)
        lay.addWidget(self.swatch)
        self._refresh()

    def rgba(self) -> tuple[int, int, int, int]:
        return self._rgba

    def set_rgba(self, rgba) -> None:
        self._rgba = tuple(int(v) for v in rgba)
        self._refresh()

    def _refresh(self) -> None:
        r, g, b, _a = self._rgba
        self.swatch.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border: 1px solid #666;")

    def _pick(self) -> None:
        r, g, b, a = self._rgba
        col = QtWidgets.QColorDialog.getColor(
            QColor(r, g, b, a), self, "Color",
            QtWidgets.QColorDialog.ShowAlphaChannel)
        if col.isValid():
            self.set_rgba(col.getRgb())
            self.color_changed.emit(self._rgba)


class CuboidSchematic(QWidget if _HAS_GUI_DEPS else object):
    """Isometric cuboid sketch with origin dot + X/Y/Z axis arrows.

    Mimics the figure in the [Scale] group of STpre part/domain dialogs.
    """

    def __init__(self, parent=None, face="#cfe8a9"):
        super().__init__(parent)
        self.setMinimumSize(150, 120)
        self._face = QColor(face)

    def paintEvent(self, _ev) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        ox, oy = w * 0.52, h * 0.78          # origin (min corner, front)
        ux, uy = w * 0.36, 0.0               # X axis vector (right)
        vx, vy = 0.0, -h * 0.42              # Y axis vector (up)
        zx, zy = -w * 0.20, -h * 0.16        # Z axis vector (up-left)

        def pt(x, y, z):
            return QPointF(ox + x * ux + y * vx + z * zx,
                           oy + x * uy + y * vy + z * zy)

        c000 = pt(0, 0, 0)
        c100, c010, c001 = pt(1, 0, 0), pt(0, 1, 0), pt(0, 0, 1)
        c110, c101, c011 = pt(1, 1, 0), pt(1, 0, 1), pt(0, 1, 1)
        c111 = pt(1, 1, 1)

        edge = QPen(QColor("#4a6b2a"), 1.4)
        p.setPen(edge)
        # hidden faces first (back / right / top, darker)
        p.setBrush(QBrush(self._face.darker(112)))
        p.drawPolygon(QPolygon([c001.toPoint(), c101.toPoint(),
                                c111.toPoint(), c011.toPoint()]))
        p.drawPolygon(QPolygon([c100.toPoint(), c110.toPoint(),
                                c111.toPoint(), c101.toPoint()]))
        p.drawPolygon(QPolygon([c010.toPoint(), c011.toPoint(),
                                c111.toPoint(), c110.toPoint()]))
        # visible faces: left / bottom / front
        p.setBrush(QBrush(self._face.darker(106)))
        p.drawPolygon(QPolygon([c000.toPoint(), c001.toPoint(),
                                c011.toPoint(), c010.toPoint()]))
        p.drawPolygon(QPolygon([c000.toPoint(), c100.toPoint(),
                                c101.toPoint(), c001.toPoint()]))
        p.setBrush(QBrush(self._face))
        p.drawPolygon(QPolygon([c000.toPoint(), c100.toPoint(),
                                c110.toPoint(), c010.toPoint()]))
        # origin dot
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#d62728")))
        p.drawEllipse(c000, 3.5, 3.5)
        # axis arrows beyond the box
        p.setPen(QPen(QColor("#1f4ed8"), 1.6))
        p.setBrush(QBrush(QColor("#1f4ed8")))
        for start, tip, label, dx, dy in (
                (c100, pt(1.18, 0, 0), "X", -2, 12),
                (c010, pt(0, 1.30, 0), "Y", 2, -2),
                (c001, pt(0, 0, 1.40), "Z", -12, 10)):
            p.drawLine(start, tip)
            p.drawText(QPointF(tip.x() + dx, tip.y() + dy), label)
        p.end()


class FanSchematic(QWidget if _HAS_GUI_DEPS else object):
    """STpre Part(Fan) Scale figure: square frame + annulus + dimension labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w * 0.42, h * 0.48
        side = min(w, h) * 0.55
        # isometric-ish square (fan housing)
        ux, uy = side * 0.55, 0.0
        vx, vy = 0.0, -side * 0.55
        wx, wy = -side * 0.28, -side * 0.18

        def pt(a, b, c=0.0):
            return QPointF(cx + a * ux + b * vx + c * wx,
                           cy + a * uy + b * vy + c * wy)

        # front face square
        q = [pt(0, 0), pt(1, 0), pt(1, 1), pt(0, 1)]
        p.setPen(QPen(QColor("#333"), 1.4))
        p.setBrush(QBrush(QColor("#e8e8e8")))
        p.drawPolygon(QPolygon([pp.toPoint() for pp in q]))
        # depth edges
        p.setPen(QPen(QColor("#666"), 1.1))
        for a, b in ((pt(1, 0), pt(1, 0, 1)), (pt(1, 1), pt(1, 1, 1)),
                     (pt(0, 1), pt(0, 1, 1))):
            p.drawLine(a, b)
        p.drawLine(pt(1, 0, 1), pt(1, 1, 1))
        p.drawLine(pt(1, 1, 1), pt(0, 1, 1))
        # outer / inner circles on front face
        center = pt(0.5, 0.5)
        ro = side * 0.22
        ri = side * 0.10
        p.setBrush(QBrush(QColor("#f5f5f5")))
        p.setPen(QPen(QColor("#222"), 1.3))
        p.drawEllipse(center, ro, ro)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(center, ri, ri)
        # Thickness dimension (along depth)
        p.setPen(QPen(QColor("#1a5fd0"), 1.3))
        t0, t1 = pt(1.05, 0.15), pt(1.05, 0.15, 1)
        p.drawLine(t0, t1)
        p.drawText(QPointF(t1.x() - 8, t1.y() - 6), "Thickness")
        # Inner radius dimension
        p.drawLine(center, QPointF(center.x() + ri, center.y()))
        p.drawText(QPointF(center.x() + ri + 4, center.y() - 4),
                   "Inner radius")
        p.end()


class FanConditionPanel(QGroupBox if _HAS_GUI_DEPS else object):
    """STpre Part(Fan) right-hand [Condition] group (flow / PQ / location)."""

    def __init__(self, parent=None):
        super().__init__("Condition", parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(4)

        self.rb_rate = QRadioButton("Constant flow rate", self)
        self.rb_vel = QRadioButton("Constant velocity", self)
        self.rb_pq = QRadioButton("P-Q characteristics", self)
        self.rb_rate.setChecked(True)
        self._flow_group = QButtonGroup(self)
        for rb in (self.rb_rate, self.rb_vel, self.rb_pq):
            self._flow_group.addButton(rb)

        row1 = QHBoxLayout()
        row1.addWidget(self.rb_rate)
        self.rate = QDoubleSpinBox(self)
        self.rate.setRange(0, 1e9)
        self.rate.setDecimals(6)
        self.rate.setValue(1.0)
        self.rate_unit = QComboBox(self)
        self.rate_unit.addItems(["m3/s", "m3/min", "CFM"])
        row1.addWidget(self.rate)
        row1.addWidget(self.rate_unit)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self.rb_vel)
        self.vel = QDoubleSpinBox(self)
        self.vel.setRange(0, 1e6)
        self.vel.setDecimals(4)
        self.vel.setValue(1.0)
        self.vel_unit = QComboBox(self)
        self.vel_unit.addItems(["m/s", "km/h"])
        row2.addWidget(self.vel)
        row2.addWidget(self.vel_unit)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self.rb_pq)
        self.pq = QComboBox(self)
        self.pq.addItems(["@T:pq-curve0"])
        self.pq.setEditable(True)
        row3.addWidget(self.pq, 1)
        self.pq_btn = QPushButton("…", self)
        self.pq_btn.setFixedWidth(28)
        row3.addWidget(self.pq_btn)
        lay.addLayout(row3)

        loc = QGroupBox("Location of setting", self)
        ll = QVBoxLayout(loc)
        self.rb_internal = QRadioButton("Internal", loc)
        self.rb_boundary = QRadioButton(
            "On the computational domain boundary or obstacle face", loc)
        self.rb_internal.setChecked(True)
        self._loc_group = QButtonGroup(loc)
        self._loc_group.addButton(self.rb_internal)
        self._loc_group.addButton(self.rb_boundary)
        ll.addWidget(self.rb_internal)
        ll.addWidget(self.rb_boundary)
        lay.addWidget(loc)

        tip = QLabel(
            "These settings are applicable only when the fan is on the "
            "computational domain or obstacle face.", self)
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(tip)

        trow = QHBoxLayout()
        trow.addWidget(QLabel("Inflow temperature", self))
        self.inflow_temp = QDoubleSpinBox(self)
        self.inflow_temp.setRange(-273.15, 1e6)
        self.inflow_temp.setValue(20.0)
        trow.addWidget(self.inflow_temp)
        trow.addWidget(QLabel("C", self))
        lay.addLayout(trow)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("External pressure", self))
        self.ext_press = QDoubleSpinBox(self)
        self.ext_press.setRange(-1e9, 1e9)
        self.ext_press.setValue(0.0)
        self.press_unit = QComboBox(self)
        self.press_unit.addItems(["Pa", "atm", "bar"])
        prow.addWidget(self.ext_press)
        prow.addWidget(self.press_unit)
        lay.addLayout(prow)

        self.straight = QCheckBox("Flow-straightening effect", self)
        lay.addWidget(self.straight)
        srow = QHBoxLayout()
        self.rb_by_panel = QRadioButton("By Panel", self)
        self.rb_by_force = QRadioButton("By force", self)
        self.rb_by_panel.setChecked(True)
        self._str_group = QButtonGroup(self)
        self._str_group.addButton(self.rb_by_panel)
        self._str_group.addButton(self.rb_by_force)
        srow.addWidget(self.rb_by_panel)
        srow.addWidget(self.rb_by_force)
        lay.addLayout(srow)
        self.output_shape = QCheckBox("Output only part shape", self)
        self.virtual_chk = QCheckBox("Virtual part", self)
        lay.addWidget(self.output_shape)
        lay.addWidget(self.virtual_chk)
        lay.addStretch(1)

        def _sync():
            self.rate.setEnabled(self.rb_rate.isChecked())
            self.rate_unit.setEnabled(self.rb_rate.isChecked())
            self.vel.setEnabled(self.rb_vel.isChecked())
            self.vel_unit.setEnabled(self.rb_vel.isChecked())
            self.pq.setEnabled(self.rb_pq.isChecked())
            self.pq_btn.setEnabled(self.rb_pq.isChecked())
            on_bnd = self.rb_boundary.isChecked()
            self.inflow_temp.setEnabled(on_bnd)
            self.ext_press.setEnabled(on_bnd)
            self.press_unit.setEnabled(on_bnd)
            self.rb_by_panel.setEnabled(self.straight.isChecked())
            self.rb_by_force.setEnabled(self.straight.isChecked())

        for rb in (self.rb_rate, self.rb_vel, self.rb_pq,
                   self.rb_internal, self.rb_boundary):
            rb.toggled.connect(lambda _=False: _sync())
        self.straight.toggled.connect(lambda _=False: _sync())
        _sync()

    def values(self) -> dict:
        if self.rb_vel.isChecked():
            mode = "velocity"
        elif self.rb_pq.isChecked():
            mode = "pq"
        else:
            mode = "flow_rate"
        return {
            "flow_mode": mode,
            "flow_rate": self.rate.value(),
            "flow_rate_unit": self.rate_unit.currentText(),
            "velocity": self.vel.value(),
            "velocity_unit": self.vel_unit.currentText(),
            "pq_curve": self.pq.currentText(),
            "setting_location": (
                "boundary" if self.rb_boundary.isChecked() else "internal"),
            "inflow_temperature": self.inflow_temp.value(),
            "external_pressure": self.ext_press.value(),
            "press_unit": self.press_unit.currentText(),
            "flow_straightening": self.straight.isChecked(),
            "straighten_by": (
                "force" if self.rb_by_force.isChecked() else "panel"),
            "output_only_shape": self.output_shape.isChecked(),
            "virtual": self.virtual_chk.isChecked(),
        }


class AttributePanel(QGroupBox if _HAS_GUI_DEPS else object):
    """STpre [Attribute/Condition] group (right column of part dialogs)."""

    configure_requested = pyqtSignal()
    attribute_changed = pyqtSignal(str)

    def __init__(self, parent=None, *,
                 attributes=("Fluid",),
                 attribute_enabled=True,
                 heat_source=False,
                 virtual_part=False,
                 temperature_unit="C",
                 full_stpre: bool = False):
        super().__init__("Attribute/Condition", parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(4)
        self._full = full_stpre

        row = QHBoxLayout()
        row.addWidget(QLabel("Attribute", self))
        self.attribute = QComboBox(self)
        self.attribute.addItems(list(attributes))
        self.attribute.setEnabled(attribute_enabled and len(attributes) > 0)
        self.attribute.currentTextChanged.connect(self._on_attr_changed)
        row.addWidget(self.attribute, 1)
        lay.addLayout(row)

        lay.addWidget(QLabel("Material", self))
        mrow = QHBoxLayout()
        self.material = QLineEdit(self)
        self.material.setReadOnly(True)
        mrow.addWidget(self.material, 1)
        self.configure = QPushButton("Configure...", self)
        self.configure.clicked.connect(self.configure_requested)
        mrow.addWidget(self.configure)
        lay.addLayout(mrow)

        self.opening_chk = None
        self.thickness = None
        self.flip_chk = None
        if full_stpre:
            self.opening_chk = QCheckBox("Opening", self)
            lay.addWidget(self.opening_chk)
            trow0 = QHBoxLayout()
            trow0.addWidget(QLabel("Thickness", self))
            self.thickness = QDoubleSpinBox(self)
            self.thickness.setRange(0.0, 1e6)
            self.thickness.setDecimals(3)
            self.thickness.setValue(0.0)
            trow0.addWidget(self.thickness)
            trow0.addWidget(QLabel("mm", self))
            trow0.addStretch(1)
            lay.addLayout(trow0)
            self.flip_chk = QCheckBox("Flip the panel face", self)
            lay.addWidget(self.flip_chk)

        trow = QHBoxLayout()
        self.init_temp_chk = QCheckBox("Initial temperature", self)
        trow.addWidget(self.init_temp_chk)
        self.init_temp = QDoubleSpinBox(self)
        self.init_temp.setRange(-273.15, 1.0e6)
        self.init_temp.setDecimals(2)
        self.init_temp.setValue(0.0 if full_stpre else 20.0)
        trow.addWidget(self.init_temp)
        trow.addWidget(QLabel(temperature_unit, self))
        trow.addStretch(1)
        lay.addLayout(trow)
        self.init_temp_chk.toggled.connect(self.init_temp.setEnabled)
        self.init_temp.setEnabled(False)

        self.heat_chk = None
        self.heat = None
        self.heat_unit = None
        if heat_source or full_stpre:
            hrow = QHBoxLayout()
            self.heat_chk = QCheckBox("Heat source", self)
            hrow.addWidget(self.heat_chk)
            self.heat = QDoubleSpinBox(self)
            self.heat.setRange(0.0, 1.0e12)
            self.heat.setDecimals(3)
            hrow.addWidget(self.heat)
            self.heat_unit = QComboBox(self)
            self.heat_unit.addItems(["W", "W/m3", "W/m2"])
            hrow.addWidget(self.heat_unit)
            hrow.addStretch(1)
            lay.addLayout(hrow)
            self.heat_chk.toggled.connect(self.heat.setEnabled)
            self.heat.setEnabled(False)

        self.rad_type = None
        self.emissivity = None
        self.rad_indiv = None
        self.absorptance = None
        if full_stpre:
            rrow = QHBoxLayout()
            rrow.addWidget(QLabel("Type of radiation", self))
            self.rad_type = QComboBox(self)
            self.rad_type.addItems(["Specify emissivity", "None"])
            self.rad_type.currentTextChanged.connect(
                lambda _t: self._on_attr_changed(self.attribute.currentText()))
            rrow.addWidget(self.rad_type, 1)
            lay.addLayout(rrow)
            erow = QHBoxLayout()
            erow.addWidget(QLabel("Emissivity", self))
            self.emissivity = QDoubleSpinBox(self)
            self.emissivity.setRange(0.0, 1.0)
            self.emissivity.setDecimals(3)
            self.emissivity.setValue(0.9)
            erow.addWidget(self.emissivity)
            erow.addWidget(QLabel("<Undefined>", self))
            lay.addLayout(erow)
            self.rad_indiv = QCheckBox("Set individually", self)
            lay.addWidget(self.rad_indiv)
            arow = QHBoxLayout()
            arow.addWidget(QLabel("Absorptance", self))
            self.absorptance = QLineEdit("Undefined", self)
            self.absorptance.setReadOnly(True)
            arow.addWidget(self.absorptance, 1)
            self.abs_cfg = QPushButton("Configure...", self)
            self.abs_cfg.setEnabled(False)
            arow.addWidget(self.abs_cfg)
            lay.addLayout(arow)

        self.monitor_chk = QCheckBox("Output temperature to Monitor", self)
        self.monitor_chk.setChecked(not full_stpre)
        lay.addWidget(self.monitor_chk)

        self.virtual_chk = None
        if virtual_part or full_stpre:
            self.virtual_chk = QCheckBox("Virtual part", self)
            lay.addWidget(self.virtual_chk)
        lay.addStretch(1)
        self._on_attr_changed(self.attribute.currentText())

    def _on_attr_changed(self, text: str) -> None:
        self.attribute_changed.emit(text)
        if not self._full:
            return
        # STpre: Obstacle disables most thermal / panel options
        attr = (text or "").lower()
        is_panel = "panel" in attr
        is_fan = attr == "fan" or "flow fan" in attr or "blower" in attr
        is_obstacle = attr == "obstacle"
        # STpre: Opening enabled for Panel and Fan; Flip only for Panel
        if self.opening_chk is not None:
            self.opening_chk.setEnabled(is_panel or is_fan)
        if self.thickness is not None:
            self.thickness.setEnabled(is_panel)
        if self.flip_chk is not None:
            self.flip_chk.setEnabled(is_panel)
        thermal = not is_obstacle
        self.init_temp_chk.setEnabled(thermal or is_panel)
        if self.heat_chk is not None:
            self.heat_chk.setEnabled(thermal)
        # D7: allow emissivity edit for Solid/Panel (radiation analysis
        # still gates solver use; UI no longer permanently disabled).
        rad_ok = thermal or is_panel
        if self.rad_type is not None:
            self.rad_type.setEnabled(rad_ok)
        if self.emissivity is not None:
            self.emissivity.setEnabled(
                rad_ok and self.rad_type.currentText() == "Specify emissivity")
        if self.rad_indiv is not None:
            self.rad_indiv.setEnabled(rad_ok)
        if self.absorptance is not None:
            self.absorptance.setEnabled(False)
        if getattr(self, "abs_cfg", None) is not None:
            self.abs_cfg.setEnabled(False)
        self.monitor_chk.setEnabled(thermal)
        if self.virtual_chk is not None:
            self.virtual_chk.setEnabled(True)

    # -- value helpers -----------------------------------------------------

    def set_material(self, name: str) -> None:
        self.material.setText(name)

    def material_name(self) -> str:
        return self.material.text().strip()

    def set_initial_temperature(self, value: Optional[float],
                                checked: bool = True) -> None:
        self.init_temp_chk.setChecked(checked)
        if value is not None:
            self.init_temp.setValue(float(value))

    def initial_temperature(self) -> Optional[float]:
        return self.init_temp.value() if self.init_temp_chk.isChecked() \
            else None

    def set_monitor(self, on: bool) -> None:
        self.monitor_chk.setChecked(on)

    def monitor(self) -> bool:
        return self.monitor_chk.isChecked()

    def heat_source(self) -> Optional[tuple[float, str]]:
        if self.heat_chk is None or not self.heat_chk.isChecked():
            return None
        return self.heat.value(), self.heat_unit.currentText()

    def condition_values(self) -> dict:
        """Fields persisted onto ``<parts>`` (D7 thermal Attribute write-back)."""
        out: dict = {
            "monitor": self.monitor(),
            "virtual": bool(
                self.virtual_chk is not None and self.virtual_chk.isChecked()),
            "initial_temperature": self.initial_temperature(),
        }
        hs = self.heat_source()
        if hs is not None:
            out["heat_source"] = hs[0]
            out["heat_source_unit"] = hs[1]
        if self.opening_chk is not None and self.opening_chk.isChecked():
            out["opening"] = True
        if self.thickness is not None and self.thickness.isEnabled():
            out["panel_thickness"] = self.thickness.value()
        if self.flip_chk is not None and self.flip_chk.isChecked():
            out["flip_panel"] = True
        if (self.rad_type is not None
                and self.rad_type.currentText() == "Specify emissivity"
                and self.emissivity is not None):
            out["emissivity"] = self.emissivity.value()
        return out


class MaterialListDialog(QDialog if _HAS_GUI_DEPS else object):
    """STpre [List of Materials] — tree of standard property groups.

    Layout matches the Cradle dialog (``standard_property_ENG.xml`` /
    ``STpreParts`` labels): group folders on the left; Parts name /
    Selected material + Reference / Expand / Set / Cancel on the right.
    """

    def __init__(self, props: Optional[PropertyModel], parent=None,
                 current: str = "", part_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("List of Materials")
        self.resize(720, 520)
        self._selected = current or ""
        # Ensure full STpre library (merge Cradle standard into project props)
        try:
            from cab_materials import ensure_complete_library
            self.props = ensure_complete_library(props)
        except Exception:
            self.props = props

        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        tip = QLabel(
            "Selects a material to set for computational domain or for "
            "parts. ( material property can be modified, too ).", self)
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#333;")
        lay.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(8)

        # Left: group tree
        from PyQt5.QtCore import QSize
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(16, 16))
        self._populate_tree()
        self.tree.itemClicked.connect(self._on_tree_click)
        self.tree.itemDoubleClicked.connect(self._on_tree_dbl)
        body.addWidget(self.tree, 3)

        # Right: selection + buttons
        right = QVBoxLayout()
        right.addWidget(QLabel("Parts name", self))
        self.part_edit = QLineEdit(self)
        self.part_edit.setReadOnly(True)
        self.part_edit.setText(part_name or self._guess_part_name(parent))
        right.addWidget(self.part_edit)
        right.addWidget(QLabel("Selected material", self))
        self.sel_edit = QLineEdit(self)
        self.sel_edit.setReadOnly(True)
        self.sel_edit.setText(self._selected)
        right.addWidget(self.sel_edit)
        hint = QLabel("( Click in the list to select material )", self)
        hint.setStyleSheet("color:#555; font-size:11px;")
        right.addWidget(hint)

        grid = QGridLayout()
        self.btn_ref = QPushButton("Reference", self)
        self.btn_expand = QPushButton("Expand", self)
        self.btn_set = QPushButton("Set", self)
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_set.setDefault(True)
        self.btn_ref.clicked.connect(self._on_reference)
        self.btn_expand.clicked.connect(self._on_expand)
        self.btn_set.clicked.connect(self._on_set)
        self.btn_cancel.clicked.connect(self.reject)
        grid.addWidget(self.btn_ref, 0, 0)
        grid.addWidget(self.btn_expand, 0, 1)
        grid.addWidget(self.btn_set, 1, 0)
        grid.addWidget(self.btn_cancel, 1, 1)
        right.addLayout(grid)

        self.edit_mode = QCheckBox("Editing mode", self)
        right.addWidget(self.edit_mode)
        note = QLabel(
            "(*) After checking the checkbox, right-click in the list "
            "to select a menu.", self)
        note.setWordWrap(True)
        note.setStyleSheet("color:#555; font-size:11px;")
        right.addWidget(note)
        right.addStretch(1)
        body.addLayout(right, 2)
        lay.addLayout(body, 1)

        brow = QHBoxLayout()
        brow.addStretch(1)
        close = QPushButton("Close", self)
        close.clicked.connect(self.reject)
        brow.addWidget(close)
        lay.addLayout(brow)

        if self._selected:
            self._select_in_tree(self._selected)

    @staticmethod
    def _guess_part_name(parent) -> str:
        if parent is None:
            return ""
        for attr in ("part_name", "name_edit"):
            w = getattr(parent, attr, None)
            if isinstance(w, str) and w:
                return w
            if w is not None and hasattr(w, "text"):
                try:
                    return w.text().strip()
                except Exception:
                    pass
        return ""

    def _populate_tree(self) -> None:
        self.tree.clear()
        folder_icon = AppIcons.get("folder", 16)
        mat_icon = AppIcons.get("library", 16)
        catalog = []
        if self.props is not None:
            catalog = self.props.group_catalog()
        for gtype, gname, names in catalog:
            if not gname:
                continue
            # Skip empty placeholder groups in the tree (keep "others" if empty)
            gitem = QTreeWidgetItem([gname])
            gitem.setIcon(0, folder_icon)
            gitem.setData(0, Qt.UserRole, ("group", gtype, gname))
            gitem.setFlags(gitem.flags() & ~Qt.ItemIsSelectable)
            for mat in names:
                c = QTreeWidgetItem([mat])
                c.setIcon(0, mat_icon)
                c.setData(0, Qt.UserRole, ("entry", mat))
                gitem.addChild(c)
            self.tree.addTopLevelItem(gitem)
        # Expand solid folders by default (matches typical STpre solid pick)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole) or ()
            if len(data) >= 2 and data[1] == "solid":
                item.setExpanded(False)  # collapsed like screenshot

    def _select_in_tree(self, name: str) -> None:
        matches = self.tree.findItems(
            name, Qt.MatchExactly | Qt.MatchRecursive)
        if matches:
            self.tree.setCurrentItem(matches[0])
            parent = matches[0].parent()
            if parent is not None:
                parent.setExpanded(True)
            self.tree.scrollToItem(matches[0])

    def _on_tree_click(self, item, _col) -> None:
        data = item.data(0, Qt.UserRole) if item is not None else None
        if data and data[0] == "entry":
            self._selected = data[1]
            self.sel_edit.setText(self._selected)

    def _on_tree_dbl(self, item, _col) -> None:
        data = item.data(0, Qt.UserRole) if item is not None else None
        if data and data[0] == "entry":
            self._selected = data[1]
            self.sel_edit.setText(self._selected)
            self.accept()

    def _on_expand(self) -> None:
        self.tree.expandAll()

    def _on_reference(self) -> None:
        name = self.selected_material()
        if not name or self.props is None:
            QMessageBox.information(self, "Reference",
                                    "Select a material in the list.")
            return
        ent = self.props.find_entry(name)
        if ent is None:
            QMessageBox.information(self, "Reference",
                                    f"No property data for '{name}'.")
            return
        from cabxml import _first
        lines = [f"Material: {name}"]
        for key in ("density", "ref_density", "ref_temperature", "viscosity",
                    "capacity", "conductivity", "expansion"):
            c = _first(ent, key)
            if c is not None and c.text and c.text.strip():
                unit = c.attrib.get("unit", "")
                lines.append(f"  {key}: {c.text.strip()}"
                             + (f" [{unit}]" if unit else ""))
        QMessageBox.information(self, "Material Reference", "\n".join(lines))

    def _on_set(self) -> None:
        if not self.selected_material():
            QMessageBox.warning(self, "List of Materials",
                                "Click in the list to select material.")
            return
        self.accept()

    def selected_material(self) -> str:
        return (self._selected or self.sel_edit.text() or "").strip()


class StpreDialogBase(QDialog if _HAS_GUI_DEPS else object):
    """Common STpre dialog chrome.

    Layout (aligned with the [Edit Computational Domain] screenshot)::

        +------------------------------------------------------+
        | [icon] Caption                                       |
        | ---------------------------------------------------  |
        | Part Name [..........]              [Color...] [sw]  |
        | +-- <left group> --------+  +-- Attribute/Condition+ |
        | | ...                    |  | ...                  | |
        | +------------------------+  +----------------------+ |
        |          [Preview] [Apply] [OK] [Cancel]             |
        +------------------------------------------------------+

    Subclasses fill the left column in :meth:`_build_left` and implement
    :meth:`_on_apply`; override :meth:`_on_ok` / :meth:`_on_cancel` when
    the default ``_on_apply`` + accept/reject behaviour is not enough.
    """

    def __init__(self, title: str, header: str, *, icon: str = "domain",
                 parent=None, name_row: bool = True,
                 attribute_panel: Optional[AttributePanel] = None,
                 left_title: str = "Scale",
                 buttons=("Preview", "Apply", "OK", "Cancel")):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._applied = False
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        self.header = DialogHeader(header, icon, self)
        lay.addWidget(self.header)

        if name_row:
            nrow = QHBoxLayout()
            nrow.addWidget(QLabel("Part Name", self))
            self.name_edit = QLineEdit(self)
            nrow.addWidget(self.name_edit, 1)
            nrow.addStretch(1)
            self.color_btn = ColorButton(parent=self)
            nrow.addWidget(self.color_btn)
            lay.addLayout(nrow)
        else:
            self.name_edit = None
            self.color_btn = None

        cols = QHBoxLayout()
        cols.setSpacing(8)
        self.left_box = QGroupBox(left_title, self)
        self.left_layout = QVBoxLayout(self.left_box)
        self.left_layout.setSpacing(6)
        cols.addWidget(self.left_box, 3)
        self.attr_panel = attribute_panel
        if attribute_panel is not None:
            cols.addWidget(attribute_panel, 2)
        lay.addLayout(cols, 1)
        self._build_left(self.left_layout)

        brow = QHBoxLayout()
        brow.addStretch(1)
        self._buttons = {}
        for label in buttons:
            btn = QPushButton(label, self)
            if label == "Preview":
                btn.clicked.connect(self._on_preview)
            elif label == "Apply":
                btn.clicked.connect(self._on_apply)
            elif label == "OK":
                btn.setDefault(True)
                btn.clicked.connect(self._on_ok)
            elif label == "Cancel":
                btn.clicked.connect(self._on_cancel)
            else:  # custom button -> _on_custom_<label>()
                handler = getattr(self, f"_on_{label.lower()}", None)
                if handler is not None:
                    btn.clicked.connect(handler)
            brow.addWidget(btn)
            self._buttons[label] = btn
        lay.addLayout(brow)

    # -- subclass hooks ----------------------------------------------------

    def _build_left(self, layout: QVBoxLayout) -> None:
        """Fill the left column (override)."""

    def _on_preview(self) -> None:
        self._on_apply()

    def _on_apply(self) -> None:
        """Apply current widget values (override)."""
        self._applied = True

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()

    def _on_cancel(self) -> None:
        self.reject()

    def button(self, label: str) -> QPushButton:
        return self._buttons[label]


# ------------------------------------------------------- computational domain


class DomainDialog(StpreDialogBase):
    """[Edit Computational Domain] — STpre layout (double-click Domain).

    Left column  [Scale]: cuboid sketch, [Calculate Part Region],
    <Rectangular box subdomain> min/max, [Extend surroundings],
    Reference coordinate system, unit.
    Right column [Attribute/Condition]: Attribute=Fluid, Material with
    [Configure...], Initial temperature, Output temperature to Monitor.
    """

    def __init__(self, model: StpreModel, props: Optional[PropertyModel],
                 cad_meshes, parent=None):
        self.model = model
        self.props = props
        self.cad_meshes = cad_meshes
        self.old_spec = cab_domain.domain_from_xml(model) \
            or cab_domain.DomainSpec()
        attr = AttributePanel(
            attributes=("Fluid",), attribute_enabled=False, parent=None)
        attr.configure_requested.connect(self._configure_material)
        super().__init__(
            "Edit Computational Domain", "Computational Domain",
            icon="domain", parent=parent, attribute_panel=attr,
            left_title="Scale")
        self._load_spec(self.old_spec)

    # -- left column (Scale) ------------------------------------------------

    def _build_left(self, lay: QVBoxLayout) -> None:
        lay.addWidget(CuboidSchematic(self), 0, Qt.AlignHCenter)
        self.btn_cad = QPushButton("Calculate Part Region", self)
        self.btn_cad.clicked.connect(self._cad_data_size)
        lay.addWidget(self.btn_cad)
        self.auto_y = QCheckBox(
            "Maximum length in Y direction: Auto setting", self)
        self.auto_y.setVisible(self.old_spec.coordinate == "axial")
        lay.addWidget(self.auto_y)
        caption = QLabel("<Rectangular box subdomain>", self)
        caption.setStyleSheet("color: #444;")
        lay.addWidget(caption)

        ref = QHBoxLayout()
        ref.addWidget(QLabel("Reference\ncoordinate system", self))
        self.ref_coord = QComboBox(self)
        self.ref_coord.addItem("Global coordinate system")
        self.ref_coord.addItem("Sketch coordinate system")
        self.ref_coord.model().item(1).setEnabled(False)
        ref.addWidget(self.ref_coord, 1)
        lay.addLayout(ref)

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        for i, ax in enumerate(("X", "Y", "Z")):
            lab = QLabel(ax, self)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 0, i + 1)
        grid.addWidget(QLabel("Minimum", self), 1, 0)
        grid.addWidget(QLabel("Maximum", self), 2, 0)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            for row, side in ((1, "min"), (2, "max")):
                sb = self._make_spin()
                grid.addWidget(sb, row, i + 1)
                self.spins[f"{ax}{side}"] = sb
        lay.addLayout(grid)

        self.extend_chk = QCheckBox("Extend surroundings", self)
        lay.addWidget(self.extend_chk)
        egrid = QGridLayout()
        egrid.setHorizontalSpacing(4)
        egrid.addWidget(QLabel("Minimum", self), 0, 0)
        egrid.addWidget(QLabel("Maximum", self), 1, 0)
        self.extend_spins: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            for row, side in ((0, "min"), (1, "max")):
                sb = self._make_spin()
                sb.setRange(0.0, 1.0e9)
                egrid.addWidget(sb, row, i + 1)
                self.extend_spins[f"{ax}{side}"] = sb
        lay.addLayout(egrid)
        self.extend_chk.toggled.connect(self._on_extend_toggled)
        self._on_extend_toggled(False)

        urow = QHBoxLayout()
        urow.addStretch(1)
        urow.addWidget(QLabel("Unit:", self))
        self.unit = QComboBox(self)
        self.unit.addItems(["mm", "m", "cm"])
        self.unit.currentTextChanged.connect(self._on_unit_changed)
        urow.addWidget(self.unit)
        lay.addLayout(urow)
        lay.addStretch(1)

    def _make_spin(self) -> QDoubleSpinBox:
        sb = QDoubleSpinBox(self)
        sb.setRange(-1.0e9, 1.0e9)
        sb.setDecimals(6)
        sb.setSingleStep(1.0)
        sb.setMinimumWidth(64)
        return sb

    def _on_extend_toggled(self, on: bool) -> None:
        for sb in self.extend_spins.values():
            sb.setEnabled(on)

    # -- spec <-> widgets ----------------------------------------------------

    def _load_spec(self, spec: cab_domain.DomainSpec) -> None:
        self.name_edit.setText(spec.name)
        self.color_btn.set_rgba(spec.color)
        self.unit.blockSignals(True)
        self.unit.setCurrentText(spec.unit if spec.unit in _UNIT_FACTOR
                                 else "mm")
        self.unit.blockSignals(False)
        self._current_unit = self.unit.currentText()
        for i, ax in enumerate("xyz"):
            self.spins[f"{ax}min"].setValue(spec.xyz_min[i])
            self.spins[f"{ax}max"].setValue(spec.xyz_max[i])
            self.extend_spins[f"{ax}min"].setValue(spec.extend_min[i])
            self.extend_spins[f"{ax}max"].setValue(spec.extend_max[i])
        self.extend_chk.setChecked(
            any(v != 0.0 for v in spec.extend_min)
            or any(v != 0.0 for v in spec.extend_max)
            or any(v != 0.0 for v in spec.extend))
        self.auto_y.setChecked(spec.auto_y_for_axial)
        attr = self.attr_panel
        attr.set_material(spec.material)
        attr.set_initial_temperature(spec.initial_temperature, checked=True)
        attr.set_monitor(spec.monitor)

    def _current_spec(self) -> cab_domain.DomainSpec:
        unit = self.unit.currentText()
        extending = self.extend_chk.isChecked()
        return cab_domain.DomainSpec(
            coordinate=self.old_spec.coordinate,
            unit=unit,
            xyz_min=(self.spins["xmin"].value(), self.spins["ymin"].value(),
                     self.spins["zmin"].value()),
            xyz_max=(self.spins["xmax"].value(), self.spins["ymax"].value(),
                     self.spins["zmax"].value()),
            material=self.attr_panel.material_name(),
            extend_min=tuple(self.extend_spins[f"{ax}min"].value()
                             if extending else 0.0 for ax in "xyz"),
            extend_max=tuple(self.extend_spins[f"{ax}max"].value()
                             if extending else 0.0 for ax in "xyz"),
            auto_y_for_axial=self.auto_y.isChecked(),
            name=self.name_edit.text().strip() or "Domain(cuboid)",
            color=self.color_btn.rgba(),
            monitor=self.attr_panel.monitor(),
            initial_temperature=self.attr_panel.initial_temperature(),
        )

    # -- unit conversion ------------------------------------------------------

    def _on_unit_changed(self, new_unit: str) -> None:
        old_unit = getattr(self, "_current_unit", "mm")
        if old_unit == new_unit or old_unit not in _UNIT_FACTOR \
                or new_unit not in _UNIT_FACTOR:
            self._current_unit = new_unit
            return
        ratio = _UNIT_FACTOR[old_unit] / _UNIT_FACTOR[new_unit]
        for sb in list(self.spins.values()) + list(self.extend_spins.values()):
            sb.setValue(sb.value() * ratio)
        self._current_unit = new_unit

    # -- buttons / actions -----------------------------------------------------

    def _configure_material(self) -> None:
        dlg = MaterialListDialog(self.props, self,
                                 current=self.attr_panel.material_name())
        if dlg.exec_() and dlg.selected_material():
            self.attr_panel.set_material(dlg.selected_material())

    def _apply(self, preview: bool = False) -> None:
        spec = self._current_spec()
        if self.extend_chk.isChecked():
            spec.xyz_min = tuple(
                v - m for v, m in zip(spec.xyz_min, spec.extend_min))
            spec.xyz_max = tuple(
                v + m for v, m in zip(spec.xyz_max, spec.extend_max))
            spec.extend_min = (0.0, 0.0, 0.0)
            spec.extend_max = (0.0, 0.0, 0.0)
        cab_domain.apply_domain(self.model, spec)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()
            parent.log(
                f"Domain preview: {spec.coordinate} "
                f"min={spec.xyz_min} max={spec.xyz_max} unit={spec.unit}")
        if not preview:
            self._current_unit = spec.unit
            self.accept()

    def _revert(self) -> None:
        cab_domain.apply_domain(self.model, self.old_spec)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()
        self.reject()

    # StpreDialogBase hooks: Preview -> preview, Apply -> apply, OK -> apply
    # + close, Cancel -> revert.
    def _on_preview(self) -> None:
        self._apply(True)

    def _on_apply(self) -> None:
        self._apply(True)

    def _on_ok(self) -> None:
        self._apply(False)

    def _on_cancel(self) -> None:
        self._revert()

    def _cad_data_size(self) -> None:
        """[Calculate Part Region]: bounding box of all registered parts."""
        lo, hi = cab_domain.part_bounds(self.model, self.cad_meshes)
        parent = self.parent()
        if not np.isfinite(lo).all():
            if parent is not None and hasattr(parent, "log"):
                parent.log("Calculate Part Region: no tessellated parts",
                           "WARN")
            return
        unit = self.unit.currentText()
        factor = _UNIT_FACTOR.get(unit, 1.0)
        # part_bounds returns metres; convert to the dialog unit
        scale = 1000.0 / factor
        for i, ax in enumerate("xyz"):
            self.spins[f"{ax}min"].setValue(lo[i] * scale)
            self.spins[f"{ax}max"].setValue(hi[i] * scale)
        if parent is not None and hasattr(parent, "log"):
            parent.log(f"Calculate Part Region: {lo * scale} ~ {hi * scale} "
                       f"[{unit}]")


# --------------------------------------------------------------- Mesh:block


class MeshBlockDialog(QDialog if _HAS_GUI_DEPS else object):
    """STpre ``Mesh:block`` — edit RootBlock range (Layout of Parts).

    Double-click / Reference on ``RootBlock`` opens this dialog (not
    Mesh→Gridding / ``Mesh:Set division``).
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("Mesh:block")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        lay.addWidget(DialogHeader(
            "Edits parameters of mesh block.", "mesh", self))

        form = QGridLayout()
        form.addWidget(QLabel("Block name", self), 0, 0)
        self.name_edit = QLineEdit(self)
        form.addWidget(self.name_edit, 0, 1, 1, 3)
        form.addWidget(QLabel("Parent block name", self), 1, 0)
        self.parent_edit = QLineEdit(self)
        form.addWidget(self.parent_edit, 1, 1, 1, 3)
        lay.addLayout(form)

        # Minimum / Maximum table
        rng = QGridLayout()
        rng.addWidget(QLabel("", self), 0, 0)
        for i, ax in enumerate("XYZ"):
            lab = QLabel(ax, self)
            lab.setAlignment(Qt.AlignCenter)
            rng.addWidget(lab, 0, i + 1)
        self.min_spins: dict[str, QDoubleSpinBox] = {}
        self.max_spins: dict[str, QDoubleSpinBox] = {}
        rng.addWidget(QLabel("Minimum", self), 1, 0)
        rng.addWidget(QLabel("Maximum", self), 2, 0)
        for i, ax in enumerate("xyz"):
            for row, store in ((1, self.min_spins), (2, self.max_spins)):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setMinimumWidth(72)
                store[ax] = sb
                rng.addWidget(sb, row, i + 1)
        lay.addLayout(rng)

        sel_row = QHBoxLayout()
        self.select_edit = QLineEdit(self)
        self.select_edit.setEnabled(False)
        sel_row.addWidget(self.select_edit, 1)
        self.btn_select = QPushButton("Select", self)
        self.btn_select.setEnabled(False)
        sel_row.addWidget(self.btn_select)
        lay.addLayout(sel_row)
        hint = QLabel(
            "By clicking 'select' button, part and/or group can be "
            "selected from the tree or draw window and set to range.",
            self)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        lay.addWidget(hint)

        # Extend surroundings
        self.extend_cb = QCheckBox("Extend surroundings", self)
        lay.addWidget(self.extend_cb)
        ext = QGridLayout()
        ext.addWidget(QLabel("Minimum", self), 1, 0)
        ext.addWidget(QLabel("Maximum", self), 2, 0)
        for i, ax in enumerate("XYZ"):
            ext.addWidget(QLabel(ax, self), 0, i + 1)
        self.ext_min: dict[str, QDoubleSpinBox] = {}
        self.ext_max: dict[str, QDoubleSpinBox] = {}
        for i, ax in enumerate("xyz"):
            for row, store in ((1, self.ext_min), (2, self.ext_max)):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setValue(0.0)
                store[ax] = sb
                ext.addWidget(sb, row, i + 1)
        self._ext_host = QWidget(self)
        self._ext_host.setLayout(ext)
        lay.addWidget(self._ext_host)
        self.extend_cb.toggled.connect(self._ext_host.setEnabled)
        self._ext_host.setEnabled(False)

        # Parameter
        self.param_cb = QCheckBox("Parameter", self)
        lay.addWidget(self.param_cb)
        prm = QGridLayout()
        for i, ax in enumerate("XYZ"):
            prm.addWidget(QLabel(ax, self), 0, i + 1)
        self.std: dict[str, QDoubleSpinBox] = {}
        self.thr: dict[str, QDoubleSpinBox] = {}
        self.ratio: dict[str, QDoubleSpinBox] = {}
        self.common: dict[str, QCheckBox] = {}
        rows = (("Standard length", self.std, 1.0),
                ("Threshold length", self.thr, 0.1),
                ("Geometric ratio", self.ratio, 1.0))
        for r, (label, store, default) in enumerate(rows, 1):
            prm.addWidget(QLabel(label, self), r, 0)
            for i, ax in enumerate("xyz"):
                sb = QDoubleSpinBox(self)
                sb.setRange(1e-9, 1e9)
                sb.setDecimals(6)
                sb.setValue(default)
                store[ax] = sb
                prm.addWidget(sb, r, i + 1)
            cb = QCheckBox("Common", self)
            if label == "Geometric ratio":
                cb.setChecked(True)
            self.common[label] = cb
            prm.addWidget(cb, r, 4)
        self._prm_host = QWidget(self)
        self._prm_host.setLayout(prm)
        lay.addWidget(self._prm_host)
        self.param_cb.toggled.connect(self._prm_host.setEnabled)
        self._prm_host.setEnabled(False)

        unit_row = QHBoxLayout()
        unit_row.addStretch(1)
        unit_row.addWidget(QLabel("Unit : mm", self))
        lay.addLayout(unit_row)

        brow = QHBoxLayout()
        brow.addStretch(1)
        for label, slot in (("Preview", self._on_preview),
                            ("OK", self._on_ok),
                            ("Cancel", self.reject)):
            btn = QPushButton(label, self)
            if label == "OK":
                btn.setDefault(True)
            btn.clicked.connect(slot)
            brow.addWidget(btn)
        lay.addLayout(brow)

        self._load()

    def _load(self) -> None:
        from cabxml import _first
        mb = self.model.mesh_block()
        name = "RootBlock"
        if mb is not None:
            n = _first(mb, "name")
            if n is not None and n.text:
                name = n.text.strip()
        self.name_edit.setText(name)
        bb = self.model.root_block_bounds()
        if bb is None:
            bb = (0.0, 0.0, 0.0, 100.0, 100.0, 100.0)
        for i, ax in enumerate("xyz"):
            self.min_spins[ax].setValue(bb[i])
            self.max_spins[ax].setValue(bb[i + 3])
        if mb is not None:
            for tag, store in (("extend_min", self.ext_min),
                               ("extend_max", self.ext_max)):
                el = _first(mb, "extend_min" if tag == "extend_min"
                            else "extend_max")
                if el is not None and el.text:
                    try:
                        vals = [float(x.strip())
                                for x in el.text.split(",")[:3]]
                        if len(vals) == 3:
                            for i, ax in enumerate("xyz"):
                                store[ax].setValue(vals[i])
                            if any(abs(v) > 1e-15 for v in vals):
                                self.extend_cb.setChecked(True)
                    except ValueError:
                        pass
        mc = _first(self.model.root, "mesh_control")
        blk = _first(mc, "block") if mc is not None else None
        lim = _first(blk, "limit") if blk is not None else None
        if lim is not None and lim.text:
            try:
                vals = [float(x.strip()) for x in lim.text.split(",")[:3]]
                if len(vals) == 3:
                    for i, ax in enumerate("xyz"):
                        self.thr[ax].setValue(vals[i])
            except ValueError:
                pass
        ratio = _first(mc, "divide_ratio2") if mc is not None else None
        if ratio is not None and ratio.text:
            try:
                vals = [float(x.strip()) for x in ratio.text.split(",")[:3]]
                if len(vals) == 3:
                    for i, ax in enumerate("xyz"):
                        self.ratio[ax].setValue(vals[i])
            except ValueError:
                pass

    def _values(self):
        name = self.name_edit.text().strip() or "RootBlock"
        mn = tuple(self.min_spins[a].value() for a in "xyz")
        mx = tuple(self.max_spins[a].value() for a in "xyz")
        if any(mx[i] <= mn[i] for i in range(3)):
            QMessageBox.warning(
                self, "Mesh:block",
                "Maximum must be greater than Minimum on each axis.")
            return None
        if self.extend_cb.isChecked():
            emin = tuple(self.ext_min[a].value() for a in "xyz")
            emax = tuple(self.ext_max[a].value() for a in "xyz")
        else:
            emin = (0.0, 0.0, 0.0)
            emax = (0.0, 0.0, 0.0)
        thr = ratio = None
        if self.param_cb.isChecked():
            thr = tuple(self.thr[a].value() for a in "xyz")
            ratio = tuple(self.ratio[a].value() for a in "xyz")
        return name, mn, mx, emin, emax, thr, ratio

    def _apply(self) -> bool:
        vals = self._values()
        if vals is None:
            return False
        name, mn, mx, emin, emax, thr, ratio = vals
        kw = dict(name=name, extend_min=emin, extend_max=emax)
        if thr is not None:
            kw["threshold"] = thr
        if ratio is not None:
            kw["ratio"] = ratio
        self.model.set_root_block_range(mn, mx, **kw)
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(
                f"RootBlock '{name}': "
                f"({mn[0]:g},{mn[1]:g},{mn[2]:g}) – "
                f"({mx[0]:g},{mx[1]:g},{mx[2]:g}) mm")
        return True

    def _on_preview(self) -> None:
        if not self._apply():
            return
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._root_block_visible = True
            parent._rebuild_scene(fit=False)

    def _on_ok(self) -> None:
        if self._apply():
            self.accept()


# ------------------------------------------------------------------ parts


class PartDialog(StpreDialogBase):
    """[Part] - [Cuboid]-style part editor built on the framework.

    Demonstrates the reusable chrome for other settings dialogs:
    [Scale] (Reference coordinate system / Location / Size) on the left,
    [Attribute/Condition] on the right, Preview/Apply/OK/Cancel below.
    Geometry fields are read-only for parts whose box parameters are not
    stored in the cab XML (body parts); name/material/color/monitor are
    always editable.
    """

    def __init__(self, model: StpreModel, props: Optional[PropertyModel],
                 part_name: str, parent=None):
        self.model = model
        self.props = props
        self.part_name = part_name
        self._part = next(
            (p for p in model.parts() if p.name == part_name), None)
        attr = AttributePanel(
            attributes=("Obstacle", "Solid", "Condition region", "Fluid"),
            attribute_enabled=True, heat_source=True, virtual_part=True)
        attr.configure_requested.connect(self._configure_material)
        super().__init__(
            f"Part — {part_name}", "Cuboid" if self._is_box() else "Part",
            icon="cube" if self._is_box() else "part", parent=parent,
            attribute_panel=attr, left_title="Scale")
        self._load_part()

    def _is_box(self) -> bool:
        return self._part is not None and self._part.kind in (
            "cube", "box", "cuboid")

    def _build_left(self, lay: QVBoxLayout) -> None:
        lay.addWidget(CuboidSchematic(self, face="#bdd7ee"), 0,
                      Qt.AlignHCenter)
        ref = QHBoxLayout()
        ref.addWidget(QLabel("Reference\ncoordinate system", self))
        self.ref_coord = QComboBox(self)
        self.ref_coord.addItem("Global coordinate system")
        self.ref_coord.addItem("Sketch coordinate system")
        self.ref_coord.model().item(1).setEnabled(False)
        ref.addWidget(self.ref_coord, 1)
        lay.addLayout(ref)

        self.loc: dict[str, QDoubleSpinBox] = {}
        self.size: dict[str, QDoubleSpinBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        for i, ax in enumerate(("X", "Y", "Z")):
            lab = QLabel(ax, self)
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, 0, i + 1)
        grid.addWidget(QLabel("Location", self), 1, 0)
        grid.addWidget(QLabel("Size", self), 2, 0)
        for i, ax in enumerate("xyz"):
            for row, store in ((1, self.loc), (2, self.size)):
                sb = QDoubleSpinBox(self)
                sb.setRange(-1.0e9, 1.0e9)
                sb.setDecimals(6)
                sb.setMinimumWidth(64)
                grid.addWidget(sb, row, i + 1)
                store[ax] = sb
        lay.addLayout(grid)
        self.geom_note = QLabel("", self)
        self.geom_note.setStyleSheet("color: #555; font-size: 11px;")
        self.geom_note.setWordWrap(True)
        lay.addWidget(self.geom_note)
        lay.addStretch(1)

    def _load_part(self) -> None:
        if self._part is None:
            self.geom_note.setText(f"Part '{self.part_name}' not found.")
            return
        p = self._part
        self.name_edit.setText(p.name)
        try:
            rgba = tuple(int(float(v)) for v in p.color.split(",")[:4])
            if len(rgba) == 4:
                self.color_btn.set_rgba(rgba)
        except (ValueError, TypeError):
            pass
        base = self._triple(p.base)
        size = self._triple(p.size)
        editable = base is not None and size is not None
        for i, ax in enumerate("xyz"):
            self.loc[ax].setValue(base[i] if base else 0.0)
            self.loc[ax].setEnabled(editable)
            self.size[ax].setValue(size[i] if size else 0.0)
            self.size[ax].setEnabled(editable)
        if not editable:
            self.geom_note.setText(
                "Geometry of this part is stored in the CAD file "
                "(body part); edit Location/Size via transform only.")
        attr = self.attr_panel
        attr.set_material(p.property)
        if p.attribute:
            idx = attr.attribute.findText(p.attribute)
            if idx >= 0:
                attr.attribute.setCurrentIndex(idx)
        mon = self.model.find_part(p.name)
        if mon is not None:
            from cabxml import _first
            mel = _first(mon, "monitor")
            attr.set_monitor(
                mel is None or not mel.text
                or mel.text.strip().upper() != "F")

    @staticmethod
    def _triple(text: str) -> Optional[tuple[float, float, float]]:
        if not text:
            return None
        try:
            vals = [float(v.strip()) for v in text.split(",")[:3]]
        except ValueError:
            return None
        return tuple(vals) if len(vals) == 3 else None  # type: ignore

    def _configure_material(self) -> None:
        dlg = MaterialListDialog(
            self.props, self,
            current=self.attr_panel.material_name(),
            part_name=getattr(self, "part_name", "")
            or (self.name_edit.text() if self.name_edit else ""))
        if dlg.exec_() and dlg.selected_material():
            self.attr_panel.set_material(dlg.selected_material())

    # -- framework hooks -----------------------------------------------------

    def _on_preview(self) -> None:
        self._commit(preview=True)

    def _on_apply(self) -> None:
        self._commit(preview=True)

    def _on_ok(self) -> None:
        self._commit(preview=False)
        self.accept()

    def _commit(self, preview: bool) -> None:
        if self._part is None:
            return
        new_name = self.name_edit.text().strip()
        if new_name and new_name != self._part.name:
            if self.model.find_part(new_name) is not None:
                parent = self.parent()
                if parent is not None and hasattr(parent, "log"):
                    parent.log(f"Part with the same name exists: {new_name}",
                               "WARN")
                return
            self.model.rename_part(self._part.name, new_name)
            self.part_name = new_name
        self.model.set_part_property(
            self.part_name, self.attr_panel.material_name())
        self.model.set_part_color(self.part_name, self.color_btn.rgba())
        self.model.set_part_monitor(
            self.part_name, self.attr_panel.monitor())
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()
            parent.log(
                f"Part '{self.part_name}' updated "
                f"(material={self.attr_panel.material_name()})")


class GriddingDialog(QDialog if _HAS_GUI_DEPS else object):
    """[Mesh] - [Gridding]: the STpre ``Mesh:Set division`` dialog.

    Six tabs aligned with the Pre_eng manual and the STpre screenshots:

    - **Basic Setting** — Vertex detection, Method of Gridding (incl.
      Specifying the numbers of elements + Sub-block mesh refinement
      factor), Division parameters of root block (Standard/Threshold/
      Geometric ratio internal+external with [Common]), generation
      options, [Interference] with [Reconstruct];
    - **Parameter** — Multiblock tree + Mesh option of each part
      (per-part vertex detection persisted to ``<parts>/<select_vertex>``);
    - **Detail meshing** — re-divide a grid-line range (direction of
      axis/division, element count, geometric ratio, retain rough grids,
      threshold of active block);
    - **Edit** — per-axis grid-line list (No./Coordinates/Type/Referred
      parts) with Add/Delete/Edit/Preview and General/Fixed/Rough types;
    - **Deletion** — Selected / All but rough grids / All (keep lines
      through part min/max), optional Fixed-type cancel;
    - **Others** — edge-contact tools, meshing of a specified part,
      meshing parameters (edge tolerance / face search / element
      threshold), domain-boundary element faces, flux-face duplication
      check, V8 meshing method, parallel degree.

    Bottom row: [Gridding] [Meshing] [Close] + ``Element #`` status.
    """

    _DETECTIONS = [
        ("All", "all"), ("Representative", "representative"),
        ("Axis plane", "axis_plane"), ("Min/Max", "minmax"),
        ("Not considered", "not_considered"), ("Uniform", "uniform"),
    ]
    _METHODS = [
        ("Rough grids only", "rough_only"),
        ("Rough grids and detailed mesh", "rough_and_detail"),
        ("Rough grids and detailed mesh by specifying the number of "
         "elements", "num_elements"),
    ]
    _DOMAIN_TYPES = [
        ("Cartesian", "cartesian"),
        ("Cylindrical", "cylindrical"),
        ("Axial", "axial"),
    ]
    _GRID_TYPES = [("General", "N"), ("Fixed", "F"), ("Rough", "S")]
    _MARK_LABEL = {"B": "block", "N": "", "F": "fixed", "S": "rough",
                   "C": "child_block"}

    def __init__(self, model: StpreModel, cad_meshes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mesh:Set division")
        self.model = model
        self.cad_meshes = cad_meshes or []
        self.stpre_callback = None   # set by cab_gui when STpre API enabled
        self._build_ui()
        self._load_from_model()

    # ================================================================ UI

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_basic_tab(), "Basic Setting")
        self.tabs.addTab(self._build_parameter_tab(), "Parameter")
        self.tabs.addTab(self._build_detail_tab(), "Detail meshing")
        self.tabs.addTab(self._build_edit_tab(), "Edit")
        self.tabs.addTab(self._build_deletion_tab(), "Deletion")
        self.tabs.addTab(self._build_others_tab(), "Others")
        lay.addWidget(self.tabs, 1)

        brow = QHBoxLayout()
        self.btn_gridding = QPushButton("Gridding", self)
        self.btn_gridding.clicked.connect(self._gridding)
        self.btn_meshing = QPushButton("Meshing", self)
        self.btn_meshing.clicked.connect(self._meshing)
        self.btn_close = QPushButton("Close", self)
        self.btn_close.clicked.connect(self.accept)
        brow.addWidget(self.btn_gridding)
        brow.addWidget(self.btn_meshing)
        brow.addStretch(1)
        brow.addWidget(self.btn_close)
        lay.addLayout(brow)
        self.element_label = QLabel(self)
        self.element_label.setStyleSheet(
            "border: 1px solid #aaa; padding: 2px 6px; background: #fff;")
        lay.addWidget(self.element_label)
        self.resize(430, 760)

    # ---------------------------------------------------------- helpers

    def _radio_group(self, parent_layout, items, key_attr,
                     cols=3) -> dict[str, QRadioButton]:
        """Create radio buttons in a grid; store in ``self.<key_attr>``."""
        radios: dict[str, QRadioButton] = {}
        grid = QGridLayout()
        for i, (label, key) in enumerate(items):
            rb = QRadioButton(label, self)
            grid.addWidget(rb, i // cols, i % cols)
            radios[key] = rb
        parent_layout.addLayout(grid)
        setattr(self, key_attr, radios)
        return radios

    def _axis_spins(self, minimum=1.0e-6, decimals=6, value=0.0
                    ) -> dict[str, QDoubleSpinBox]:
        spins: dict[str, QDoubleSpinBox] = {}
        for ax in "xyz":
            sb = QDoubleSpinBox(self)
            sb.setRange(minimum, 1.0e9)
            sb.setDecimals(decimals)
            sb.setValue(value)
            sb.setMinimumWidth(58)
            spins[ax] = sb
        return spins

    def _active_block_row(self, lay: QVBoxLayout) -> None:
        box = QGroupBox("ActiveBlock", self)
        row = QHBoxLayout(box)
        row.addWidget(QLabel("Block name", box))
        edit = QLineEdit("RootBlock", box)
        edit.setReadOnly(True)
        row.addWidget(edit, 1)
        dots = QPushButton("...", box)
        dots.setFixedWidth(28)
        dots.clicked.connect(self._select_active_block)
        row.addWidget(dots)
        lay.addWidget(box)

    def _select_active_block(self) -> None:
        # [Selection of Active mesh block] — cab currently stores a single
        # RootBlock, so the dialog is informational.
        QMessageBox.information(
            self, "Selection of Active mesh block",
            "RootBlock\n\n(Only the root block exists in this project; "
            "multiblock editing is not supported by the cab viewer yet.)")

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)

    # ------------------------------------------------------ Basic Setting

    def _build_basic_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setSpacing(6)

        vd = QGroupBox("Vertex detection", page)
        vl = QVBoxLayout(vd)
        self._radio_group(vl, self._DETECTIONS, "detection_radios")
        lay.addWidget(vd)

        dt = QGroupBox("Domain type", page)
        dl_dt = QVBoxLayout(dt)
        self._radio_group(dl_dt, self._DOMAIN_TYPES, "domain_type_radios",
                          cols=3)
        note = QLabel(
            "Note: cylindrical/axial are stored on the model; native "
            "gridding still generates cartesian AABB axes.", dt)
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-size: 10px;")
        dl_dt.addWidget(note)
        lay.addWidget(dt)

        mg = QGroupBox("Method of Gridding", page)
        ml = QVBoxLayout(mg)
        self.method_radios: dict[str, QRadioButton] = {}
        for label, key in self._METHODS:
            rb = QRadioButton(label, mg)
            ml.addWidget(rb)
            self.method_radios[key] = rb
            rb.toggled.connect(self._on_method_changed)
        self.num_box = QGroupBox("Specifying the numbers of elements", mg)
        nl = QVBoxLayout(self.num_box)
        self.num_total_radio = QRadioButton("Total number of elements",
                                            self.num_box)
        trow = QHBoxLayout()
        trow.addWidget(self.num_total_radio)
        trow.addStretch(1)
        self.target = QDoubleSpinBox(self.num_box)
        self.target.setRange(8, 1.0e12)
        self.target.setDecimals(0)
        self.target.setValue(125000)
        self.target.setGroupSeparatorShown(True)
        trow.addWidget(self.target)
        nl.addLayout(trow)
        self.num_axis_radio = QRadioButton(
            "The number of elements in each axis direction", self.num_box)
        nl.addWidget(self.num_axis_radio)
        arow = QHBoxLayout()
        arow.addStretch(1)
        self.target_axes: dict[str, QSpinBox] = {}
        for i, ax in enumerate("xyz"):
            sb = QSpinBox(self.num_box)
            sb.setRange(2, 100000)
            sb.setValue((253, 152, 54)[i])
            self.target_axes[ax] = sb
            arow.addWidget(sb)
            if ax != "z":
                arow.addWidget(QLabel("x", self.num_box))
        nl.addLayout(arow)
        self.num_total_radio.setChecked(True)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Sub-block mesh refinement factor",
                              self.num_box))
        srow.addStretch(1)
        self.subblock_factor = QSpinBox(self.num_box)
        self.subblock_factor.setRange(1, 16)
        self.subblock_factor.setValue(2)
        srow.addWidget(self.subblock_factor)
        nl.addLayout(srow)
        ml.addWidget(self.num_box)
        lay.addWidget(mg)

        dp = QGroupBox("Division parameters of root block", page)
        dl = QGridLayout(dp)
        for i, ax in enumerate(("X", "Y", "Z")):
            lab = QLabel(ax, dp)
            lab.setAlignment(Qt.AlignCenter)
            dl.addWidget(lab, 0, i + 1)
        self.std = self._axis_spins(value=0.5)
        self.thr = self._axis_spins(value=0.1)
        self.ratio = self._axis_spins(value=1.0)
        self.ratio_ext = self._axis_spins(value=1.1)
        rows = (
            ("Standard length", self.std, "std_common", False),
            ("Threshold length", self.thr, "thr_common", False),
            ("Geometric ratio\n(internal)", self.ratio, "ratio_common", True),
            ("(external)", self.ratio_ext, "ratio_ext_common", True),
        )
        for r, (label, spins, common_attr, checked) in enumerate(rows, 1):
            dl.addWidget(QLabel(label, dp), r, 0)
            for i, ax in enumerate("xyz"):
                dl.addWidget(spins[ax], r, i + 1)
            common = QCheckBox("Common", dp)
            common.setChecked(checked)
            setattr(self, common_attr, common)
            dl.addWidget(common, r, 4)
            common.toggled.connect(
                lambda on, s=spins: self._on_common_toggled(s, on))
            for ax in "yz":
                spins[ax].setEnabled(not checked)
        for spins in (self.std, self.thr, self.ratio, self.ratio_ext):
            spins["x"].valueChanged.connect(
                lambda v, s=spins: self._on_common_value(s, v))
        lay.addWidget(dp)

        opt = QVBoxLayout()
        self.chk_discard = QCheckBox(
            "Generate mesh discarding the existing mesh", page)
        self.chk_discard.setChecked(True)
        self.chk_internal = QCheckBox(
            "Generate mesh as internal region", page)
        self.chk_child_only = QCheckBox(
            "Consider only child-blocks for gridding", page)
        self.chk_child_only.setEnabled(False)   # multiblock NYI
        self.chk_lower_level = QCheckBox(
            "Consider rough grid of lower level block", page)
        self.chk_lower_level.setEnabled(False)  # multiblock NYI
        self.chk_remove_edge_all = QCheckBox(
            "Remove edge contact elements of all parts", page)
        for cb in (self.chk_discard, self.chk_internal, self.chk_child_only,
                   self.chk_lower_level, self.chk_remove_edge_all):
            opt.addWidget(cb)
        urow = QHBoxLayout()
        urow.addLayout(opt)
        urow.addStretch(1)
        self.basic_unit_label = QLabel("Unit : mm", page)
        urow.addWidget(self.basic_unit_label)
        lay.addLayout(urow)

        intf = QGroupBox("Interference", page)
        il = QHBoxLayout(intf)
        self.chk_reconstruct = QCheckBox(
            "Execute reconstruction of interfering parts", intf)
        self.chk_reconstruct.setChecked(True)
        il.addWidget(self.chk_reconstruct)
        il.addStretch(1)
        self.btn_reconstruct = QPushButton("Reconstruct", intf)
        self.btn_reconstruct.clicked.connect(self._reconstruct)
        il.addWidget(self.btn_reconstruct)
        help_btn = QPushButton("?", intf)
        help_btn.setFixedWidth(24)
        help_btn.setStyleSheet("color: red; font-weight: bold;")
        help_btn.clicked.connect(self._open_gridding_manual)
        il.addWidget(help_btn)
        lay.addWidget(intf)
        lay.addStretch(1)
        return page

    def _open_gridding_manual(self) -> None:
        import os as _os
        path = (r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML"
                r"\Pre_eng\St_pre_Mesh-Gridding.html")
        if _os.path.isfile(path):
            _os.startfile(path)  # noqa: S606
        else:
            self._log(f"Manual not found: {path}", "WARN")

    def _on_method_changed(self) -> None:
        by_num = self.method_radios["num_elements"].isChecked()
        self.num_box.setEnabled(by_num)
        rough_only = self.method_radios["rough_only"].isChecked()
        if rough_only:
            for spins in (self.std, self.thr, self.ratio, self.ratio_ext):
                for sb in spins.values():
                    sb.setEnabled(False)
        else:
            self._restore_common_state()

    def _restore_common_state(self) -> None:
        for spins, common in (
                (self.std, self.std_common), (self.thr, self.thr_common),
                (self.ratio, self.ratio_common),
                (self.ratio_ext, self.ratio_ext_common)):
            spins["x"].setEnabled(True)
            for ax in "yz":
                spins[ax].setEnabled(not common.isChecked())

    def _on_common_toggled(self, spins, on: bool) -> None:
        for ax in "yz":
            spins[ax].setEnabled(not on)
        if on:
            v = spins["x"].value()
            spins["y"].setValue(v)
            spins["z"].setValue(v)

    def _on_common_value(self, spins, value: float) -> None:
        common = {id(self.std): self.std_common, id(self.thr):
                  self.thr_common, id(self.ratio): self.ratio_common,
                  id(self.ratio_ext): self.ratio_ext_common}[id(spins)]
        if common.isChecked():
            spins["y"].setValue(value)
            spins["z"].setValue(value)

    # ---------------------------------------------------------- Parameter

    def _build_parameter_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        mb_box = QGroupBox("Multiblock", page)
        ml = QVBoxLayout(mb_box)
        self.block_tree = QTreeWidget(mb_box)
        self.block_tree.setHeaderLabels(
            ["Block", "Standard length", "Geometric ratio",
             "Threshold length"])
        self.block_tree.setRootIsDecorated(False)
        self.block_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.block_tree.customContextMenuRequested.connect(
            self._block_context)
        self.block_tree.itemDoubleClicked.connect(
            lambda *_: self._edit_mesh_block())
        ml.addWidget(self.block_tree)
        note = QLabel("(The block parameter can be set in the dialog "
                      "opened by right-clicking a block name)", mb_box)
        note.setStyleSheet("color: #555; font-size: 11px;")
        ml.addWidget(note)
        lay.addWidget(mb_box, 1)

        lay.addWidget(QLabel("Mesh option of each part", page))
        self.part_mesh_tree = QTreeWidget(page)
        self.part_mesh_tree.setHeaderLabels(
            ["PartsName", "Select Vertex", "NumGridLines",
             "Priority of rough grid", "Priority of part"])
        self.part_mesh_tree.setRootIsDecorated(False)
        lay.addWidget(self.part_mesh_tree, 2)
        note2 = QLabel("(The vertex detection type and the number of mesh "
                       "grid lines placed on each part can be set in the "
                       "dialog opened by right-clicking a part name)", page)
        note2.setStyleSheet("color: #555; font-size: 11px;")
        note2.setWordWrap(True)
        lay.addWidget(note2)
        return page

    def _populate_parameter_tab(self) -> None:
        import cab_grid
        self.block_tree.clear()

        def add_item(blk: dict, parent_item=None) -> None:
            divide = cab_grid._parse_block_vec(
                blk.get("divide", ""), 1.0)
            ratio = cab_grid._parse_block_vec(
                blk.get("ratio", ""), 1.0)
            limit = cab_grid._parse_block_vec(
                blk.get("limit", ""), 0.1)
            item = QTreeWidgetItem([
                blk["name"],
                "/".join(f"{v:g}" for v in divide),
                "/".join(f"{v:g}" for v in ratio),
                "/".join(f"{v:g}" for v in limit),
            ])
            if parent_item is None:
                self.block_tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            for child in blk.get("children", []):
                add_item(child, item)

        for blk in self.model.mesh_blocks():
            add_item(blk)

        self.part_mesh_tree.clear()
        self._part_vertex_combos: dict[str, QComboBox] = {}
        options = ["default"] + [k for _l, k in self._DETECTIONS]
        for p in self.model.parts():
            item = QTreeWidgetItem([p.name, "", "---", "3", "0"])
            self.part_mesh_tree.addTopLevelItem(item)
            combo = QComboBox(self.part_mesh_tree)
            combo.addItems(options)
            current = self.model.part_mesh_option(p.name) or "default"
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.currentTextChanged.connect(
                lambda text, name=p.name: self._on_part_vertex(name, text))
            self.part_mesh_tree.setItemWidget(item, 1, combo)
            self._part_vertex_combos[p.name] = combo

    def _on_part_vertex(self, name: str, detection: str) -> None:
        if detection == "default":
            return
        self.model.set_part_mesh_option(name, detection)
        self._log(f"Mesh option: {name} vertex detection = {detection}")

    def _block_context(self, pos) -> None:
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Edit mesh block", self._edit_mesh_block)
        menu.addAction("Create mesh block", self._create_child_block)
        menu.addAction("Insert mesh block", self._create_child_block)
        for label in ("Cancel mesh block", "Create connected block",
                      "Create bounding block"):
            menu.addAction(
                label, lambda l=label: self._log(
                    f"[{l}] advanced multiblock not yet supported.",
                    "WARN"))
        menu.exec_(self.block_tree.viewport().mapToGlobal(pos))

    def _create_child_block(self) -> None:
        """L7.6: append a nested child <block> (STpre multiblock layout)."""
        item = self.block_tree.currentItem()
        parent = item.text(0) if item is not None else "RootBlock"
        dlg = QDialog(self)
        dlg.setWindowTitle("Create mesh block")
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        spins = []
        for label in ("X min", "Y min", "Z min",
                      "X max", "Y max", "Z max"):
            sp = QDoubleSpinBox(dlg)
            sp.setRange(-1.0e9, 1.0e9)
            sp.setDecimals(4)
            spins.append(sp)
            form.addRow(label + " (mm)", sp)
        length = QDoubleSpinBox(dlg)
        length.setRange(1e-6, 1e9)
        length.setValue(0.5)
        form.addRow("Standard length (mm)", length)
        limit = QDoubleSpinBox(dlg)
        limit.setRange(1e-6, 1e9)
        limit.setValue(0.1)
        form.addRow("Threshold (mm)", limit)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton("OK", dlg)
        cancel = QPushButton("Cancel", dlg)
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if not dlg.exec_():
            return
        lo = tuple(spins[i].value() for i in range(3))
        hi = tuple(spins[i + 3].value() for i in range(3))
        n = 1
        blocks = self.model.mesh_blocks()
        names = set()

        def collect(blk):
            names.add(blk["name"])
            for c in blk.get("children", []):
                collect(c)

        for blk in blocks:
            collect(blk)
        while f"ChildBlock{n}" in names:
            n += 1
        name = f"ChildBlock{n}"
        if not self.model.add_child_block(
                name, parent, lo, hi,
                length=(length.value(), length.value(), length.value()),
                limit=(limit.value(), limit.value(), limit.value())):
            self._log(f"Create mesh block '{name}' failed.", "WARN")
            return
        self._populate_parameter_tab()
        self.chk_child_only.setEnabled(True)
        self.chk_lower_level.setEnabled(True)
        self._log(
            f"Created mesh block '{name}' under '{parent}' "
            f"({lo[0]:g},{lo[1]:g},{lo[2]:g})-"
            f"({hi[0]:g},{hi[1]:g},{hi[2]:g}) mm.")

    def _edit_mesh_block(self) -> None:
        """[Mesh: Block] dialog: selected block std/ratio/threshold."""
        import cab_grid
        item = self.block_tree.currentItem()
        name = item.text(0) if item is not None else "RootBlock"
        dlg = QDialog(self)
        dlg.setWindowTitle("Mesh: Block")
        lay = QVBoxLayout(dlg)
        grid = QGridLayout()
        for i, ax in enumerate(("X", "Y", "Z")):
            grid.addWidget(QLabel(ax, dlg), 0, i + 1)
        if name == "RootBlock":
            divide = [self.std[a].value() for a in "xyz"]
            limit = [self.thr[a].value() for a in "xyz"]
            ratio = [self.ratio[a].value() for a in "xyz"]
        else:
            divide = list(cab_grid._parse_block_vec(
                self.model.block_param(name, "divide_length", "1,1,1"),
                1.0))
            limit = list(cab_grid._parse_block_vec(
                self.model.block_param(name, "limit", "0.1,0.1,0.1"),
                0.1))
            ratio = list(cab_grid._parse_block_vec(
                self.model.block_param(name, "divide_ratio1", "1,1,1"),
                1.0))
        rows = (("Standard length", divide),
                ("Threshold length", limit),
                ("Geometric ratio", ratio))
        spins: list[tuple[str, QDoubleSpinBox]] = []
        for r, (label, src) in enumerate(rows, 1):
            grid.addWidget(QLabel(label, dlg), r, 0)
            for i, ax in enumerate("xyz"):
                sb = QDoubleSpinBox(dlg)
                sb.setRange(1.0e-6, 1.0e9)
                sb.setDecimals(6)
                sb.setValue(src[i])
                grid.addWidget(sb, r, i + 1)
                spins.append((ax + str(r), sb))
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if dlg.exec_():
            for r, (_label, vals) in enumerate(rows, 1):
                for i, ax in enumerate("xyz"):
                    sb = dict(spins)[ax + str(r)]
                    vals[i] = sb.value()
            if name == "RootBlock":
                for i, ax in enumerate("xyz"):
                    self.std[ax].setValue(divide[i])
                    self.thr[ax].setValue(limit[i])
                    self.ratio[ax].setValue(ratio[i])
            self.model.set_block_param(
                name, "divide_length",
                ",".join(f"{v:g}" for v in divide), unit="mm")
            self.model.set_block_param(
                name, "limit",
                ",".join(f"{v:g}" for v in limit), unit="mm")
            self.model.set_block_param(
                name, "divide_ratio1",
                ",".join(f"{v:g}" for v in ratio))
            self._populate_parameter_tab()
            self._log(f"Mesh block '{name}' parameters updated.")

    # ------------------------------------------------------ Detail meshing

    def _build_detail_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self._active_block_row(lay)

        mid = QHBoxLayout()
        ax_box = QGroupBox("Direction of axis", page)
        al = QHBoxLayout(ax_box)
        self.detail_axis: dict[str, QRadioButton] = {}
        for ax in "XYZ":
            rb = QRadioButton(ax, ax_box)
            al.addWidget(rb)
            self.detail_axis[ax.lower()] = rb
            rb.toggled.connect(self._refresh_detail_ranges)
        mid.addWidget(ax_box)
        n_box = QGroupBox("Number of element", page)
        nl = QHBoxLayout(n_box)
        self.detail_n = QSpinBox(n_box)
        self.detail_n.setRange(1, 10000)
        self.detail_n.setValue(5)
        nl.addWidget(self.detail_n)
        mid.addWidget(n_box)
        lay.addLayout(mid)

        dd = QGroupBox("Direction of division", page)
        dl = QHBoxLayout(dd)
        self.detail_dir: dict[str, QRadioButton] = {}
        for label, key in (("-->", "forward"), ("--><--", "symmetric"),
                           ("<--", "backward")):
            rb = QRadioButton(label, dd)
            dl.addWidget(rb)
            self.detail_dir[key] = rb
        self.detail_dir["forward"].setChecked(True)
        lay.addWidget(dd)

        gr = QGroupBox("Geometric ratio", page)
        gl = QHBoxLayout(gr)
        self.detail_ratio_slider = QSlider(Qt.Horizontal, gr)
        self.detail_ratio_slider.setRange(10, 1000)
        self.detail_ratio_slider.setValue(100)
        gl.addWidget(self.detail_ratio_slider, 1)
        self.detail_ratio = QDoubleSpinBox(gr)
        self.detail_ratio.setRange(0.1, 10.0)
        self.detail_ratio.setDecimals(3)
        self.detail_ratio.setValue(1.0)
        gl.addWidget(self.detail_ratio)
        self.detail_ratio_slider.valueChanged.connect(
            lambda v: self.detail_ratio.setValue(v / 100.0))
        self.detail_ratio.valueChanged.connect(
            lambda v: self.detail_ratio_slider.setValue(int(v * 100)))
        lay.addWidget(gr)

        self.detail_retain = QCheckBox(
            "Retain rough grids within the range", page)
        lay.addWidget(self.detail_retain)
        self.detail_thr_chk = QCheckBox(
            "Consider a threshold element size", page)
        lay.addWidget(self.detail_thr_chk)

        ms = QGroupBox("Method of selection", page)
        msl = QVBoxLayout(ms)
        txt = QLabel("Pick the range with the two combo boxes below "
                     "(cab viewer substitutes mouse picking).", ms)
        txt.setWordWrap(True)
        msl.addWidget(txt)
        rng = QHBoxLayout()
        rng.addWidget(QLabel("From", ms))
        self.detail_from = QComboBox(ms)
        self.detail_from.setEditable(True)
        rng.addWidget(self.detail_from, 1)
        rng.addWidget(QLabel("To", ms))
        self.detail_to = QComboBox(ms)
        self.detail_to.setEditable(True)
        rng.addWidget(self.detail_to, 1)
        self.btn_divide = QPushButton("Divide", ms)
        self.btn_divide.clicked.connect(self._divide_range)
        rng.addWidget(self.btn_divide)
        msl.addLayout(rng)
        lay.addWidget(ms)

        th = QGroupBox("Threshold element size of active block", page)
        tg = QGridLayout(th)
        self.detail_thr = self._axis_spins(value=0.1)
        for i, ax in enumerate(("X", "Y", "Z")):
            lab = QLabel(ax, th)
            lab.setAlignment(Qt.AlignCenter)
            tg.addWidget(lab, 0, i * 2)
        for i, ax in enumerate("xyz"):
            tg.addWidget(self.detail_thr[ax], 1, i * 2)
            tg.addWidget(QLabel("mm", th), 1, i * 2 + 1)
        lay.addWidget(th)
        lay.addStretch(1)
        # default axis last: the slot touches detail_from/detail_to
        self.detail_axis["x"].setChecked(True)
        return page

    def _current_axis(self, radios: dict[str, QRadioButton]) -> str:
        for ax, rb in radios.items():
            if rb.isChecked():
                return ax
        return "x"

    def _refresh_detail_ranges(self) -> None:
        ax = self._current_axis(self.detail_axis)
        entries = self.model.mesh_axis_entries(ax)
        for combo in (self.detail_from, self.detail_to):
            combo.clear()
            for val, _mark in entries:
                combo.addItem(f"{val:g}")
        if entries:
            self.detail_from.setCurrentIndex(0)
            self.detail_to.setCurrentIndex(len(entries) - 1)

    def _divide_range(self) -> None:
        import cab_grid

        ax = self._current_axis(self.detail_axis)
        try:
            a = float(self.detail_from.currentText())
            b = float(self.detail_to.currentText())
        except ValueError:
            self._log("Detail meshing: invalid range.", "WARN")
            return
        if a >= b:
            self._log("Detail meshing: From must be smaller than To.",
                      "WARN")
            return
        entries = self.model.mesh_axis_entries(ax)
        if not entries:
            self._log("Detail meshing: no mesh block.", "WARN")
            return
        vals = [v for v, _m in entries]
        retain = None
        if self.detail_retain.isChecked():
            retain = [v for v, m in entries if m in ("S", "B", "F")]
        threshold = self.detail_thr[ax].value() \
            if self.detail_thr_chk.isChecked() else 0.0
        mode = self._current_axis(self.detail_dir)
        new_vals = cab_grid.divide_interval(
            vals, a, b, self.detail_n.value(),
            ratio=self.detail_ratio.value(), mode=mode,
            threshold=threshold, retain=retain)
        marks = {round(v, 9): m for v, m in entries}
        self.model.set_mesh_axis(
            ax, [(v, marks.get(round(v, 9), "N")) for v in new_vals])
        self._after_grid_edit(
            f"Detail meshing: {ax} [{a:g}, {b:g}] -> "
            f"{self.detail_n.value()} elements ({mode})")

    # --------------------------------------------------------------- Edit

    def _build_edit_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self._active_block_row(lay)

        top = QHBoxLayout()
        ax_box = QGroupBox("Coordinate axis", page)
        al = QHBoxLayout(ax_box)
        self.edit_axis: dict[str, QRadioButton] = {}
        for ax in "XYZ":
            rb = QRadioButton(ax, ax_box)
            al.addWidget(rb)
            self.edit_axis[ax.lower()] = rb
            rb.toggled.connect(self._refresh_edit_list)
        top.addWidget(ax_box)
        ty_box = QGroupBox("Grid type", page)
        tl = QHBoxLayout(ty_box)
        self.edit_type: dict[str, QRadioButton] = {}
        for label, mark in self._GRID_TYPES:
            rb = QRadioButton(label, ty_box)
            tl.addWidget(rb)
            self.edit_type[mark] = rb
        self.edit_type["N"].setChecked(True)
        top.addWidget(ty_box)
        lay.addLayout(top)

        row = QHBoxLayout()
        row.addWidget(QLabel("Coord.", page))
        self.edit_coord = QDoubleSpinBox(page)
        self.edit_coord.setRange(-1.0e9, 1.0e9)
        self.edit_coord.setDecimals(6)
        row.addWidget(self.edit_coord)
        # List-based pick (not STpre mouse vertex pick) — labeled clearly.
        self.btn_select = QPushButton("Select from list…", page)
        self.btn_select.setToolTip(
            "Pick a grid / part reference coordinate from a list "
            "(mouse vertex pick is not available in the cab viewer).")
        self.btn_select.clicked.connect(self._edit_select)
        row.addWidget(self.btn_select)
        for label in ("Preview", "Delete", "Edit", "Add"):
            btn = QPushButton(label, page)
            btn.clicked.connect(getattr(self, f"_edit_{label.lower()}"))
            row.addWidget(btn)
            setattr(self, f"btn_{label.lower()}", btn)
        lay.addLayout(row)
        pick_hint = QLabel(
            "Select from list… = choose a coordinate from the grid-line "
            "list or part min/max (not mouse pick).", page)
        pick_hint.setStyleSheet("color: #666; font-size: 10px;")
        pick_hint.setWordWrap(True)
        lay.addWidget(pick_hint)
        self.edit_thr_chk = QCheckBox(
            "Consider a threshold element size (unit mm)", page)
        lay.addWidget(self.edit_thr_chk)

        self.edit_list = QTreeWidget(page)
        self.edit_list.setHeaderLabels(
            ["No.", "Coordinates", "Type", "Referred parts"])
        self.edit_list.setRootIsDecorated(False)
        self.edit_list.setSelectionMode(
            QTreeWidget.ExtendedSelection)
        self.edit_list.itemSelectionChanged.connect(self._on_edit_selected)
        lay.addWidget(self.edit_list, 1)
        # default axis last: the slot touches edit_list
        self.edit_axis["x"].setChecked(True)
        return page

    def _refresh_edit_list(self) -> None:
        ax = self._current_axis(self.edit_axis)
        entries = self.model.mesh_axis_entries(ax)
        self.edit_list.clear()
        refs = self._part_reference_coords(ax)
        for i, (val, mark) in enumerate(entries, start=1):
            referred = [name for c, name in refs
                        if abs(c - val) < 1e-6]
            QTreeWidgetItem(self.edit_list, [
                str(i), f"{val:.10g}", self._MARK_LABEL.get(mark, mark),
                ",".join(referred)])
        self.edit_list.resizeColumnToContents(0)

    def _part_reference_coords(self, axis: str) -> list[tuple[float, str]]:
        """(coordinate, part name) for part min/max along ``axis`` (mm)."""
        ax_i = "xyz".index(axis)
        refs: list[tuple[float, str]] = []
        for part in self.cad_meshes or []:
            pts = np.asarray(part.points, dtype=np.float64)
            if len(pts) == 0:
                continue
            col = pts[:, ax_i] * 1000.0   # m -> mm
            refs.append((float(col.min()), part.name))
            refs.append((float(col.max()), part.name))
        return refs

    def _on_edit_selected(self) -> None:
        items = self.edit_list.selectedItems()
        if items:
            self.edit_coord.setValue(float(items[0].text(1)))

    def _edit_entries(self) -> tuple[str, list[tuple[float, str]]]:
        ax = self._current_axis(self.edit_axis)
        return ax, self.model.mesh_axis_entries(ax)

    def _selected_rows(self) -> list[int]:
        return sorted(int(i.text(0)) - 1
                      for i in self.edit_list.selectedItems())

    def _edit_select(self) -> None:
        """List-based coordinate pick (replaces STpre mouse vertex pick)."""
        ax = self._current_axis(self.edit_axis)
        entries = self.model.mesh_axis_entries(ax)
        refs = self._part_reference_coords(ax)
        labels: list[str] = []
        values: list[float] = []
        for i, (val, mark) in enumerate(entries, start=1):
            labels.append(
                f"grid #{i}: {val:.10g} mm  [{self._MARK_LABEL.get(mark, mark)}]")
            values.append(val)
        for c, name in refs:
            labels.append(f"part {name}: {c:.10g} mm")
            values.append(c)
        if not labels:
            self._log("Select from list: no grid lines or part refs.",
                      "WARN")
            return
        # Prefer current list selection when present
        rows = self._selected_rows()
        if len(rows) == 1 and 0 <= rows[0] < len(entries):
            self.edit_coord.setValue(entries[rows[0]][0])
            self._log(
                f"Select from list: grid row → {ax} = "
                f"{entries[rows[0]][0]:g} mm")
            return
        choice, ok = QInputDialog.getItem(
            self, "Select grid coordinate (list)",
            f"Axis {ax.upper()} — pick a coordinate "
            f"(list-based; not mouse pick):",
            labels, 0, False)
        if not ok:
            return
        idx = labels.index(choice)
        self.edit_coord.setValue(values[idx])
        self._log(f"Select from list: {ax} = {values[idx]:g} mm")

    def _edit_preview(self) -> None:
        self._log(f"Preview grid line: {self._current_axis(self.edit_axis)}"
                  f" = {self.edit_coord.value():g} mm")

    def _edit_add(self) -> None:
        ax, entries = self._edit_entries()
        val = self.edit_coord.value()
        if any(abs(v - val) < 1e-9 for v, _m in entries):
            self._log("A grid line on an already existing grid can not "
                      "be added.", "WARN")
            return
        mark = self._current_axis(self.edit_type)
        entries.append((val, mark))
        entries.sort(key=lambda e: e[0])
        if self.edit_thr_chk.isChecked():
            thr = self.thr[ax].value()
            entries = [e for i, e in enumerate(entries)
                       if i == 0 or e[0] - entries[i - 1][0] >= thr]
        self.model.set_mesh_axis(ax, entries)
        self._after_grid_edit(f"Grid line added: {ax} = {val:g} [{mark}]")

    def _edit_delete(self) -> None:
        ax, entries = self._edit_entries()
        rows = self._selected_rows()
        if not rows:
            self._log("Delete: select grid line(s) in the list.", "WARN")
            return
        keep = [e for i, e in enumerate(entries)
                if i not in rows or e[1] == "B"
                or i == 0 or i == len(entries) - 1]
        removed = len(entries) - len(keep)
        self.model.set_mesh_axis(ax, keep)
        self._after_grid_edit(f"Deleted {removed} grid line(s) on {ax}")

    def _edit_edit(self) -> None:
        ax, entries = self._edit_entries()
        rows = self._selected_rows()
        if len(rows) != 1:
            self._log("Edit: select exactly one grid line.", "WARN")
            return
        i = rows[0]
        if entries[i][1] == "B":
            self._log("Block boundary lines can not be edited.", "WARN")
            return
        mark = self._current_axis(self.edit_type)
        entries[i] = (self.edit_coord.value(), mark)
        entries.sort(key=lambda e: e[0])
        self.model.set_mesh_axis(ax, entries)
        self._after_grid_edit(
            f"Grid line edited: {ax} = {self.edit_coord.value():g} [{mark}]")

    def _after_grid_edit(self, message: str) -> None:
        self._refresh_edit_list()
        self._refresh_detail_ranges()
        self._update_element_label()
        self._log(message)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()

    # ----------------------------------------------------------- Deletion

    def _build_deletion_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self._active_block_row(lay)

        top = QHBoxLayout()
        ax_box = QGroupBox("Direction to select", page)
        al = QHBoxLayout(ax_box)
        self.del_axis: dict[str, QRadioButton] = {}
        for ax in "XYZ":
            rb = QRadioButton(ax, ax_box)
            al.addWidget(rb)
            self.del_axis[ax.lower()] = rb
        self.del_axis["x"].setChecked(True)
        top.addWidget(ax_box)
        self.btn_delete = QPushButton("Executing Deletion", page)
        self.btn_delete.clicked.connect(self._delete_grids)
        top.addWidget(self.btn_delete)
        lay.addLayout(top)

        tg = QGroupBox("Target of deletion", page)
        tl = QVBoxLayout(tg)
        self.del_target: dict[str, QRadioButton] = {}
        for label, key in (
                ("Selected\n(Selected grid lines, all mesh grids within "
                 "selected range)", "selected"),
                ("All but rough grids", "all_but_rough"),
                ("All  ( all but grid lines through maximum/minimum "
                 "coordinate\nof each part )", "all")):
            rb = QRadioButton(label, tg)
            tl.addWidget(rb)
            self.del_target[key] = rb
        self.del_target["all_but_rough"].setChecked(True)
        self.del_cancel_fixed = QCheckBox("Fixed Type is cancelled.", tg)
        tl.addWidget(self.del_cancel_fixed)
        lay.addWidget(tg)

        ms = QGroupBox("Method of Selection", page)
        msl = QVBoxLayout(ms)
        txt = QLabel("By mouse to select a range, select the second mesh "
                     "while holding Shift key.\n(cab viewer: 'Selected' "
                     "uses the current selection of the Edit tab list.)", ms)
        txt.setWordWrap(True)
        msl.addWidget(txt)
        lay.addWidget(ms)
        self.del_retain = QCheckBox(
            "Retain rough division mesh within the range.", page)
        lay.addWidget(self.del_retain)
        lay.addStretch(1)
        return page

    def _delete_grids(self) -> None:
        import cab_grid

        ax = self._current_axis(self.del_axis)
        entries = self.model.mesh_axis_entries(ax)
        if not entries:
            self._log("Deletion: no mesh block.", "WARN")
            return
        if self.del_cancel_fixed.isChecked():
            entries = [(v, "N" if m == "F" else m) for v, m in entries]
        target = self._current_axis(self.del_target)
        if target == "selected":
            rows = self._selected_rows()
            if not rows:
                self._log("Deletion (Selected): select grid line(s) in "
                          "the Edit tab list first.", "WARN")
                return
            keep_marks = ("S", "B", "F") if self.del_retain.isChecked() \
                else ("B",)
            keep = [e for i, e in enumerate(entries)
                    if i not in rows or e[1] in keep_marks
                    or i == 0 or i == len(entries) - 1]
        else:
            refs = None
            if target == "all":
                refs = [c for c, _n in self._part_reference_coords(ax)]
            keep = cab_grid.delete_grid_lines(entries, target, refs)
        removed = len(entries) - len(keep)
        self.model.set_mesh_axis(ax, keep)
        self._after_grid_edit(
            f"Deletion ({target}) on {ax}: removed {removed} line(s), "
            f"{len(keep)} remain")

    # ------------------------------------------------------------- Others

    def _build_others_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)

        ec = QGroupBox("Remove edge-contacts of specified part", page)
        el = QVBoxLayout(ec)
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Part name", ec))
        self.edge_part = QLineEdit(ec)
        nrow.addWidget(self.edge_part, 1)
        el.addLayout(nrow)
        brow = QHBoxLayout()
        self.btn_investigate = QPushButton(
            "Investigate the number of\nedge-contact elements", ec)
        self.btn_investigate.clicked.connect(self._investigate_edge_contact)
        brow.addWidget(self.btn_investigate)
        brow.addWidget(QLabel("=>", ec))
        self.btn_remove_edge = QPushButton("Remove edge-contacts", ec)
        self.btn_remove_edge.clicked.connect(self._remove_edge_contacts)
        brow.addWidget(self.btn_remove_edge)
        el.addLayout(brow)
        lay.addWidget(ec)

        mp = QGroupBox("Meshing of specified part", page)
        ml = QVBoxLayout(mp)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Part name", mp))
        self.mesh_part = QLineEdit(mp)
        prow.addWidget(self.mesh_part, 1)
        ml.addLayout(prow)
        mrow = QHBoxLayout()
        self.btn_part_meshing = QPushButton("Meshing", mp)
        self.btn_part_meshing.clicked.connect(self._mesh_single_part)
        mrow.addWidget(self.btn_part_meshing)
        self.chk_part_edge = QCheckBox("Remove edge-contacts", mp)
        self.chk_part_interf = QCheckBox("Element interferences", mp)
        mrow.addWidget(self.chk_part_edge)
        mrow.addWidget(self.chk_part_interf)
        ml.addLayout(mrow)
        lay.addWidget(mp)

        prm = QGroupBox("Meshing parameter", page)
        pl = QGridLayout(prm)
        pl.addWidget(QLabel("Edge tolerance", prm), 0, 0)
        self.p_edge_tol = QDoubleSpinBox(prm)
        self.p_edge_tol.setDecimals(6)
        self.p_edge_tol.setRange(0.0, 1.0)
        self.p_edge_tol.setValue(0.0001)
        self.p_edge_tol.setSingleStep(0.0001)
        pl.addWidget(self.p_edge_tol, 0, 1)
        pl.addWidget(QLabel("Search range\nfor element face", prm), 0, 2)
        self.p_face_search = QDoubleSpinBox(prm)
        self.p_face_search.setRange(0.0, 100.0)
        self.p_face_search.setValue(1.0)
        pl.addWidget(self.p_face_search, 0, 3)
        pl.addWidget(QLabel("Element threshold", prm), 1, 0)
        self.p_elem_thr = QDoubleSpinBox(prm)
        self.p_elem_thr.setRange(0.0, 1.0)
        self.p_elem_thr.setSingleStep(0.05)
        self.p_elem_thr.setValue(0.5)
        pl.addWidget(self.p_elem_thr, 1, 1)
        lay.addWidget(prm)
        self.p_edge_tol.valueChanged.connect(
            lambda v: self.model.set_mesh_control_value(
                "edge_eps", f"{v:g}"))
        self.p_elem_thr.valueChanged.connect(
            lambda v: self.model.set_mesh_control_value(
                "element_threshold", f"{v:g}"))
        self.p_face_search.valueChanged.connect(
            lambda v: self.model.set_mesh_control_value(
                "face_search", f"{v:g}"))

        bf = QGroupBox(
            "Generate element face on computational domain boundary", page)
        bl = QHBoxLayout(bf)
        self.boundary_face: dict[str, QRadioButton] = {}
        for label, key in (("Normal", "normal"),
                           ("Exclude symmetrical face", "excl_symm"),
                           ("Exclude all", "excl_all")):
            rb = QRadioButton(label, bf)
            bl.addWidget(rb)
            self.boundary_face[key] = rb
            rb.toggled.connect(self._on_boundary_face)
        self.boundary_face["normal"].setChecked(True)
        lay.addWidget(bf)

        dup = QGroupBox("Check duplication of flux condition faces", page)
        dupl = QVBoxLayout(dup)
        self.chk_flux_dup = QCheckBox("Activate", dup)
        self.chk_flux_dup.toggled.connect(
            lambda on: self.model.set_mesh_control_value(
                "check_scheme", "1" if on else "0"))
        dupl.addWidget(self.chk_flux_dup)
        lay.addWidget(dup)

        mm = QGroupBox("Meshing method", page)
        mml = QVBoxLayout(mm)
        mml.addWidget(QLabel(
            "Convert the element shape to that of the block in the "
            "upper level.", mm))
        srow = QHBoxLayout()
        self.chk_v8_solid = QCheckBox("Solid parts", mm)
        self.chk_v8_panel = QCheckBox("Panel parts", mm)
        self.chk_v8_panel.setChecked(True)
        self.chk_v8_solid.toggled.connect(
            lambda on: self.model.set_mesh_control_value(
                "solid_scheme", "0" if on else "1"))
        self.chk_v8_panel.toggled.connect(
            lambda on: self.model.set_mesh_control_value(
                "panel_scheme", "0" if on else "1"))
        srow.addWidget(self.chk_v8_solid)
        srow.addWidget(self.chk_v8_panel)
        srow.addStretch(1)
        mml.addLayout(srow)
        lay.addWidget(mm)

        par = QGroupBox("Parallel number on mesh division", page)
        parl = QHBoxLayout(par)
        parl.addWidget(QLabel("Degree of parallelism", par))
        import os as _os
        self.p_parallel = QSpinBox(par)
        self.p_parallel.setRange(1, 256)
        self.p_parallel.setValue(min(2, _os.cpu_count() or 1))
        self.p_parallel.valueChanged.connect(
            lambda v: self.model.set_mesh_control_value(
                "parallel_degree", str(int(v))))
        parl.addWidget(self.p_parallel)
        parl.addWidget(QLabel("( Thread )", par))
        parl.addStretch(1)
        lay.addWidget(par)
        lay.addStretch(1)
        return page

    def _on_boundary_face(self) -> None:
        key = self._current_axis(self.boundary_face)
        code = {"normal": "1", "excl_symm": "2", "excl_all": "0"}[key]
        self.model.set_mesh_control_value("panel_block_face", code)

    def _investigate_edge_contact(self) -> None:
        name = self.edge_part.text().strip()
        if not name:
            self._log("Investigate: enter a part name.", "WARN")
            return
        boxes = self.model.part_boxes(name)
        if not boxes:
            self._log(f"Investigate: no elements for part '{name}' "
                      f"(run Meshing first).", "WARN")
            return
        import cab_mesh
        pairs = [pair for pair in cab_mesh.find_interferences(self.model)
                 if name in pair]
        cells = sum((b[1] - b[0] + 1) * (b[3] - b[2] + 1) * (b[5] - b[4] + 1)
                    for b in boxes)
        self._log(f"Edge-contact investigation: {name}: {len(boxes)} box "
                  f"list(s), ~{cells} element(s); interfering neighbours: "
                  f"{len(pairs)} "
                  f"{[p[1] if p[0] == name else p[0] for p in pairs]}")

    def _remove_edge_contacts(self) -> None:
        import cab_mesh
        changed = cab_mesh.resolve_interferences(self.model)
        self._after_grid_edit(
            f"Remove edge-contacts: resolved overlaps for {changed} "
            f"part(s)")

    def _mesh_single_part(self) -> None:
        name = self.mesh_part.text().strip()
        if not name:
            self._log("Meshing of specified part: enter a part name.",
                      "WARN")
            return
        axes = self.model.mesh_axes()
        if not axes or any(len(v) < 2 for v in axes.values()):
            self._log("Meshing: no mesh_block. Run Gridding first.", "WARN")
            return
        meshes = {p.name: p for p in self.cad_meshes or []}
        if name not in meshes:
            self._log(f"Meshing: no tessellated geometry for '{name}'.",
                      "WARN")
            return
        import cab_mesh
        transforms = {p.name: p.transform for p in self.model.parts()}
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
                return float(self.model.mesh_control_value(tag) or default)
            except (TypeError, ValueError):
                return default

        edge_eps = _mc("edge_eps", 0.0001)
        face_search = _mc("face_search", 1.0)
        elem_thr = _mc("element_threshold", 0.5)
        samples = ("corners" if (self.model.mesh_control_value("samples")
                                 or "").strip().lower() == "corners"
                   else "center")
        _abox, boxes = cab_mesh.classify_cells(
            axes, [meshes[name]], transforms=transforms,
            part_kinds=part_kinds, part_attrs=part_attrs,
            edge_eps=edge_eps, face_search=face_search,
            element_threshold=elem_thr, samples=samples,
            coordinate=coord)
        cab_mesh.update_part_elements(
            self.model, name, boxes.get(name, []))
        msg = f"Meshing of specified part: {name} -> " \
              f"{len(boxes.get(name, []))} box list(s)"
        if self.chk_part_edge.isChecked():
            changed = cab_mesh.resolve_interferences(self.model)
            msg += f"; edge-contacts removed for {changed} part(s)"
        if self.chk_part_interf.isChecked():
            pairs = cab_mesh.find_interferences(self.model)
            msg += f"; interferences: {len(pairs)} pair(s)"
        self._after_grid_edit(msg)

    # ------------------------------------------------------- interference

    def _reconstruct(self) -> None:
        import cab_mesh
        pairs = cab_mesh.find_interferences(self.model)
        if not pairs:
            QMessageBox.information(
                self, "List of Parts Interferences after Meshing",
                "No interfering parts.")
            self._log("Reconstruct: no interfering parts.")
            return
        text = "Interfering part pairs:\n\n" + "\n".join(
            f"  {a}  <->  {b}" for a, b in pairs)
        ret = QMessageBox.question(
            self, "List of Parts Interferences after Meshing",
            text + "\n\nReconstruct elements to remove interferences?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret == QMessageBox.Yes:
            changed = cab_mesh.resolve_interferences(self.model)
            self._after_grid_edit(
                f"Reconstruct: resolved {len(pairs)} interfering pair(s), "
                f"{changed} part(s) changed")

    # ---------------------------------------------------- load / gridding

    def _load_from_model(self) -> None:
        spec = cab_domain.domain_from_xml(self.model)
        self._dom_min = list(spec.xyz_min) if spec is not None \
            else [-100.0, -100.0, -100.0]
        self._dom_max = list(spec.xyz_max) if spec is not None \
            else [150.0, 300.0, 315.0]
        if spec is not None:
            self.basic_unit_label.setText(f"Unit : {spec.unit}")
        coord = (spec.coordinate if spec is not None else "cartesian")
        if coord not in self.domain_type_radios:
            coord = "cartesian"
        self.domain_type_radios[coord].setChecked(True)

        def _int(tag, default):
            try:
                return int(self.model.mesh_control_value(tag) or default)
            except ValueError:
                return default

        # STpre default Vertex detection = Representative (enum 1)
        det_idx = _int("select_vertex", 1)
        det_keys = [k for _l, k in self._DETECTIONS]
        self.detection_radios[
            det_keys[det_idx] if 0 <= det_idx < len(det_keys)
            else "representative"].setChecked(True)
        method_idx = _int("divide_method", 1)
        method_keys = [k for _l, k in self._METHODS]
        self.method_radios[
            method_keys[method_idx] if 0 <= method_idx < len(method_keys)
            else "rough_and_detail"].setChecked(True)
        self.subblock_factor.setValue(_int("divide_scale", 2))
        from cabxml import _first as _f1
        mc = _f1(self.model.root, "mesh_control")
        mc_block = _f1(mc, "block") if mc is not None else None
        mb = _f1(self.model.root, "mesh_block")
        limit_el = _f1(mc_block, "limit") if mc_block is not None else None
        if limit_el is None and mb is not None:
            limit_el = _f1(mb, "limit")
        if limit_el is not None and limit_el.text:
            for i, ax in enumerate("xyz"):
                try:
                    self.thr[ax].setValue(
                        float(limit_el.text.split(",")[i].strip()))
                except (ValueError, IndexError):
                    pass
        # Standard length from mesh_block/divide_length (STpre RootBlock)
        length_el = _f1(mb, "divide_length") if mb is not None else None
        if length_el is not None and length_el.text:
            for i, ax in enumerate("xyz"):
                try:
                    self.std[ax].setValue(
                        float(length_el.text.split(",")[i].strip()))
                except (ValueError, IndexError):
                    pass
        # Internal ratio: mesh_block/divide_ratio1; external: divide_ratio2
        ratio1_el = _f1(mb, "divide_ratio1") if mb is not None else None
        if ratio1_el is not None and ratio1_el.text:
            for i, ax in enumerate("xyz"):
                try:
                    self.ratio[ax].setValue(
                        float(ratio1_el.text.split(",")[i].strip()))
                except (ValueError, IndexError):
                    pass
        ratio2 = (self.model.mesh_control_value("divide_ratio2") or "").split(
            ",")
        for i, ax in enumerate("xyz"):
            if i < len(ratio2) and ratio2[i].strip():
                try:
                    self.ratio_ext[ax].setValue(float(ratio2[i].strip()))
                except ValueError:
                    pass
        edge_contact = self.model.mesh_control_value("edge_contact")
        self.chk_remove_edge_all.setChecked(edge_contact == "1")
        for tag, spin in (("edge_eps", self.p_edge_tol),
                          ("element_threshold", self.p_elem_thr),
                          ("face_search", self.p_face_search)):
            val = self.model.mesh_control_value(tag)
            if val:
                try:
                    spin.setValue(float(val))
                except ValueError:
                    pass
        pbf = self.model.mesh_control_value("panel_block_face")
        for key, code in (("normal", "1"), ("excl_symm", "2"),
                          ("excl_all", "0")):
            if pbf == code:
                self.boundary_face[key].setChecked(True)
        chk = self.model.mesh_control_value("check_scheme")
        self.chk_flux_dup.setChecked(chk == "1")
        self.chk_v8_solid.setChecked(
            self.model.mesh_control_value("solid_scheme") == "0")
        self.chk_v8_panel.setChecked(
            self.model.mesh_control_value("panel_scheme") == "0")
        self._on_method_changed()
        self._populate_parameter_tab()
        has_children = bool(self.model.mesh_blocks()
                            and self.model.mesh_blocks()[0].get("children"))
        self.chk_child_only.setEnabled(has_children)
        self.chk_lower_level.setEnabled(has_children)
        self._refresh_edit_list()
        self._refresh_detail_ranges()
        self._update_element_label()

    def _update_element_label(self) -> None:
        # STpre Element # = cell count (grid points − 1 per axis)
        axes = self.model.mesh_axes()
        if axes and all(axes.get(a) for a in "xyz"):
            nx, ny, nz = (max(0, len(axes[a]) - 1) for a in "xyz")
            self.element_label.setText(
                f"Element #   {nx * ny * nz:,} = {nx} x {ny} x {nz}")
        else:
            self.element_label.setText("Element #   1 = 1 x 1 x 1")

    def _detection_key(self) -> str:
        return self._current_axis(self.detection_radios)

    def _method_key(self) -> str:
        return self._current_axis(self.method_radios)

    def _gridding(self) -> None:
        """[Gridding]: generate mesh grids from the current parameters."""
        import cab_grid

        detection = self._detection_key()
        method = self._method_key()
        domain_coord = self._current_axis(self.domain_type_radios)
        # Persist domain type flags (generation remains cartesian AABB).
        dom = cab_domain.domain_from_xml(self.model)
        if dom is None:
            dom = cab_domain.DomainSpec(
                xyz_min=tuple(self._dom_min),
                xyz_max=tuple(self._dom_max))
        dom.coordinate = domain_coord
        cab_domain.apply_domain(self.model, dom)
        spec = cab_grid.GridSpec(
            unit="mm",
            domain_min=tuple(self._dom_min),
            domain_max=tuple(self._dom_max),
            domain_coordinate=domain_coord,
            vertex_detection=detection,
            method=method,
            standard_length=tuple(sb.value() for sb in self.std.values()),
            threshold_length=tuple(sb.value() for sb in self.thr.values()),
            geometric_ratio=tuple(sb.value() for sb in self.ratio.values()),
            geometric_ratio_external=tuple(
                sb.value() for sb in self.ratio_ext.values()),
            target_elements=int(self.target.value())
            if method == "num_elements"
            and self.num_total_radio.isChecked() else None,
            target_per_axis=tuple(self.target_axes[a].value() for a in "xyz")
            if method == "num_elements"
            and self.num_axis_radio.isChecked() else None,
            discard_existing=self.chk_discard.isChecked(),
        )
        if self.stpre_callback is not None and self.stpre_callback(
                spec, self.chk_remove_edge_all.isChecked()):
            self._update_element_label()
            self._refresh_edit_list()
            self._refresh_detail_ranges()
            self._populate_parameter_tab()
            parent = self.parent()
            if parent is not None and hasattr(
                    parent, "_enable_mesh_layer_after_gridding"):
                parent._enable_mesh_layer_after_gridding()
                if hasattr(parent, "_rebuild_scene"):
                    parent._rebuild_scene(fit=False)
            self._log("Gridding (STpre API) finished.")
            return
        import cab_vtk
        transforms = {p.name: p.transform for p in self.model.parts()}

        def _mm(pts, name):
            pts = np.asarray(pts, dtype=np.float64)
            return cab_vtk._apply_transform(
                pts, transforms.get(name, "")) * 1000.0

        part_points = {
            p.name: _mm(p.points, p.name)
            for p in self.cad_meshes
        }
        part_vertices = {
            p.name: _mm(p.rep_vertices if getattr(p, "rep_vertices", None)
                        is not None else p.vertices, p.name)
            for p in self.cad_meshes
            if getattr(p, "vertices", None) is not None
        }
        internal = self.chk_internal.isChecked()
        lo, hi = cab_domain.part_bounds(self.model, self.cad_meshes)
        part_bounds = None
        part_min = part_max = None
        if np.isfinite(lo).all() and not internal:
            part_min = tuple(float(v) * 1000.0 for v in lo)
            part_max = tuple(float(v) * 1000.0 for v in hi)
            part_bounds = (np.asarray(part_min, dtype=float),
                           np.asarray(part_max, dtype=float))
        blocks = self.model.mesh_blocks()
        entries = None
        has_children = bool(blocks and blocks[0].get("children"))
        if has_children:
            _rough, detailed, entries = cab_grid.build_axes_multiblock(
                part_points, spec, blocks,
                part_vertices=part_vertices or None,
                part_bounds=part_bounds,
                child_only=self.chk_child_only.isChecked())
        else:
            _rough, detailed = cab_grid.build_axes(
                part_points, spec, part_vertices=part_vertices or None,
                part_bounds=part_bounds)
        self.model.set_mesh(
            detailed,
            unit="mm",
            domain_min=tuple(self._dom_min),
            domain_max=tuple(self._dom_max),
            threshold=tuple(sb.value() for sb in self.thr.values()),
            ratio=tuple(sb.value() for sb in self.ratio.values()),
            standard_length=tuple(sb.value() for sb in self.std.values()),
            ratio_external=tuple(
                sb.value() for sb in self.ratio_ext.values()),
            detection=cab_grid.detection_index(spec),
            method=cab_grid.method_index(spec),
            part_min=part_min,
            part_max=part_max,
        )
        if entries:
            for ax in "xyz":
                self.model.set_mesh_axis(ax, entries[ax])
            self._update_child_grid_counts(blocks, entries)
        self.model.set_mesh_control_value(
            "divide_scale", str(self.subblock_factor.value()))
        self.model.set_mesh_control_value(
            "edge_contact",
            "1" if self.chk_remove_edge_all.isChecked() else "0")
        counts = tuple(len(v) for v in detailed.values())
        self._update_element_label()
        self._refresh_edit_list()
        self._refresh_detail_ranges()
        self._populate_parameter_tab()
        parent = self.parent()
        if parent is not None and hasattr(
                parent, "_enable_mesh_layer_after_gridding"):
            parent._enable_mesh_layer_after_gridding()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene(fit=False)
        cells = tuple(max(0, n - 1) for n in counts)
        self._log(
            f"Gridding: {detection}/{method} -> "
            f"{cells[0]}x{cells[1]}x{cells[2]} elements "
            f"({counts[0]}x{counts[1]}x{counts[2]} points)"
            + (" (internal region)" if internal else "")
            + (" (multiblock)" if has_children else "")
            + (f"; domain_type={domain_coord}"
               + (" (axes still cartesian AABB)"
                  if domain_coord != "cartesian" else "")))

    def _update_child_grid_counts(self, blocks: list[dict], entries) -> None:
        """Sync each child block's ``<grid>`` with merged axis entries."""

        def walk(blk: dict) -> None:
            if blk.get("min") and blk.get("max"):
                counts = []
                for i, ax in enumerate("xyz"):
                    lo = blk["min"][i]
                    hi = blk["max"][i]
                    n = sum(1 for v, _m in entries[ax]
                            if lo - 1e-9 <= v <= hi + 1e-9)
                    counts.append(max(2, n))
                self.model.update_child_block_grid(blk["name"], counts)
            for child in blk.get("children", []):
                walk(child)

        for blk in blocks:
            walk(blk)

    def _apply(self) -> None:
        """Backward-compatible alias for the [Gridding] button."""
        self._gridding()

    def _meshing(self) -> None:
        """[Meshing]: generate elements from the current grids."""
        parent = self.parent()
        if parent is not None and hasattr(parent, "_meshing_dialog"):
            parent._meshing_dialog()
            self._update_element_label()
        else:
            self._log("Meshing requires the CabViewer parent window.",
                      "WARN")


# ================================================================ Mesh menu
#
# The four remaining [Mesh] menu dialogs, aligned with the Pre_eng manual
# pages and the UI strings extracted from ``STpreTool_Bx64.dll``:
#   "Checking Parts Interferences"  -> InterferenceDialog
#   "Editing Mesh..."               -> EditMeshDialog
#   "Showing Element Cross-Section" -> SectionDialog
#   "Checking S-File..."            -> SFileCheckDialog


def _parts_with_elements(model: StpreModel) -> list[str]:
    return [name for name in (p.name for p in model.parts())
            if model.part_boxes(name)]


class InterferenceDialog(QDialog if _HAS_GUI_DEPS else object):
    """[Mesh] - [Checking Parts Interferences].

    [Select] picks the parts to inspect, the result list shows every
    interfering pair with its STpre status (Interference / Contact /
    Separation), [Separation only] filters out the first two states.
    [Confirm] highlights the pairs in the Draw window, [Reconstruct]
    resolves overlaps via ``cab_mesh.resolve_interferences``.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Checking Parts Interferences")
        self.model = model
        self._selected: set[str] = set()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.addWidget(DialogHeader("Parts Interferences", "mesh", self))

        sel = QHBoxLayout()
        self.btn_select = QPushButton("Select", self)
        self.btn_select.clicked.connect(self._select_parts)
        sel.addWidget(self.btn_select)
        self.sel_label = QLabel("(all parts)", self)
        sel.addWidget(self.sel_label, 1)
        lay.addLayout(sel)

        self.chk_sep_only = QCheckBox("Separation only", self)
        self.chk_sep_only.toggled.connect(lambda _o: self._refresh())
        lay.addWidget(self.chk_sep_only)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Part 1", "Part 2", "Status"])
        self.tree.setRootIsDecorated(False)
        lay.addWidget(self.tree, 1)

        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_confirm = QPushButton("Confirm", self)
        self.btn_confirm.clicked.connect(self._confirm)
        self.btn_reconstruct = QPushButton("Reconstruct", self)
        self.btn_reconstruct.clicked.connect(self._reconstruct)
        self.btn_close = QPushButton("Close", self)
        self.btn_close.clicked.connect(self.accept)
        for b in (self.btn_confirm, self.btn_reconstruct, self.btn_close):
            brow.addWidget(b)
        lay.addLayout(brow)
        self.resize(460, 360)

    def _select_parts(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Select parts")
        lay = QVBoxLayout(dlg)
        names = _parts_with_elements(self.model) or \
            [p.name for p in self.model.parts()]
        lst = QListWidget(dlg)
        lst.setSelectionMode(QListWidget.ExtendedSelection)
        for n in names:
            QListWidgetItem(n, lst)
            if n in self._selected:
                lst.item(lst.count() - 1).setSelected(True)
        lay.addWidget(lst, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK", dlg)
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("Cancel", dlg)
        cancel.clicked.connect(dlg.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if dlg.exec_():
            self._selected = {lst.item(i).text()
                              for i in range(lst.count())
                              if lst.item(i).isSelected()}
            self._refresh()

    def _refresh(self) -> None:
        import cab_mesh
        if self._selected:
            pairs = [(a, b, s) for a, b, s in
                     cab_mesh.classify_interferences(self.model)
                     if a in self._selected and b in self._selected]
        else:
            pairs = cab_mesh.classify_interferences(self.model)
        self.sel_label.setText(
            ", ".join(sorted(self._selected)) if self._selected
            else "(all parts)")
        self.tree.clear()
        if self.chk_sep_only.isChecked():
            pairs = [p for p in pairs if p[2] == "Separation"]
        for a, b, status in pairs:
            QTreeWidgetItem(self.tree, [a, b, status])
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)

    def _pairs(self) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            out.append((it.text(0), it.text(1), it.text(2)))
        return out

    def _confirm(self) -> None:
        pairs = self._pairs()
        names = sorted({n for p in pairs for n in p[:2]})
        parent = self.parent()
        if parent is not None and hasattr(parent, "_confirm_interferences"):
            parent._confirm_interferences(names)
            return
        self._log("Confirm: interfering parts: " + ", ".join(names))

    def _reconstruct(self) -> None:
        import cab_mesh
        changed = cab_mesh.resolve_interferences(self.model)
        self._log(
            f"Reconstruct: resolved overlaps for {changed} part(s)")
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()
        self._refresh()

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)


class EditMeshDialog(QDialog if _HAS_GUI_DEPS else object):
    """[Mesh] - [Editing Mesh]: fine-tune part/fluid cell assignment.

    [Active block] -> RootBlock (multiblock not supported by the cab
    viewer); a layer on the I/J/K side is selected with an index spin and
    two in-plane ranges (cab viewer substitutes combo/spin picking for the
    STpre mouse selection).  [-> Effective] adds the cells to the target
    part, [-> Ineffective] removes them.
    """

    _AXIS_LABEL = {"I": "x", "J": "y", "K": "z"}

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editing Mesh")
        self.model = model
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.addWidget(DialogHeader("Edit Mesh", "mesh", self))

        abox = QGroupBox("ActiveBlock", self)
        arow = QHBoxLayout(abox)
        arow.addWidget(QLabel("Block name", abox))
        self.block_edit = QLineEdit("RootBlock", abox)
        self.block_edit.setReadOnly(True)
        arow.addWidget(self.block_edit, 1)
        dots = QPushButton("...", abox)
        dots.setFixedWidth(28)
        dots.clicked.connect(lambda: QMessageBox.information(
            self, "Selection of mesh block",
            "RootBlock\n\n(Only the root block exists in this project.)"))
        arow.addWidget(dots)
        lay.addWidget(abox)

        side = QGroupBox("Layer selection", self)
        sl = QHBoxLayout(side)
        self.side: dict[str, QRadioButton] = {}
        for label in "IJK":
            rb = QRadioButton(f"{label} side", side)
            sl.addWidget(rb)
            self.side[label] = rb
            rb.toggled.connect(self._on_side_changed)
        sl.addWidget(QLabel("Layer", side))
        self.layer = QSpinBox(side)
        self.layer.setRange(1, 10000)
        sl.addWidget(self.layer)
        sl.addStretch(1)
        lay.addWidget(side)

        rng = QGroupBox("Range on the layer", self)
        rl = QGridLayout(rng)
        self.inplane_from: dict[str, QSpinBox] = {}
        self.inplane_to: dict[str, QSpinBox] = {}
        for i, ax in enumerate("yz"):
            rl.addWidget(QLabel(ax.upper(), rng), 0, i * 2)
            f = QSpinBox(rng)
            t = QSpinBox(rng)
            f.setRange(1, 10000)
            t.setRange(1, 10000)
            self.inplane_from[ax] = f
            self.inplane_to[ax] = t
            rl.addWidget(f, 1, i * 2)
            rl.addWidget(t, 1, i * 2 + 1)
        lay.addWidget(rng)

        tgt = QHBoxLayout()
        tgt.addWidget(QLabel("Target part", self))
        self.part_combo = QComboBox(self)
        tgt.addWidget(self.part_combo, 1)
        lay.addLayout(tgt)

        edit = QGroupBox("Edit type", self)
        el = QHBoxLayout(edit)
        self.edit_type: dict[str, QRadioButton] = {}
        for label, key in (("-> Effective", "effective"),
                           ("-> Ineffective", "ineffective")):
            rb = QRadioButton(label, edit)
            el.addWidget(rb)
            self.edit_type[key] = rb
        self.edit_type["ineffective"].setChecked(True)
        el.addStretch(1)
        lay.addWidget(edit)

        self.cells_label = QLabel(self)
        self.cells_label.setStyleSheet("color: #444;")
        lay.addWidget(self.cells_label)

        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_exec = QPushButton("Execute editing element", self)
        self.btn_exec.clicked.connect(self._execute)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        brow.addWidget(self.btn_exec)
        brow.addWidget(close)
        lay.addLayout(brow)
        self.resize(420, 430)

    def _load(self) -> None:
        axes = self.model.mesh_axes()
        self._ncells = {a: max(len(axes.get(a, [])), 1) - 1 for a in "xyz"}
        names = _parts_with_elements(self.model) or \
            [p.name for p in self.model.parts()]
        self.part_combo.addItems(names)
        self._on_side_changed()
        self._update_cells_label()

    def _on_side_changed(self) -> None:
        axis = self._AXIS_LABEL[self._current_side()]
        ni = self._ncells.get(axis, 1) if hasattr(self, "_ncells") else 1
        self.layer.setMaximum(max(ni, 1))
        self.layer.setValue(1)
        for ax in "yz":
            n = self._ncells.get(ax, 1) if hasattr(self, "_ncells") else 1
            self.inplane_from[ax].setMaximum(max(n, 1))
            self.inplane_to[ax].setMaximum(max(n, 1))
            self.inplane_to[ax].setValue(max(n, 1))
            self.inplane_from[ax].setValue(1)
        self._update_cells_label()

    def _current_side(self) -> str:
        for label in "IJK":
            if self.side[label].isChecked():
                return label
        return "I"

    def _selected_cells(self) -> list[tuple[int, int, int]]:
        axis = self._AXIS_LABEL[self._current_side()]
        idx = self.layer.value()
        ranges: dict[str, tuple[int, int]] = {}
        for ax in "xyz":
            if ax == axis:
                ranges[ax] = (idx, idx)
            else:
                ranges[ax] = (self.inplane_from[ax].value(),
                              self.inplane_to[ax].value())
        cells = []
        for i in range(ranges["x"][0], ranges["x"][1] + 1):
            for j in range(ranges["y"][0], ranges["y"][1] + 1):
                for k in range(ranges["z"][0], ranges["z"][1] + 1):
                    cells.append((i, j, k))
        return cells

    def _update_cells_label(self) -> None:
        cells = self._selected_cells()
        self.cells_label.setText(
            f"{len(cells):,} cell(s) in the selection"
            f"  (axis {self._AXIS_LABEL[self._current_side()]}, "
            f"layer {self.layer.value()})")

    def _execute(self) -> None:
        import cab_mesh
        part = self.part_combo.currentText()
        if not part:
            self._log("Editing Mesh: select a target part.", "WARN")
            return
        cells = self._selected_cells()
        effective = self.edit_type["effective"].isChecked()
        n_boxes = cab_mesh.toggle_cells_effective(
            self.model, part, cells, effective)
        self._log(
            f"Edit Mesh: {len(cells):,} cell(s) "
            f"{'-> Effective' if effective else '-> Ineffective'} "
            f"on part '{part}' -> {n_boxes} box list(s)")
        parent = self.parent()
        if parent is not None and hasattr(parent, "_rebuild_scene"):
            parent._rebuild_scene()

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)


class SectionDialog(QDialog if _HAS_GUI_DEPS else object):
    """[Mesh] - [Showing Element Cross-Section].

    Slice of the element mesh at a given element address along the chosen
    axis; [Display type] picks element/face address, [Show/Hide of fluid
    element] controls whether fluid cells are drawn.  The slice refreshes
    live in the Draw window through the parent ``_show_section`` hook.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show Element Cross-Section")
        self.model = model
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.addWidget(DialogHeader("Element Cross-Section", "mesh", self))

        abox = QGroupBox("ActiveBlock", self)
        arow = QHBoxLayout(abox)
        arow.addWidget(QLabel("Block name", abox))
        self.block_edit = QLineEdit("RootBlock", abox)
        self.block_edit.setReadOnly(True)
        arow.addWidget(self.block_edit, 1)
        dots = QPushButton("...", abox)
        dots.setFixedWidth(28)
        dots.clicked.connect(lambda: QMessageBox.information(
            self, "Selection of Active mesh block",
            "RootBlock\n\n(Only the root block exists in this project.)"))
        arow.addWidget(dots)
        lay.addWidget(abox)

        loc = QGroupBox("Location", self)
        ll = QVBoxLayout(loc)
        arow = QHBoxLayout()
        arow.addWidget(QLabel("Axis", loc))
        self.axis: dict[str, QRadioButton] = {}
        for ax in "XYZ":
            rb = QRadioButton(ax, loc)
            arow.addWidget(rb)
            self.axis[ax.lower()] = rb
            rb.toggled.connect(self._on_axis_changed)
        arow.addStretch(1)
        ll.addLayout(arow)

        dt = QHBoxLayout()
        self.disp_type: dict[str, QRadioButton] = {}
        for label, key in (("Element address", "element"),
                           ("Face address", "face")):
            rb = QRadioButton(label, loc)
            ll.addWidget(rb)
            self.disp_type[key] = rb
        self.disp_type["element"].setChecked(True)
        dt.addStretch(1)
        ll.addLayout(dt)

        sl = QHBoxLayout()
        sl.addWidget(QLabel("Element address", loc))
        self.slider = QSlider(Qt.Horizontal, loc)
        self.slider.setRange(1, 2)
        sl.addWidget(self.slider, 1)
        self.slider_value = QLabel("1", loc)
        self.slider_value.setMinimumWidth(40)
        sl.addWidget(self.slider_value)
        ll.addLayout(sl)

        self.chk_all = QCheckBox("All blocks", loc)
        self.chk_all.setChecked(True)
        ll.addWidget(self.chk_all)
        lay.addWidget(loc)

        sh = QGroupBox("Show/Hide of fluid element", self)
        shl = QHBoxLayout(sh)
        self.mode: dict[str, QRadioButton] = {}
        for label, key in (("Show", "show"), ("Hide", "hide"),
                           ("Show only fluid", "fluid_only")):
            rb = QRadioButton(label, sh)
            shl.addWidget(rb)
            self.mode[key] = rb
        self.mode["show"].setChecked(True)
        shl.addStretch(1)
        lay.addWidget(sh)

        note = QLabel("The section refreshes in the Draw window while the "
                      "slider is dragged.", self)
        note.setStyleSheet("color: #555; font-size: 11px;")
        lay.addWidget(note)

        brow = QHBoxLayout()
        brow.addStretch(1)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        brow.addWidget(close)
        lay.addLayout(brow)
        self.resize(400, 380)

        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderReleased.connect(self._render)
        for key in ("show", "hide", "fluid_only"):
            self.mode[key].toggled.connect(self._render)

    def _load(self) -> None:
        axes = self.model.mesh_axes()
        self._ncells = {a: max(len(axes.get(a, [])), 1) - 1 for a in "xyz"}
        self._on_axis_changed()

    def _current_axis(self) -> str:
        for ax in "xyz":
            if self.axis[ax].isChecked():
                return ax
        return "x"

    def _current_mode(self) -> str:
        for key, rb in self.mode.items():
            if rb.isChecked():
                return key
        return "show"

    def _on_axis_changed(self) -> None:
        ax = self._current_axis()
        n = self._ncells.get(ax, 1)
        self.slider.blockSignals(True)
        self.slider.setRange(1, max(n, 1))
        self.slider.setValue(1)
        self.slider.blockSignals(False)
        self._render()

    def _on_slider(self, value: int) -> None:
        self.slider_value.setText(str(value))

    def _render(self) -> None:
        import cab_vtk
        ax = self._current_axis()
        idx = self.slider.value()
        pd, colors = cab_vtk.element_section_polydata(
            self.model, ax, idx, self._current_mode())
        parent = self.parent()
        if parent is not None and hasattr(parent, "_show_section"):
            parent._show_section(pd, colors)


class SFileCheckDialog(QDialog if _HAS_GUI_DEPS else object):
    """[Mesh] - [Checking S-File].

    [Open] loads an existing S file and lists its parts / panels / condition
    setting regions; when a listed name matches a model part, its checkbox
    toggles that part's visibility in the Draw window (STpre behaviour).
    Without an external file the current project's parts and condition
    regions are shown.
    """

    def __init__(self, model: StpreModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Checking S File")
        self.model = model
        self._loaded_names: list[str] = []
        self._build_ui()
        self._refresh_tree(open_file=False)

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.addWidget(DialogHeader("Check S File", "mesh", self))

        row = QHBoxLayout()
        self.btn_open = QPushButton("Open", self)
        self.btn_open.clicked.connect(self._open)
        row.addWidget(self.btn_open)
        self.file_label = QLabel("(current project)", self)
        self.file_label.setStyleSheet("color: #555;")
        row.addWidget(self.file_label, 1)
        lay.addLayout(row)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Item", "Type"])
        self.tree.setRootIsDecorated(False)
        self.tree.itemChanged.connect(self._on_toggled)
        lay.addWidget(self.tree, 1)

        self.diag = QTextEdit(self)
        self.diag.setReadOnly(True)
        self.diag.setFixedHeight(96)
        self.diag.setStyleSheet("color:#333;")
        lay.addWidget(self.diag)

        brow = QHBoxLayout()
        brow.addStretch(1)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        brow.addWidget(close)
        lay.addLayout(brow)
        self.resize(380, 420)

    def _open(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open S File", "", "S File (*.s);;All files (*)")
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8-sig").read()
        except OSError as exc:
            self._log(f"Checking S-File: cannot read {path}: {exc}", "ERROR")
            return
        import s_export
        self._loaded_names = s_export.parse_s_parts(text)
        self.file_label.setText(path)
        self._refresh_tree(open_file=True)
        self._log(f"Checking S-File: {path} -> {len(self._loaded_names)} "
                  f"part/region name(s)")
        try:
            diags = s_export.validate_sfile(text)
            lines = [f"[{lv}] {msg}" for lv, msg in diags]
            self.diag.setPlainText("\n".join(lines))
            for lv, msg in diags:
                self._log(f"S-File {lv}: {msg}", lv)
        except Exception as exc:
            self.diag.setPlainText(f"validation failed: {exc}")

    def _refresh_tree(self, open_file: bool) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        if open_file:
            for name in self._loaded_names:
                kind = ("part" if self.model.find_part(name) is not None
                        else "condition region")
                it = QTreeWidgetItem(self.tree, [name, kind])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked)
                it.setData(0, Qt.UserRole, kind)
        else:
            for p in self.model.parts():
                it = QTreeWidgetItem(self.tree, [p.name, "part"])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked)
                it.setData(0, Qt.UserRole, "part")
            seen = set()
            for c in self.model.conditions():
                target = None
                for ch in c:
                    if ch.tag == "region":
                        target = ch.text.strip()
                        break
                if target and target not in seen and \
                        not target.startswith("undefine"):
                    seen.add(target)
                    it = QTreeWidgetItem(self.tree, [target,
                                                     "condition region"])
                    it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.Checked)
                    it.setData(0, Qt.UserRole, "region")
        self.tree.resizeColumnToContents(0)
        self.tree.blockSignals(False)

    def _on_toggled(self, item, _col) -> None:
        name = item.text(0)
        visible = item.checkState(0) == Qt.Checked
        kind = item.data(0, Qt.UserRole)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_set_part_visible"):
            parent._set_part_visible(name, visible)
        elif parent is not None and hasattr(parent, "log"):
            parent.log(f"S-File check: {kind} '{name}' "
                       f"{'shown' if visible else 'hidden'}")

    def _log(self, msg: str, level: str = "INFO") -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "log"):
            parent.log(msg, level)

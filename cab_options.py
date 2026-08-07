"""M7: Option menu dialogs (Environment Settings / Detailed Program Settings).

Aligned with the Pre_eng pages (Basic Setting / Parts / Mesh / Message
Window / User Interface); settings persist through QSettings and are applied
live by :class:`cab_gui.CabViewer._apply_options`.
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
)

_ORG = "cabdecoding"
_APP = "options"
_MEM: dict = {}


def get_setting(key: str, default=None):
    if key in _MEM:
        return _MEM[key]
    try:
        return QSettings(_ORG, _APP).value(key, default)
    except Exception:
        return default


def set_setting(key: str, value) -> None:
    _MEM[key] = value
    try:
        QSettings(_ORG, _APP).setValue(key, value)
    except Exception:
        pass


class OptionsDialog(QDialog):
    """Environment Settings / Detailed Program Settings (subset)."""

    def __init__(self, parent=None, props=None, detailed: bool = False):
        super().__init__(parent)
        self.props = props
        self.setWindowTitle(
            "Detailed Program Settings" if detailed
            else "Environment Settings")
        self.resize(520, 460)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._basic_tab(), "Basic Setting")
        self.tabs.addTab(self._parts_tab(), "Parts")
        self.tabs.addTab(self._mesh_tab(), "Mesh")
        self.tabs.addTab(self._message_tab(), "Message Window")
        self.tabs.addTab(self._ui_tab(), "User Interface")
        lay.addWidget(self.tabs)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("OK", self)
        ok.setDefault(True)
        ok.clicked.connect(self._save_and_accept)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        lay.addLayout(brow)

    # -- tabs -------------------------------------------------------------

    def _basic_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.user_name = QLineEdit(str(get_setting("user_name", "")), w)
        f.addRow("User name", self.user_name)
        self.undo_levels = QSpinBox(w)
        self.undo_levels.setRange(1, 200)
        self.undo_levels.setValue(int(get_setting("undo_levels", 50)))
        f.addRow("Number of undo levels", self.undo_levels)
        self.autosave = QSpinBox(w)
        self.autosave.setRange(0, 600)
        self.autosave.setSuffix(" min")
        self.autosave.setValue(int(get_setting("autosave_min", 0)))
        f.addRow("Auto save interval of CAB file", self.autosave)
        self.display_unit = QComboBox(w)
        self.display_unit.addItems(["mm", "m", "cm"])
        self.display_unit.setCurrentText(
            str(get_setting("display_unit", "mm")))
        f.addRow("Display unit of a model (length)", self.display_unit)
        self.internal_unit = QComboBox(w)
        self.internal_unit.addItems(["mm", "m", "cm"])
        self.internal_unit.setCurrentText(
            str(get_setting("internal_unit", "mm")))
        f.addRow("Internal unit of a model (length)", self.internal_unit)
        self.background = QComboBox(w)
        self.background.addItems(["Gradation", "Black", "White"])
        self.background.setCurrentText(
            str(get_setting("background", "Gradation")))
        f.addRow("Background color", self.background)
        self.sig_figs = QSpinBox(w)
        self.sig_figs.setRange(3, 17)
        self.sig_figs.setValue(int(get_setting("sig_figs", 12)))
        f.addRow("Number of significant figures for display", self.sig_figs)
        return w

    def _parts_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.default_attribute = QComboBox(w)
        self.default_attribute.addItems(
            ["Solid", "Obstacle", "Fluid", "Condition region", "Panel"])
        self.default_attribute.setCurrentText(
            str(get_setting("default_attribute", "Solid")))
        f.addRow("Default attribute", self.default_attribute)
        self.default_material = QComboBox(w)
        self.default_material.setEditable(True)
        if self.props is not None:
            self.default_material.addItems(self.props.material_names())
        self.default_material.setCurrentText(
            str(get_setting("default_material",
                            self.default_material.itemText(0) or "")))
        f.addRow("Default material", self.default_material)
        return w

    def _mesh_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.facet_tol = QDoubleSpinBox(w)
        self.facet_tol.setRange(1e-12, 1.0)
        self.facet_tol.setDecimals(10)
        self.facet_tol.setValue(float(get_setting("facet_tol", 1e-4)))
        f.addRow("Surface facet tolerance", self.facet_tol)
        self.facet_angle = QDoubleSpinBox(w)
        self.facet_angle.setRange(0.5, 45.0)
        self.facet_angle.setDecimals(2)
        self.facet_angle.setValue(float(get_setting("facet_angle", 12.0)))
        f.addRow("Surface facet angle (deg)", self.facet_angle)
        return w

    def _message_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.font_name = QLineEdit(
            str(get_setting("message_font", "Consolas")), w)
        f.addRow("Font name", self.font_name)
        self.log_level = QComboBox(w)
        self.log_level.addItems(["INFO", "WARN", "ERROR"])
        self.log_level.setCurrentText(str(get_setting("log_level", "INFO")))
        f.addRow("Log level", self.log_level)
        self.max_blocks = QSpinBox(w)
        self.max_blocks.setRange(100, 20000)
        self.max_blocks.setValue(int(get_setting("message_max_blocks", 2000)))
        f.addRow("Maximum message blocks", self.max_blocks)
        return w

    def _ui_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.drawing_mode = QComboBox(w)
        self.drawing_mode.addItems(["Shading", "Line", "Translucent"])
        self.drawing_mode.setCurrentText(
            str(get_setting("drawing_mode", "Shading")))
        f.addRow("Default drawing mode", self.drawing_mode)
        self.show_status = QCheckBox("Show status bar", w)
        self.show_status.setChecked(
            str(get_setting("show_status_bar", "True")) == "True")
        f.addRow(self.show_status)
        return w

    # -- values -----------------------------------------------------------

    def values(self) -> dict:
        return {
            "user_name": self.user_name.text(),
            "undo_levels": self.undo_levels.value(),
            "autosave_min": self.autosave.value(),
            "display_unit": self.display_unit.currentText(),
            "internal_unit": self.internal_unit.currentText(),
            "background": self.background.currentText(),
            "sig_figs": self.sig_figs.value(),
            "default_attribute": self.default_attribute.currentText(),
            "default_material": self.default_material.currentText(),
            "facet_tol": self.facet_tol.value(),
            "facet_angle": self.facet_angle.value(),
            "message_font": self.font_name.text(),
            "log_level": self.log_level.currentText(),
            "message_max_blocks": self.max_blocks.value(),
            "drawing_mode": self.drawing_mode.currentText(),
            "show_status_bar": self.show_status.isChecked(),
        }

    def _save_and_accept(self) -> None:
        for key, value in self.values().items():
            set_setting(key, value)
        self.accept()

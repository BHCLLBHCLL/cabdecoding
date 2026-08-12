"""M7/M29/M32: Option menu dialogs (Environment / Detailed Program Settings).

Aligned with Pre_eng Environment Setting pages (≈13). Settings persist through
QSettings and are applied live by :class:`cab_gui.CabViewer._apply_options`.

**Frozen:** Mesh tab ``use_stpre_api`` semantics must not change (STpre API
Gridding/Meshing path).
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
)

try:  # strip insignificant trailing zeros on coordinate spin boxes
    from cab_widgets import CoordSpinBox
    QDoubleSpinBox = CoordSpinBox
except Exception:
    pass

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
    """Environment Settings / Detailed Program Settings (STpre page set)."""

    def __init__(self, parent=None, props=None, detailed: bool = False):
        super().__init__(parent)
        self.props = props
        self.detailed = detailed
        self.setWindowTitle(
            "Detailed Program Settings" if detailed
            else "Environment Settings")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        # Pre_eng Environment Setting page order (subset labels)
        self.tabs.addTab(self._basic_tab(), "Basic Setting")
        self.tabs.addTab(self._parts_tab(), "Parts")
        self.tabs.addTab(self._mesh_tab(), "Mesh")
        self.tabs.addTab(self._folder_tab(), "Folder")
        self.tabs.addTab(self._file_tab(), "File")
        self.tabs.addTab(self._io_tab(), "Input/Output")
        self.tabs.addTab(self._unit_tab(), "Units")
        self.tabs.addTab(self._color_part_tab(), "Color (Part)")
        self.tabs.addTab(self._color_mesh_tab(), "Color (Mesh)")
        self.tabs.addTab(self._color_other_tab(), "Color (Others)")
        self.tabs.addTab(self._message_tab(), "Message Window")
        self.tabs.addTab(self._parametric_tab(), "Parametric Study")
        self.tabs.addTab(self._ui_tab(), "User Interface")
        # Extra pages (Detailed Program Settings + Environment both expose)
        self.tabs.addTab(self._mouse_tab(), "Mouse")
        self.tabs.addTab(self._tree_tab(), "Tree/List View")
        self.tabs.addTab(self._shortcut_tab(), "Shortcut")
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
        # Frozen: STpre API Gridding/Meshing toggle — do not rename/repurpose
        self.use_stpre_api = QCheckBox(
            "Use STpre API for Gridding/Meshing (external automation)", w)
        self.use_stpre_api.setChecked(
            str(get_setting("use_stpre_api", "False")) == "True")
        f.addRow(self.use_stpre_api)
        return w

    def _folder_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.work_folder = QLineEdit(
            str(get_setting("work_folder", "")), w)
        self.lib_folder = QLineEdit(
            str(get_setting("lib_folder", "")), w)
        self.temp_folder = QLineEdit(
            str(get_setting("temp_folder", "")), w)
        f.addRow("Work folder", self.work_folder)
        f.addRow("Library folder", self.lib_folder)
        f.addRow("Temporary folder", self.temp_folder)
        return w

    def _file_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.default_cab_ext = QComboBox(w)
        self.default_cab_ext.addItems([".cab", ".CAB"])
        self.default_cab_ext.setCurrentText(
            str(get_setting("default_cab_ext", ".cab")))
        f.addRow("Default CAB extension", self.default_cab_ext)
        self.autosave_name = QLineEdit(
            str(get_setting("autosave_name", "autosave.cab")), w)
        f.addRow("Auto-save file name", self.autosave_name)
        return w

    def _io_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.mesh_info_txt = QCheckBox(
            "Output messages of meshing to mesh_info.txt", w)
        self.mesh_info_txt.setChecked(
            str(get_setting("mesh_info_txt", "False")) == "True")
        self.s_info_txt = QCheckBox(
            "Output messages of S file output to s_info.txt", w)
        self.s_info_txt.setChecked(
            str(get_setting("s_info_txt", "False")) == "True")
        f.addRow(self.mesh_info_txt)
        f.addRow(self.s_info_txt)
        return w

    def _color_part_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.part_color = QLineEdit(
            str(get_setting("default_part_color", "180,180,180,255")), w)
        f.addRow("Default part color (RGBA)", self.part_color)
        return w

    def _color_mesh_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.mesh_line_color = QLineEdit(
            str(get_setting("mesh_line_color", "30,30,36,255")), w)
        f.addRow("Element division line color (RGBA)", self.mesh_line_color)
        return w

    def _color_other_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.domain_color = QLineEdit(
            str(get_setting("default_domain_color", "0,255,255,255")), w)
        f.addRow("Default domain color (RGBA)", self.domain_color)
        return w

    # Compat alias used by older tests / callers
    _color_tab = _color_part_tab

    def _unit_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.temp_unit = QComboBox(w)
        self.temp_unit.addItems(["C", "K", "F"])
        self.temp_unit.setCurrentText(str(get_setting("temp_unit", "C")))
        self.press_unit = QComboBox(w)
        self.press_unit.addItems(["Pa", "atm", "bar"])
        self.press_unit.setCurrentText(str(get_setting("press_unit", "Pa")))
        self.ui_language = QComboBox(w)
        self.ui_language.addItems(["English", "中文"])
        self.ui_language.setCurrentText(
            "中文" if str(get_setting("ui_language", "en")) == "zh"
            else "English")
        f.addRow("Temperature unit", self.temp_unit)
        f.addRow("Pressure unit", self.press_unit)
        f.addRow("UI language", self.ui_language)
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

    def _parametric_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.param_enable = QCheckBox("Enable parametric study UI", w)
        self.param_enable.setChecked(
            str(get_setting("parametric_study", "False")) == "True")
        f.addRow(self.param_enable)
        note = QLabel(
            "Parametric cases are registered in the model; solver matrix "
            "execution is separate.", w)
        note.setWordWrap(True)
        f.addRow(note)
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
        self.enable_thermal_parts = QCheckBox(
            "Enable thermal design part (toolbar/menu)", w)
        self.enable_thermal_parts.setChecked(
            str(get_setting("enable_thermal_parts", "True")) == "True")
        f.addRow(self.enable_thermal_parts)
        self.add_view_dialogs = QCheckBox(
            "Add List of Part / Edit Part Face / Contact TR to View menu", w)
        self.add_view_dialogs.setChecked(
            str(get_setting("add_view_dialogs", "True")) == "True")
        f.addRow(self.add_view_dialogs)
        self.auto_sketch = QCheckBox(
            "Automatic sketch mode at selection of part", w)
        self.auto_sketch.setChecked(
            str(get_setting("auto_sketch_mode", "False")) == "True")
        f.addRow(self.auto_sketch)
        self.english_names = QCheckBox(
            "Set the default name of a part/region/condition in English", w)
        self.english_names.setChecked(
            str(get_setting("english_default_names", "True")) == "True")
        f.addRow(self.english_names)
        return w

    def _mouse_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.mouse_mode = QComboBox(w)
        self.mouse_mode.addItems(["Trackball", "Rubber Band Zoom"])
        cur = str(get_setting("mouse_mode", "Trackball"))
        self.mouse_mode.setCurrentText(
            cur if cur in ("Trackball", "Rubber Band Zoom") else "Trackball")
        f.addRow("Default mouse mode", self.mouse_mode)
        self.wheel_zoom = QCheckBox("Enable mouse-wheel zoom", w)
        self.wheel_zoom.setChecked(
            str(get_setting("wheel_zoom", "True")) == "True")
        f.addRow(self.wheel_zoom)
        return w

    def _tree_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        self.tree_expand = QComboBox(w)
        self.tree_expand.addItems(["Expanded", "Collapsed"])
        self.tree_expand.setCurrentText(
            str(get_setting("tree_expand_default", "Expanded")))
        f.addRow("Default tree expand state", self.tree_expand)
        self.show_groups = QCheckBox("Show groups in Tree/List View", w)
        self.show_groups.setChecked(
            str(get_setting("tree_show_groups", "True")) == "True")
        f.addRow(self.show_groups)
        return w

    def _shortcut_tab(self):
        from PyQt5.QtWidgets import QWidget
        w = QWidget(self)
        f = QFormLayout(w)
        note = QLabel(
            "Draw Window: X/Y/Z plane views, Shift+X/Y/Z opposite, "
            "F Fit (when Draw focused). Menu: Ctrl+N/O/S/E, Ctrl+Z/Y Undo.",
            w)
        note.setWordWrap(True)
        f.addRow(note)
        self.fit_key = QLineEdit(str(get_setting("shortcut_fit", "F")), w)
        self.fit_key.setMaxLength(1)
        f.addRow("Fit key (Draw Window)", self.fit_key)
        return w

    # -- values -----------------------------------------------------------

    def values(self) -> dict:
        out = {
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
            "use_stpre_api": self.use_stpre_api.isChecked(),
            "work_folder": self.work_folder.text(),
            "lib_folder": self.lib_folder.text(),
            "temp_folder": self.temp_folder.text(),
            "default_cab_ext": self.default_cab_ext.currentText(),
            "autosave_name": self.autosave_name.text(),
            "mesh_info_txt": self.mesh_info_txt.isChecked(),
            "s_info_txt": self.s_info_txt.isChecked(),
            "default_part_color": self.part_color.text(),
            "mesh_line_color": self.mesh_line_color.text(),
            "default_domain_color": self.domain_color.text(),
            "temp_unit": self.temp_unit.currentText(),
            "press_unit": self.press_unit.currentText(),
            "ui_language": ("zh" if self.ui_language.currentText() == "中文"
                            else "en"),
            "message_font": self.font_name.text(),
            "log_level": self.log_level.currentText(),
            "message_max_blocks": self.max_blocks.value(),
            "parametric_study": self.param_enable.isChecked(),
            "drawing_mode": self.drawing_mode.currentText(),
            "show_status_bar": self.show_status.isChecked(),
            "enable_thermal_parts": self.enable_thermal_parts.isChecked(),
            "add_view_dialogs": self.add_view_dialogs.isChecked(),
            "auto_sketch_mode": self.auto_sketch.isChecked(),
            "english_default_names": self.english_names.isChecked(),
            "mouse_mode": self.mouse_mode.currentText(),
            "wheel_zoom": self.wheel_zoom.isChecked(),
            "tree_expand_default": self.tree_expand.currentText(),
            "tree_show_groups": self.show_groups.isChecked(),
            "shortcut_fit": self.fit_key.text() or "F",
        }
        return out

    def _save_and_accept(self) -> None:
        for key, value in self.values().items():
            set_setting(key, value)
        self.accept()

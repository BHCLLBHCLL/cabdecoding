"""§25 F3 batch: the seven non-Condition dialogs (Chemical Material,
Compressible Fluid, Cloth Model, Check Time Step, the two thermal
calculators and the humidity phi-h calculator)."""
from __future__ import annotations

import pytest

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


@pytest.fixture(scope="module")
def qapp():
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys as _sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([_sys.argv[0]])
    yield app


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def test_chemical_material_roundtrip(qapp):
    import cab_extra_dialogs as x
    m = _model()
    dlg = x.ChemicalMaterialDialog(m)
    try:
        dlg.sp_name.setText("CO2")
        dlg.sp_kind.setCurrentText("viscosity")
        dlg.sp_coeffs.setText("1.45e-6,0.5,273")
        dlg._add_row()
        dlg.sp_name.setText("CO2")
        dlg.sp_kind.setCurrentText("thermal_conductivity")
        dlg.sp_coeffs.setText("0.014,0.7,273")
        dlg._add_row()
        dlg.apply_settings()
        assert m.analysis_set_value("chemical_material").startswith(
            "CO2|viscosity|1.45e-6,0.5,273;")
        # reload restores both rows
        dlg2 = x.ChemicalMaterialDialog(m)
        try:
            assert dlg2.table.rowCount() == 2
        finally:
            dlg2.deleteLater()
        # delete selected removes a row
        dlg.table.selectRow(0)
        dlg._delete_selected()
        assert dlg.table.rowCount() == 1
    finally:
        dlg.deleteLater()


def test_compressible_fluid_roundtrip(qapp):
    import cab_extra_dialogs as x
    m = _model()
    dlg = x.CompressibleFluidDialog(m)
    try:
        dlg.mode.setCurrentText("Script")
        dlg.script.setText("visc_fn")
        dlg.apply_settings()
        assert m.analysis_set_value("compressible_mode") == "script"
        assert m.analysis_set_value("compressible_script") == "visc_fn"
        dlg2 = x.CompressibleFluidDialog(m)
        try:
            assert dlg2.mode.currentText() == "Script"
            assert dlg2.script.text() == "visc_fn"
        finally:
            dlg2.deleteLater()
    finally:
        dlg.deleteLater()


def test_cloth_model_roundtrip(qapp):
    import cab_extra_dialogs as x
    m = _model()
    dlg = x.ClothModelDialog(m)
    try:
        dlg.calc_model.setCurrentText("Rheology model")
        dlg.stretch_k.setValue(12.5)
        dlg.apply_settings()
        assert m.analysis_set_value("cloth_model") == "rheology"
        assert m.analysis_set_value("cloth_stretch_k") == "12.5"
        dlg2 = x.ClothModelDialog(m)
        try:
            assert dlg2.calc_model.currentText() == "Rheology model"
            assert dlg2.stretch_k.value() == 12.5
        finally:
            dlg2.deleteLater()
    finally:
        dlg.deleteLater()


def test_check_time_step_rows(qapp):
    import cab_extra_dialogs as x
    m = _model()
    m.set_analysis_set_value("calculation", "transient")
    m.set_analysis_set_value("cycle", "1:300")
    m.set_analysis_set_value("init_time_step", "0.0001")
    dlg = x.CheckTimeStepDialog(m)
    try:
        rows = x.CheckTimeStepDialog.build_rows(m)
        assert rows[0][0] == "Transient"
        assert rows[0][1] == "1" and rows[0][2] == "300"
        assert "0.0001" in rows[0][3]
        assert dlg.table.rowCount() == 1
    finally:
        dlg.deleteLater()


def test_conductivity_calculator(qapp):
    import cab_extra_dialogs as x
    dlg = x.CalculateConductivityDialog()
    try:
        dlg.heat_trans.setValue(2.0)
        dlg.h1.setValue(10.0)
        dlg.h2.setValue(10.0)
        dlg.thickness.setValue(0.05)
        dlg.calculate()
        # 1/U = 0.5; 1/h1 + 1/h2 = 0.2 -> denom 0.3 -> 0.05/0.3
        assert abs(float(dlg.result.text()) - 0.05 / 0.3) < 1e-6
        # non-physical (U larger than the h-limited transmission) -> blank
        dlg.heat_trans.setValue(100.0)
        dlg.calculate()
        assert dlg.result.text() == ""
    finally:
        dlg.deleteLater()


def test_htc_calculator(qapp):
    import cab_extra_dialogs as x
    dlg = x.HeatTransferCoefficientDialog()
    try:
        dlg.mat_name.setText("epoxy")
        dlg.conductivity.setValue(0.2)
        dlg.thickness.setValue(0.001)
        dlg.calculate()
        assert abs(float(dlg.result.text()) - 200.0) < 1e-9
    finally:
        dlg.deleteLater()


def test_humidity_phih_persist(qapp):
    import cab_extra_dialogs as x
    m = _model()
    dlg = x.HumidityAbsorptionDialog(m)
    try:
        vals = (0.0, 0.1, -0.02, 0.003, -0.0001)
        for sb, v in zip(dlg.coeffs, vals):
            sb.setValue(v)
        dlg.apply_settings()
        assert m.analysis_set_value("humidity_phih_coeffs") == \
            "0,0.1,-0.02,0.003,-0.0001"
        dlg2 = x.HumidityAbsorptionDialog(m)
        try:
            assert [sb.value() for sb in dlg2.coeffs] == \
                list(vals)
        finally:
            dlg2.deleteLater()
    finally:
        dlg.deleteLater()

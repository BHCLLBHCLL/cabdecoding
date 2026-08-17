"""W2: CW edge pages write analysis_etc; scFLOW-only types stay disabled."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cabxml import StpreModel, new_stpre_bytes, parse_stpre
from cab_wizards import _CwAnalysisTypesPage


def test_cosim_bci_rom_always_disabled():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert "msc_cosim" in _CwAnalysisTypesPage._ALWAYS_DISABLED
    assert "bci_rom" in _CwAnalysisTypesPage._ALWAYS_DISABLED
    m = StpreModel(parse_stpre(new_stpre_bytes("cw")))
    page = _CwAnalysisTypesPage(m)
    for key in ("msc_cosim", "bci_rom"):
        w = page.types[key]
        assert not w.isEnabled()
        assert not w.isChecked()
    page.apply()
    assert (m.analysis_set_value("msc_cosim", "") or "0") in ("", "0", "F")
    assert (m.analysis_set_value("bci_rom", "") or "0") in ("", "0", "F")
    _ = app


def test_lamp_and_fusion_analysis_etc_roundtrip():
    from PyQt5.QtWidgets import QApplication
    from cab_cwizard_pages import _CwLampPage, _CwFusionPage
    app = QApplication.instance() or QApplication([])
    m = StpreModel(parse_stpre(new_stpre_bytes("cw2")))
    lamp = _CwLampPage(m)
    lamp.enable.setChecked(True)
    lamp.model_type.setCurrentText("Line source")
    lamp.flux.setValue(1200.0)
    lamp.apply()
    assert m.analysis_etc_section("artificial_light") is not None
    assert m.analysis_etc_child("artificial_light", "lamp_model") == "Line source"
    assert float(m.analysis_etc_child("artificial_light", "lamp_flux")) == 1200.0

    fusion = _CwFusionPage(m)
    fusion.enable.setChecked(True)
    fusion.solidus.setValue(10.0)
    fusion.liquidus.setValue(20.0)
    fusion.latent.setValue(330000.0)
    fusion.apply()
    assert m.analysis_etc_child("fusion", "solidus") == "10"
    again = StpreModel(parse_stpre(m.doc.serialize()))
    lamp2 = _CwLampPage(again)
    assert lamp2.enable.isChecked()
    assert lamp2.model_type.currentText() == "Line source"
    fusion2 = _CwFusionPage(again)
    assert fusion2.enable.isChecked()
    assert fusion2.solidus.value() == 10.0
    _ = app

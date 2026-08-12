"""M36: Condition Wizard Source page write-back."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cabxml import StpreModel, _first, new_stpre_bytes, parse_stpre


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _model() -> StpreModel:
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(base=(0, 0, 0), size=(100, 100, 100), material="air")
    m.ensure_domain_faces()
    return m


def test_vol_heat_source_writeback(qapp):
    from cab_cwizard_pages import _CwSourcePage
    m = _model()
    page = _CwSourcePage(m)
    # Bypass dialog: call upsert + bind like New Volumetric heat
    m.upsert_value("heat_source", "HeatSource1", [
        ("source", "12.5", "W"),
        ("heat", "12.5", "W"),
        ("kind", "volumetric", None),
    ])
    m.bind_condition("analysis", m.domain_name() or "Domain(cuboid)",
                     "HeatSource1")
    page.refresh()
    page.apply()
    val = m.find_value("HeatSource1")
    assert val is not None
    assert val.attrib.get("type") == "heat_source"
    assert float((_first(val, "source").text or "").strip()) == 12.5
    assert (_first(val, "source").attrib.get("unit") or "") == "W"
    assert m.analysis_set_value("source_heat") == "T"
    assert m.analysis_set_value("heat") == "1"
    # Binding survives serialize round-trip
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.find_value("HeatSource1") is not None
    assert again.condition_value("analysis", again.domain_name()
                                 or "Domain(cuboid)") is not None \
        or any(
            (_first(c, "value").text or "").strip() == "HeatSource1"
            for c in again.conditions()
            if _first(c, "value") is not None)


def test_vol_force_and_area_heat_writeback(qapp):
    from cab_cwizard_pages import _CwSourcePage
    m = _model()
    page = _CwSourcePage(m)
    m.upsert_value("volumetric_force", "VolForce1", [
        ("force", "0,0,-9.8", "N/m3"),
        ("fx", "0", "N/m3"), ("fy", "0", "N/m3"), ("fz", "-9.8", "N/m3"),
    ])
    m.bind_condition("analysis", m.domain_name() or "Domain(cuboid)",
                     "VolForce1")
    m.upsert_value("area_heat_source", "AreaHeat1", [
        ("source", "5", "W/m2"),
        ("heat", "5", "W/m2"),
        ("kind", "area", None),
    ])
    m.bind_condition("region", "Xmin", "AreaHeat1")
    page.refresh()
    page.apply()
    assert m.analysis_set_value("source_volumetric") == "T"
    assert m.analysis_set_value("source_heat") == "T"
    force = m.find_value("VolForce1")
    assert (_first(force, "force").text or "").strip() == "0,0,-9.8"
    area = m.find_value("AreaHeat1")
    assert (_first(area, "source").attrib.get("unit") or "") == "W/m2"


def test_unsupported_analysis_types_disabled(qapp):
    from cab_wizards import _CwAnalysisTypesPage
    m = _model()
    page = _CwAnalysisTypesPage(m)
    assert not page.types["diffusion"].isEnabled()
    assert "not supported" in (page.types["diffusion"].toolTip() or "").lower()
    # Core product types stay enabled
    assert page.types["heat"].isEnabled()
    assert page.types["humidity"].isEnabled()
    assert page.types["porous_media"].isEnabled()


def test_source_writeback_s_export_consistency(qapp):
    """P4: wizard Source write-back is visible in the exported S file."""
    from cab_cwizard_pages import _CwSourcePage
    from cabxml import PropertyModel, new_property_bytes, parse_property
    import s_export
    m = _model()
    page = _CwSourcePage(m)
    m.upsert_value("heat_source", "HeatSource1", [
        ("source", "12.5", "W"),
        ("kind", "volumetric", None),
    ])
    m.bind_condition("analysis", m.domain_name() or "Domain(cuboid)",
                     "HeatSource1")
    page.refresh()
    page.apply()
    props = PropertyModel(parse_property(new_property_bytes()))
    text = s_export.build_sdat(m, props)
    assert "HeatSource1" in text
    assert "source" in text.lower()

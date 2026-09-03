"""§27 R4: partial-page storage groups — particle families, porous
subtypes, bubble nucleus, area objective function."""
from __future__ import annotations

import pytest

from cabxml import StpreModel, _first, new_stpre_bytes, parse_stpre


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


def test_particle_families_roundtrip(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwParticlePage(m)
    try:
        assert page.commit_particle_family(
            "heat_source", {"region": "Xmin面", "power": "1200.0",
                            "unit": "W"}) == "ok:heat_source"
        assert page.commit_particle_family(
            "fixed_velocity", {"vx": "1.5", "vy": "0", "vz": "0"}) \
            == "ok:fixed_velocity"
        assert page.commit_particle_family(
            "motion_udf", {"name": "usr_motion"}) == "ok:motion_udf"
        assert page.commit_particle_family(
            "statistics", {"cycle": "10"}) == "ok:statistics"
        assert page.commit_particle_family(
            "dem_gen", {"count": "200", "radius": "0.001"}) == "ok:dem_gen"
        assert page.commit_particle_family(
            "dem_restitution", {"normal": "0.9", "tangential": "0.8"}) \
            == "ok:dem_restitution"
        r = page.read_particle_family(
            "heat_source", ("region", "power"))
        assert r["region"] == "Xmin面" and r["power"] == "1200.0"
    finally:
        page.deleteLater()


def test_porous_subtypes(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwPorousPage(m)
    try:
        assert page._commit_porous_subtype(
            "moisture", source=0.5)
        assert page._commit_porous_subtype(
            "plate_fin", spacing=0.01, thickness=0.002)
        assert page._commit_porous_subtype(
            "solid_solid", conductivity=1.0)
        v = page._porous_subtype_value("plate_fin")
        assert v["subtype"] == "plate_fin" and v["spacing"] == "0.01"
        # particle release sub-page stores through the particle family
        assert page._commit_porous_subtype(
            "particle", rate=1000.0)
        assert page._porous_subtype_value("particle")["rate"] == "1000"
    finally:
        page.deleteLater()


def test_bubble_nucleus(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwBoilPage(m)
    try:
        assert page._commit_bubble_nucleus("Bub1", 1.0e5, 2000.0)
        val = m.find_value("Bub1")
        assert val is not None and val.attrib.get("type") == "bubble_nucleus"
        kids = {c.tag: (c.text or "").strip() for c in val}
        assert kids["nucleation_site"] == "100000"
        assert kids["q0"] == "2000" or kids["q0"] == "2000.0"
    finally:
        page.deleteLater()


def test_area_objective(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwTopologyOptiPage(m)
    try:
        assert page._commit_area_objective("AreaObj1", 0.05, 1.2)
        val = m.find_value("AreaObj1")
        assert val is not None and val.attrib.get("type") == "topo_area_obj"
        kids = {c.tag: (c.text or "").strip() for c in val}
        assert kids["obj_constraint"] == "0.05" and kids["weight"] == "1.2"
    finally:
        page.deleteLater()


# ------------------------------------------------- A2: UI wiring smoke

def test_particle_family_ui_wired(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwParticlePage(m)
    try:
        assert hasattr(page, "pf_table")
        page.commit_particle_family("heat_source", {"region": "Xmin",
                                                    "power": "500"})
        assert page.pf_table.rowCount() == 1
        assert page.pf_table.item(0, 0).text() == "heat_source"
        assert "power=500" in page.pf_table.item(0, 1).text()
    finally:
        page.deleteLater()


def test_porous_subtype_ui_wired(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwPorousPage(m)
    try:
        assert hasattr(page, "ps_subtype")
        page.ps_subtype.setCurrentText("plate_fin")
        page.ps_k1.setValue(0.01)
        page.ps_k2.setValue(0.002)
        page._ps_apply()
        v = page._porous_subtype_value("plate_fin")
        assert v["subtype"] == "plate_fin"
        assert v["k1"] == "0.01" and v["k2"] == "0.002"
    finally:
        page.deleteLater()


def test_moving_body_ui_wired(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwMovingBodyPage(m)
    try:
        page.mo_hum_name.setText("MOHum2")
        page.mo_hum_value.setValue(60.0)
        page._mo_hum_apply()
        val = m.find_value("MOHum2")
        assert val is not None and val.attrib.get("type") == "mo_humidity"
        page.mo_ct_name.setText("MOCt2")
        page.mo_ct_value.setValue(1500.0)
        page._mo_ct_apply()
        val = m.find_value("MOCt2")
        assert val is not None and val.attrib.get("type") == "mo_contact_heat"
    finally:
        page.deleteLater()

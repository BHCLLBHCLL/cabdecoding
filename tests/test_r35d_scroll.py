"""R3.5d scroll: official part-key deep fields for panel and sphere
(exA15-x 溶融鋼部 / exA07-3 球1 schemas), storage + panel + geometry
consumption."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


@pytest.fixture(scope="module")
def qapp():
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([sys.argv[0]])
    yield app


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def test_panel_official_keys_roundtrip():
    """exA15-x 溶融鋼部 schema: percent=-1, thick=0 (zero-thickness
    cface panel)."""
    m = _model()
    m.add_part(name="溶融鋼部", kind="panel", attribute="cface")
    assert m.set_part_params("溶融鋼部", {"percent": -1.0, "thick": 0.0})
    params = m.part_params("溶融鋼部")
    assert params == {"percent": -1.0, "thick": 0.0}
    el = m.find_part("溶融鋼部")
    assert el.findtext("percent").strip() == "-1"
    assert el.find("thick").attrib.get("unit") == "mm"


def test_sphere_official_keys_roundtrip():
    """exA07-3 球1 schema: radius3 ellipsoid triple, angle span,
    divide, percent, thick."""
    m = _model()
    m.add_part(name="球1", kind="sphere", attribute="solid")
    assert m.set_part_params("球1", {
        "radius3": "20,20,20", "angle": "0,360",
        "divide": 48, "percent": 0.0, "thick": 0.0})
    params = m.part_params("球1")
    assert params["radius3"] == [20.0, 20.0, 20.0]
    assert params["angle"] == [0.0, 360.0]
    assert params["divide"] == 48
    el = m.find_part("球1")
    r3 = el.find("radius3")
    assert r3.attrib.get("unit") == "mm"
    assert r3.text.strip() == "20,20,20"
    assert el.findtext("divide").strip() == "48"


def test_sphere_tess_consumes_radius3():
    """Geometry reads the official radius3 triple as an ellipsoid and
    the divide key."""
    from cab_parts import tess_for_part
    m = _model()
    m.add_part(name="球椭", kind="sphere", attribute="solid")
    el = m.find_part("球椭")
    from xml.etree import ElementTree as ET
    for tag, text, unit in (("center", "0,0,0", "mm"),
                            ("radius3", "30,20,10", "mm"),
                            ("divide", "24", None)):
        c = ET.SubElement(el, tag)
        c.text = f" {text} "
        if unit:
            c.attrib["unit"] = unit
    part = m.parts()[0]
    tess = tess_for_part(part)
    assert tess is not None
    xs = [p[0] for p in tess.points]
    ys = [p[1] for p in tess.points]
    # ellipsoid extents along x/y reflect the anisotropic radii
    assert max(xs) - min(xs) == pytest.approx(0.060, abs=1e-3)
    assert max(ys) - min(ys) == pytest.approx(0.040, abs=1e-3)


def test_sphere_scalar_radius_still_works():
    """Legacy scalar <radius> path unchanged."""
    from cab_parts import tess_for_part
    m = _model()
    m.add_part(name="球2", kind="sphere", attribute="solid")
    el = m.find_part("球2")
    from xml.etree import ElementTree as ET
    for tag, text, unit in (("center", "0,0,0", "mm"),
                            ("radius", "5", "mm")):
        c = ET.SubElement(el, tag)
        c.text = f" {text} "
        if unit:
            c.attrib["unit"] = unit
    tess = tess_for_part(m.parts()[0])
    xs = [p[0] for p in tess.points]
    assert max(xs) - min(xs) == pytest.approx(0.010, abs=1e-3)


def test_special_params_panel_groups(qapp):
    """SpecialParamsPanel shows the new panel/sphere groups and
    round-trips the official values."""
    from cab_dialogs import SpecialParamsPanel
    m = _model()
    m.add_part(name="溶融鋼部", kind="panel", attribute="cface")
    m.set_part_params("溶融鋼部", {"percent": -1.0, "thick": 0.0})
    panel = SpecialParamsPanel(m, "溶融鋼部")
    panel.load()
    assert ("percent", None) in panel.edits
    assert ("thick", None) in panel.edits
    panel.edits[("thick", None)].setValue(2.5)
    assert panel.commit()
    assert m.part_params("溶融鋼部")["thick"] == pytest.approx(2.5)
    m.add_part(name="球1", kind="sphere", attribute="solid")
    p2 = SpecialParamsPanel(m, "球1")
    assert ("radius3", None) in p2.edits
    assert ("divide", None) in p2.edits


def test_csv_arity_accepts_any_length():
    """fmt='csv' accepts 2/3-value rows without the int-arity check."""
    m = _model()
    m.add_part(name="球3", kind="sphere", attribute="solid")
    assert m.set_part_params("球3", {"angle": "0,180"})
    assert m.set_part_params("球3", {"angle": "0,180,45"})
    assert m.part_params("球3")["angle"] == [0.0, 180.0, 45.0]


def test_enclosure_official_case_cube_keys(qapp):
    """exA07-5 Duct_case schema: thickness 6-value per-face wall + 
    solar_property on the canonical enclosure kind."""
    from cab_dialogs import SpecialParamsPanel
    m = _model()
    m.add_part(name="Duct_case", kind="enclosure", attribute="solid")
    assert m.set_part_params("Duct_case", {
        "thickness": "5,5,5,5,5,50",
        "solar_property": "吸収体"})
    params = m.part_params("Duct_case")
    assert params["thickness"] == [5.0, 5.0, 5.0, 5.0, 5.0, 50.0]
    assert params["solar_property"] == "吸収体"
    el = m.find_part("Duct_case")
    th = el.find("thickness")
    assert th.attrib.get("unit") == "mm"
    assert th.text.strip() == "5,5,5,5,5,50"
    panel = SpecialParamsPanel(m, "Duct_case")
    panel.load()
    assert ("thickness", None) in panel.edits
    assert panel.edits[("solar_property", None)].text() == "吸収体"

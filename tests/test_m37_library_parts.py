"""M37: library register stubs + AC/Diffuser kinds + thermal tint helper."""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cabxml import StpreModel, new_stpre_bytes, parse_stpre
import cab_parts


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_ac_unit_and_diffuser_kinds():
    assert "ac_unit" in cab_parts.PRIMITIVE_KINDS
    assert "diffuser" in cab_parts.PRIMITIVE_KINDS
    ac = cab_parts.tess_for_spec(
        "ac_unit", {"base": (0, 0, 0), "size": (20, 20, 10)})
    assert ac is not None and len(ac.points) > 0
    df = cab_parts.tess_for_spec(
        "diffuser", {"base": (0, 0, 0), "size": (20, 20, 40)})
    assert df is not None and len(df.points) > 0


def test_register_primitive_ac_unit_xml():
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    ok = cab_parts.register_primitive(
        m, name="ACUnit1", kind="ac_unit",
        params={"base": (0, 0, 0), "size": (30, 20, 15)},
        material="aluminum", attribute="Solid", color="100,160,220,255")
    assert ok
    el = m.find_part("ACUnit1")
    assert el is not None
    assert el.attrib.get("type") == "ac_unit"


def test_project_part_library_json_roundtrip():
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    lib = [{
        "name": "HeatBlock",
        "kind": "cube",
        "attribute": "Solid",
        "material": "aluminum",
        "heat_source": 12.0,
        "params": {"base": [0, 0, 0], "size": [10, 10, 10]},
        "summary": "kind=cube; heat=12.0",
    }]
    assert m.set_project_value(
        "part_library", json.dumps(lib, ensure_ascii=False))
    again = StpreModel(parse_stpre(m.doc.serialize()))
    raw = again.project_value("part_library", "")
    data = json.loads(raw)
    assert data[0]["name"] == "HeatBlock"
    assert data[0]["heat_source"] == 12.0


def test_thermal_tint_helper(qapp):
    from cab_gui import CabViewer
    from cabxml import _first, set_text
    import xml.etree.ElementTree as ET

    m = StpreModel(parse_stpre(new_stpre_bytes()))
    cab_parts.register_primitive(
        m, name="Hot1", kind="cube",
        params={"base": (0, 0, 0), "size": (10, 10, 10)},
        material="", attribute="Solid", color="180,180,180,255")
    el = m.find_part("Hot1")
    hs = ET.SubElement(el, "heat_source")
    set_text(hs, "50")
    v = CabViewer.__new__(CabViewer)
    v.model = m
    v._thermal_display = {"heat_source": True, "temperature": False}
    tint = CabViewer._thermal_tint_for_part(v, "Hot1", (0.7, 0.7, 0.7))
    assert tint[0] > tint[2]  # warmer / redder than blue

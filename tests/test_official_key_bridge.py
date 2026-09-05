"""Official-key bridges: two_resistor <-> network condition keys
(exA22-1 resistance J-T/J-B + source J) and axial_fan sketch-style
keys -> FANV_REGION derivation (exA13-1)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET

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


def _lines(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def _official_network(m, name="熱回路網モデル1"):
    """Create a part carrying the exA22-1 official network schema."""
    m.add_part(name=name, kind="two_resistor", attribute="solid")
    el = m.find_part(name)
    ET.SubElement(el, "package").text = " TWO_RESIST "
    ET.SubElement(el, "base").attrib["unit"] = "mm"
    el.find("base").text = " 0,0,0 "
    cond = ET.SubElement(el, "condition")
    r1 = ET.SubElement(cond, "resistance")
    r1.attrib.update(node1="J", node2="T", unit="K/W")
    r1.text = " 10 "
    r2 = ET.SubElement(cond, "resistance")
    r2.attrib.update(node1="J", node2="B", unit="K/W")
    r2.text = " 5 "
    s = ET.SubElement(cond, "source")
    s.attrib.update(node="J", unit="W")
    s.text = " 1 "
    return el


def test_two_resistor_derives_from_official_keys():
    """part_params derives rjc/rjb/package_power from the official
    condition nodes; official keys win over flat children."""
    m = _model()
    _official_network(m)
    params = m.part_params("熱回路網モデル1")
    assert params["rjc"] == 10.0
    assert params["rjb"] == 5.0
    assert params["package_power"] == 1.0
    assert params["package"] == "TWO_RESIST"


def test_two_resistor_write_back_to_official_keys():
    """set_part_params updates the official resistance/source nodes in
    place (no flattening)."""
    m = _model()
    _official_network(m)
    assert m.set_part_params("熱回路網モデル1",
                             {"rjc": 12.5, "rjb": 6.0,
                              "package_power": 2.0})
    el = m.find_part("熱回路網モデル1")
    cond = el.find("condition")
    ress = {r.attrib.get("node2"): r.text.strip()
            for r in cond.findall("resistance")}
    assert ress["T"] == "12.5"
    assert ress["B"] == "6"
    assert cond.find("source").text.strip() == "2"
    # derived read reflects the write
    params = m.part_params("熱回路網モデル1")
    assert params["rjc"] == 12.5 and params["rjb"] == 6.0


def test_axial_fan_official_keys_fanv_derivation():
    """exA13-1 official sketch-style axial_fan -> FANV_REGION card with
    v12=size (m), name, dual region rows."""
    m = _model()
    m.add_part(name="軸流ファン", kind="axial_fan", attribute="area")
    el = m.find_part("軸流ファン")
    for tag, text, unit in (
            ("kind", "circle", None), ("panel_kind", "2", None),
            ("center", "1.2,1.2,0", "m"),
            ("size", "0.098,0.27", "m"),
            ("thick", "0.067,0.067", "m"),
            ("sketch_plane", "-0", None)):
        c = ET.SubElement(el, tag)
        c.text = f" {text} "
        if unit:
            c.attrib["unit"] = unit
    lines = _lines(m)
    i = lines.index("FANV_REGION")
    assert lines[i + 1] == "circle   0  ! 軸流ファン"
    assert lines[i + 2] == f"{0.098:29.14e}{0.27:26.14e}"
    assert lines[i + 5] == "   @T:fanpq"
    assert lines[i + 9] == "   軸流ファン"
    assert lines[i + 11] == "   軸流ファン_inlet"
    assert lines[i + 13] == "/"


def test_axial_fan_without_official_keys_no_fanv():
    """Non-official axial_fan parts (no panel_kind) keep the hand-tuned
    analysis_etc/fanv_region path; no derivation."""
    m = _model()
    m.add_part(name="fan1", kind="axial_fan", attribute="solid")
    assert "FANV_REGION" not in _lines(m)


def test_axial_fan_panel_official_keys(qapp):
    from cab_dialogs import SpecialParamsPanel
    m = _model()
    m.add_part(name="軸流ファン", kind="axial_fan", attribute="area")
    m.set_part_params("軸流ファン", {"panel_kind": 2,
                                     "sketch_plane": "-0"})
    panel = SpecialParamsPanel(m, "軸流ファン")
    panel.load()
    assert ("panel_kind", None) in panel.edits
    assert ("sketch_plane", None) in panel.edits
    assert panel.edits[("sketch_plane", None)].text() == "-0"

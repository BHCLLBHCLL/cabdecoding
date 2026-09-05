"""I3 + I1c leftovers: SURF_WAVEGENE (official cab mapping), LAMP
family, ECUR_CONTROL/ECUR_BOUNDARY extensions, JOS verbatim cards and
the TABLE UI on the Output Series page."""
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


def _lines(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def test_surf_wavegene_official_mapping():
    """exA15-6 .cab storage (kind=stokes3 angle=0 bias=7 depth=7
    height=2 period=5 num=0) -> official card bytes."""
    m = _model()
    m.upsert_value("wave_gen", "自由表面3", [
        ("kind", "stokes3", None), ("angle", "0", None),
        ("bias", "7", "m"), ("depth", "7", "m"),
        ("height", "2", "m"), ("period", "5", None),
        ("num", "0", None)])
    m.bind_condition("parts", "WavePart", "自由表面3")
    lines = _lines(m)
    i = lines.index("SURF_WAVEGENE")
    assert lines[i:i + 6] == [
        "SURF_WAVEGENE",
        "Stokes3  1  7  7  0",
        f"{2.0:29.14e}{5.0:26.14e}",
        f"{100.0:29.14e}{0.0:26.14e}{1.0:26.14e}",
        "   /",
        "/",
    ]


def test_lamp_family():
    """exA07-5 — LAMP_REGION diffusion card + LAMP_RAYDRAW table."""
    m = _model()
    m.ensure_analysis_etc_section("lamp_region")
    lr = m.root.find("analysis_etc/lamp_region")
    import xml.etree.ElementTree as ET
    r = ET.SubElement(lr, "row")
    r.attrib.update(kind="diffusion", count="10", value="20",
                    region="Lamp_surf")
    m.ensure_analysis_etc_section("lamp_raydraw")
    rd = m.root.find("analysis_etc/lamp_raydraw")
    for kw, v in (("NRAY", "1000"), ("NDIV", "1"), ("ISW_OUT", "2")):
        ET.SubElement(rd, kw).text = f" {v} "
    lines = _lines(m)
    i = lines.index("LAMP_REGION")
    assert lines[i:i + 5] == [
        "LAMP_REGION",
        "diffusion          10",
        f"{20.0:29.14e}",
        "   Lamp_surf",
        "   /",
    ]
    assert lines[i + 5] == "/"
    j = lines.index("LAMP_RAYDRAW")
    assert lines[j:j + 4] == [
        "LAMP_RAYDRAW",
        "    NRAY         1000",
        "    NDIV            1",
        "    ISW_OUT         2",
    ]
    assert lines[j + 4] == "/"


def test_ecur_control_and_boundary():
    """exA12-2a — ECUR_CONTROL keyword table + ECUR_BOUNDARY records."""
    m = _model()
    m.ensure_analysis_etc_section("ecur")
    ec = m.root.find("analysis_etc/ecur")
    ec.attrib.update(control_kind="joule_ht_by_resist", control_val="1")
    import xml.etree.ElementTree as ET
    b = ET.SubElement(ec, "ebound")
    b.attrib.update(kind="epotential", no="0", name="電流1",
                    value="0", region="Side-A")
    lines = _lines(m)
    i = lines.index("ECUR_CONTROL")
    assert lines[i:i + 4] == ["ECUR_CONTROL", "joule_ht_by_resist",
                              f"{1:>15d}", "/"]
    j = lines.index("ECUR_BOUNDARY")
    assert lines[j:j + 5] == [
        "ECUR_BOUNDARY",
        "epotential    0   ! 電流1",
        f"{0.0:26.14e}",
        "   Side-A",
        "   /",
    ]
    assert lines[j + 5] == "/"


def test_jos_verbatim_cards():
    m = _model()
    m.ensure_analysis_etc_section("jos")
    jos = m.root.find("analysis_etc/jos")
    import xml.etree.ElementTree as ET
    c = ET.SubElement(jos, "card")
    c.attrib.update(
        name="JOS_PERSON",
        lines="   BodyType1|   MALE            20"
              "      1.60000000000000e+01      6.00000000000000e+01")
    lines = _lines(m)
    i = lines.index("JOS_PERSON")
    assert lines[i + 1] == "   BodyType1"
    assert lines[i + 2].startswith("   MALE")
    assert lines[i + 3] == "/"


def test_table_ui_roundtrip(qapp):
    """Output Series page TABLE group -> value storage -> TABLE card."""
    from cab_cwizard_pages import _CwOutputSeriesPage
    m = _model()
    page = _CwOutputSeriesPage(m)
    page._tbl_add("fanpq", "simple", "0.6166666666666667", "127.4")
    page._tbl_add("fanpq", "simple", "1.3333333333333333", "0")
    page.apply()
    val = m.find_value("fanpq")
    assert val is not None and val.attrib.get("type") == "table"
    assert len(val.findall("row")) == 2
    lines = _lines(m)
    i = lines.index("TABLE")
    assert lines[i:i + 5] == [
        "TABLE",
        "   fanpq   ! fanpq",
        "   simple",
        f"{2:>7d}",
        f"{0.6166666666666667:>27.14e}{127.4:>25.14e}",
    ]
    page2 = _CwOutputSeriesPage(m)
    assert page2.tbl_table.rowCount() == 2


def test_lamp_page_ui_roundtrip(qapp):
    from cab_cwizard_pages import _CwLampPage
    m = _model()
    page = _CwLampPage(m)
    page._lamp_region_add("diffusion", "10", "20", "Lamp_surf")
    page._raydraw_add("NRAY", "1000")
    page.apply()
    assert len(m.root.findall("analysis_etc/lamp_region/row")) == 1
    page2 = _CwLampPage(m)
    assert page2.lamp_region_table.rowCount() == 1
    assert page2.raydraw_table.item(0, 0).text() == "NRAY"


def test_current_page_ecur_ext_roundtrip(qapp):
    from cab_cwizard_pages import _CwCurrentPage
    m = _model()
    page = _CwCurrentPage(m)
    page.ecur_control_kind.setCurrentIndex(
        page.ecur_control_kind.findData("joule_ht_by_resist"))
    page._ecb_add("epotential", "0", "電流1", "0", "Side-A")
    page.apply()
    ec = m.root.find("analysis_etc/ecur")
    assert ec.attrib["control_kind"] == "joule_ht_by_resist"
    assert len(ec.findall("ebound")) == 1
    page2 = _CwCurrentPage(m)
    assert page2.ecb_table.rowCount() == 1


def test_absent_without_storage():
    lines = _lines(_model())
    for cmd in ("SURF_WAVEGENE", "LAMP_REGION", "LAMP_RAYDRAW",
                "ECUR_CONTROL", "ECUR_BOUNDARY", "TABLE"):
        assert cmd not in lines, cmd

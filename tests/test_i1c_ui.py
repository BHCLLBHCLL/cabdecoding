"""I1c: subsystem UI wiring — Reaction page chem group (SNAM/CDIF/
REAC/VDFU), Current page ECUR group, Solar page SOLAR/SOLA_DEFAULT/
SOLA_REGION group, each verified through the full
UI -> storage -> .s emission loop."""
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


def test_reaction_page_chem_group(qapp):
    """exA04-1 / exA03-1 loop: SNAM line edits + table rows -> chem
    storage -> SNAM/CDIF/REAC_REGION/VDFU_REGION cards."""
    from cab_cwizard_pages import _CwReactionPage
    m = _model()
    page = _CwReactionPage(m)
    page.snam_r1.setText("R1")
    page.snam_r2.setText("R2")
    page.snam_p1.setText("P1")
    page.snam_p2.setText("P2")
    page._dif_add("cn1", "0.0")
    page._reac_add("1", "R1 + 2R2 => P1 + 2P2",
                   "1.5", "0", "0", "10000", "1", "2", "0", "0",
                   "円柱領域")
    page._vdfu_add("CN01", "拡散1", "3.0", "煙H")
    page.apply()
    chem = m.root.find("analysis_etc/chem")
    assert chem is not None
    assert chem.find("snam").attrib["r1"] == "R1"
    assert len(chem.findall("dif")) == 1
    assert len(chem.findall("reac")) == 1
    assert len(chem.findall("vdfu")) == 1
    lines = _lines(m)
    assert lines[lines.index("SNAM") + 1] == "   R1              "
    assert lines[lines.index("CDIF") + 1] == f"{0.0:29.14e}  ! cn1"
    j = lines.index("REAC_REGION")
    assert lines[j + 2] == "    R1 + 2R2 => P1 + 2P2"
    k = lines.index("VDFU_REGION")
    assert lines[k:k + 3] == ["VDFU_REGION", "CN01",
                              "source    0   ! 拡散1"]
    # reload into a fresh page
    page2 = _CwReactionPage(m)
    assert page2.snam_r1.text() == "R1"
    assert page2.dif_table.rowCount() == 1
    assert page2.reac_table.rowCount() == 1
    assert page2.vdfu_table.rowCount() == 1


def test_current_page_ecur_group(qapp):
    """exA12-1 loop: ECUR head/mag/props through the Current page."""
    from cab_cwizard_pages import _CwCurrentPage
    m = _model()
    page = _CwCurrentPage(m)
    page.ecur_i1.setValue(1)
    page.ecur_mag_kind.setCurrentIndex(
        page.ecur_mag_kind.findData("uniform"))
    page.ecur_mag_region.setText("@S:rbmx")
    page._ecur_add("1", "1e6")
    page._ecur_add("2", "1e6")
    page.apply()
    ec = m.root.find("analysis_etc/ecur")
    assert ec is not None and ec.attrib["mag_kind"] == "uniform"
    lines = _lines(m)
    i = lines.index("ECUR")
    assert lines[i + 1] == f"{1:12d}{0:12d}{0:12d}"
    assert lines[i + 3] == "uniform   0"
    assert lines[i + 4] == f"     @S:rbmx{0.0:26.14e}{0.0:26.14e}"
    assert lines[i + 6] == f"{1:12d}{1e6:26.14e}"
    assert lines[i + 7] == f"{2:12d}{1e6:26.14e}"
    page2 = _CwCurrentPage(m)
    assert page2.ecur_table.rowCount() == 2
    assert page2.ecur_mag_region.text() == "@S:rbmx"


def test_solar_page_solar_cards(qapp):
    """exA08-1 loop: SOLAR head (lat/lon/meridian from the location
    widgets) + SOLA_DEFAULT + region rows through the Solar page."""
    from cab_cwizard_pages import _CwSolarPage
    m = _model()
    page = _CwSolarPage(m)
    page.enable.setChecked(True)
    page.lat.setValue(35.680)
    page.lon.setValue(139.770)
    page.tz.setValue(9)
    page.solar_emit.setChecked(True)
    page.solar_ashrae.setValue(0.1)
    page.solar_monthly1.setText(
        "0.392,0.434,0.496,0.534,0.544,0.541,0.510,0.502,0.457,"
        "0.430,0.415,0.368")
    page.solar_monthly2.setText(
        "2.323,2.154,1.965,1.862,1.836,1.884,2.021,2.073,2.268,"
        "2.325,2.333,2.450")
    page._sola_add("body_d", "吸収体", "1.0", "0", "0", "0", "0",
                   "Duct_case")
    page.apply()
    sol = m.root.find("analysis_etc/solar")
    assert sol is not None and sol.attrib["lat"] == "35.68"
    assert sol.attrib["meridian"] == "135"
    lines = _lines(m)
    i = lines.index("SOLAR")
    assert lines[i + 1] == " latitude_dec"
    assert lines[i + 2] == "     35.680    139.770    135.000"
    assert lines[i + 6] == " ASHRAE      1.00000000000000e-01"
    j = lines.index("SOLA_DEFAULT")
    assert lines[j:j + 3] == ["SOLA_DEFAULT", "    IDRF        1",
                              "    SKY      1.00000e+00"]
    k = lines.index("SOLA_REGION")
    assert lines[k:k + 6] == [
        "SOLA_REGION",
        "body_d",
        f"{1.0:28.14e}{0.0:27.14e}{0.0:27.14e}{0.0:27.14e}  ! 吸収体",
        "   0",
        "   Duct_case",
        "   /",
    ]
    page2 = _CwSolarPage(m)
    assert page2.solar_emit.isChecked()
    assert page2.sola_table.rowCount() == 1
    assert page2.sola_table.item(0, 7).text() == "Duct_case"

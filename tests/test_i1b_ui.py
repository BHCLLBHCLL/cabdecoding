"""I1b: specialty-page UI wiring — humidity evaporation family
(HUMD_CONTROL / HUMC / type=4 fluxhumid), free-surface extensions
(VOF2 / SURF_1MARS / SURF_AENT / VFRT_SPC) and the LES page
(LES_INIT / LES_OPTION), each verified through the full
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


def test_humidity_page_humd_humc_and_fluxhumid(qapp):
    """exA05-1 loop: HUMD_CONTROL/HUMC widgets + fluxhumid button ->
    storage -> HUMD_CONTROL/HUMC/HUMF_REGION cards."""
    from cab_cwizard_pages import _CwHumidityPage
    m = _model()
    page = _CwHumidityPage(m)
    page.humd_evaporation.setChecked(True)
    page.humd_upper.setChecked(True)
    page.humc_value.setValue(2.56e-05)
    page.apply()
    assert m.root.find("analysis_etc/humd_control") is not None
    assert m.root.find("analysis_etc/humc") is not None
    # fluxhumid condition via the page's own commit path
    assert page._commit_humidity("湿度1", 4, -0.000309, 0.0, "風呂湯面")
    lines = _lines(m)
    i = lines.index("HUMD_CONTROL")
    assert lines[i:i + 5] == ["HUMD_CONTROL", "evaporation", f"{1:>15d}",
                              "upper_limit", f"{1:>15d}"]
    j = lines.index("HUMC")
    assert lines[j + 1] == f"{2.56e-05:29.14e}"
    assert lines[j + 2] == "HUMF_REGION"
    assert lines[j + 3] == "fluxhumid    0   ! 湿度1"
    assert lines[j + 4] == f"{-0.000309:29.14e}{0.0:26.14e}"
    assert lines[j + 5] == "   風呂湯面"


def test_free_surface_page_vof2_1mars_aent_vfrt(qapp):
    """exA09-4/exA15-3/exA15-1/exA02-2a loop through the evaporation
    page's Free Surface group."""
    from cab_cwizard_pages import _CwEvaporationPage
    m = _model()
    page = _CwEvaporationPage(m)
    page.fs_enable.setChecked(True)
    page.fs_p2_name.setText("水")
    page.fs_p2_density.setValue(1.0)
    page.fs_1mars_m1.setValue(2)
    page.fs_1mars_m2.setValue(0)
    page.fs_aent_kind.setCurrentIndex(
        page.fs_aent_kind.findData("adiabatic"))
    page.fs_aent_value.setValue(0.0)
    page.fs_vfrt_region.setText("直方体領域")
    # tension is the SURF-family emission gate (see _free_surf_sections)
    m.set_free_surf_attr("tension", "0,0.0727")
    page.apply()
    assert m.free_surf_attr("phase2_name") == "水"
    assert m.free_surf_attr("surf_1mars") == "2,0"
    assert m.free_surf_attr("surf_aent_kind") == "adiabatic"
    assert m.free_surf_attr("vfrt_spc_region") == "直方体領域"
    lines = _lines(m)
    i = lines.index("VOF2")
    assert lines[i:i + 4] == ["VOF2", f"{1.0:29.14e}", "   水", "   /"]
    j = lines.index("SURF_1MARS")
    assert lines[j + 1] == f"{2:>15d}{0:12d}"
    k = lines.index("SURF_AENT")
    assert lines[k:k + 3] == ["SURF_AENT", "   adiabatic",
                              f"{0.0:26.14e}"]
    v = lines.index("VFRT_SPC")
    assert lines[v:v + 3] == ["VFRT_SPC", "    直方体領域", "/"]
    assert j < k < lines.index("SURF_PROPERTY") < v


def test_free_surface_page_off_clears_vof2(qapp):
    from cab_cwizard_pages import _CwEvaporationPage
    m = _model()
    page = _CwEvaporationPage(m)
    page.fs_enable.setChecked(True)
    page.fs_p2_name.setText("水")
    page.apply()
    page.fs_p2_name.setText("")
    page.apply()
    assert m.free_surf_attr("phase2_name", "") == ""
    assert "VOF2" not in _lines(m)


def test_les_page_registered_and_roundtrip(qapp):
    """_CwLesPage exists, is registered in the wizard flow, and its
    apply -> storage -> LES_INIT/LES_OPTION emission matches exB18."""
    import cab_wizards as w
    from cab_cwizard_pages import _CwLesPage
    flow = [k for k, _l, _p in w._CW_PAGES]
    assert "les" in flow
    m = _model()
    page = _CwLesPage(m)
    page.init_enable.setChecked(True)
    page.init_name.setText("条件7")
    page.init_region.setText("ドライバー領域")
    page._opt_add("wiggle_sensor", "1")
    page._opt_add("time_integration", "0")
    page.apply()
    li = m.root.find("analysis_etc/les_init")
    assert li is not None and li.findtext("region").strip() == \
        "ドライバー領域"
    lo = m.root.find("analysis_etc/les_option")
    assert lo is not None and lo.findtext("wiggle_sensor").strip() == "1"
    lines = _lines(m)
    i = lines.index("LES_INIT")
    assert lines[i:i + 5] == [
        "LES_INIT",
        "random  ! 条件7",
        f"{1.0:29.14e}{3.0:26.14e}{3.0:26.14e}",
        "   ドライバー領域",
        "   /",
    ]
    j = lines.index("LES_OPTION")
    assert lines[j:j + 5] == ["LES_OPTION", "wiggle_sensor", f"{1:>15d}",
                              "time_integration", f"{0:>15d}"]
    # reload into a fresh page
    page2 = _CwLesPage(m)
    assert page2.init_enable.isChecked()
    assert page2.opt_table.rowCount() == 2
    assert page2.opt_table.item(0, 0).text() == "wiggle_sensor"

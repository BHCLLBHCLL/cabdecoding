"""I1a: Solver Control tab in _CwSolverPage — UI wiring for the
H1b/H1h header flags (PCTY/TBEC/JFNK/WALL_MODEL/CYLD/LESM/UPWD) and
the STMC/PBAS_MATERIAL row tables, verified through the full
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


def _page(m):
    from cab_cwizard_pages import _CwSolverPage
    return _CwSolverPage(m)


def test_tab_present_and_loaded(qapp):
    m = _model()
    page = _page(m)
    tabs = page.tabs
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Solver Control" in labels
    # defaults load as zeros / empty
    assert page.pcty.value() == 0
    assert page.upwd_mask.text() == ""
    assert page.stmc_table.rowCount() == 0
    assert page.pbas_table.rowCount() == 0


def test_flags_apply_and_emit(qapp):
    """Widgets -> analysis_set storage -> UPWD/TBEC/PCTY cards in the
    rendered .s (byte-checked against exA23-1a / exA01-1 / exB18)."""
    m = _model()
    page = _page(m)
    page.pcty.setValue(3)
    page.tbec.setValue(1)
    page.jfnk_flag.setValue(10)
    page.wall_model.setValue(2)
    page.cyl_a.setValue(1)
    page.cyl_b.setValue(1)
    page.lesm_m.setValue(2)
    page.lesm_s1.setValue(5)
    page.lesm_s2.setValue(5)
    page.upwd_mask.setText("11000000")
    page.apply()
    # storage side
    assert m.analysis_set_value("pcty") == "3"
    assert m.analysis_set_value("tbec") == "1"
    assert m.analysis_set_value("jfnk") == "10"
    assert m.analysis_set_value("wall_model") == "2"
    assert m.analysis_set_value("cyl_coord") == "1,1"
    assert m.analysis_set_value("lesm") == "2,5,5"
    assert m.analysis_set_value("upwd_mask") == "11000000"
    # emission side
    from s_export import build_sdat
    lines = build_sdat(m, _props()).split("\r\n")
    assert lines[lines.index("UPWD") + 1] == "11000000"
    assert lines[lines.index("TBEC") + 1] == f"{1:12d}"
    assert lines[lines.index("PCTY") + 1] == f"{3:12d}"
    assert lines[lines.index("CYLD") + 1] == f"{1:12d}{1:12d}"
    i = lines.index("LESM")
    assert lines[i + 1] == f"{2:>15d}"
    assert lines[i + 2] == f"{5:>15d}{5:12d}"
    assert lines[lines.index("JFNK") + 1] == "10"
    assert lines[lines.index("WALL_MODEL") + 1] == f"{2:>15d}"


def test_stmc_pbas_row_tables_roundtrip_and_emit(qapp):
    m = _model()
    page = _page(m)
    page.stmc_flag.setValue(1)
    page._stmc_add_row()
    page.stmc_table.item(0, 0).setText("1")
    page.stmc_table.item(0, 1).setText("0.99,0.5,0.0001")
    page._stmc_add_row()
    page.stmc_table.item(1, 0).setText("5")
    page.stmc_table.item(1, 1).setText("0.9999")
    page._pbas_add_row()
    page.pbas_table.item(0, 0).setText("1")
    page.pbas_table.item(0, 1).setText("101325")
    page.pbas_table.item(0, 2).setText("0")
    page.apply()
    # reload into a fresh page (storage -> widgets)
    page2 = _page(m)
    assert page2.stmc_table.rowCount() == 2
    assert page2.stmc_table.item(0, 1).text() == "0.99,0.5,0.0001"
    assert page2.pbas_table.rowCount() == 1
    assert page2.pbas_table.item(0, 1).text() == "101325"
    # emission side (exA23-4 / exA14-1)
    from s_export import build_sdat
    lines = build_sdat(m, _props()).split("\r\n")
    i = lines.index("STMC")
    assert lines[i + 1] == f"{1:>15d}"
    assert lines[i + 3] == (
        f"{1:12d}{0.99:26.14e}{0.5:26.14e}{0.0001:26.14e}")
    j = lines.index("PBAS_MATERIAL")
    assert lines[j + 1] == f"{1:12d}{101325.0:26.14e}{0.0:26.14e}"


def test_row_delete_and_mask_clear(qapp):
    m = _model()
    page = _page(m)
    page._stmc_add_row()
    page.stmc_table.selectRow(0)
    page._stmc_del_row()
    assert page.stmc_table.rowCount() == 0
    page.upwd_mask.setText("11000000")
    page.apply()
    page2 = _page(m)
    page2.upwd_mask.setText("")
    page2.apply()
    # cleared mask drops the storage tag -> no UPWD emission
    assert m.analysis_set_value("upwd_mask", "") == ""
    from s_export import build_sdat
    assert "\r\nUPWD\r\n" not in build_sdat(m, _props())

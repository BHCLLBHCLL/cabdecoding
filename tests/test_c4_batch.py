"""§23 C4 batch: FLUX_SUM (Output Passage) .s emission with the official
exA18-2 card layout, plus the L File Standardized Concentration tab."""
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


def _add_passage(model, name, region):
    """Create one Output Passage condition (official exA18-2 shape)."""
    assert model.upsert_value("list_summary", name, [
        ("heat_flux", "1", None),
    ])
    assert model.bind_condition("region", region, name)


def test_flux_sum_matches_official_layout():
    """Two list_summary values bound to in/out reproduce the exA18-2
    FLUX_SUM block verbatim (evidence-locked card layout)."""
    from s_export import build_sdat
    m = _model()
    _add_passage(m, "通過流量1", "in")
    _add_passage(m, "通過流量2", "out")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("FLUX_SUM")
    block = lines[i:i + 9]
    assert block == [
        "FLUX_SUM",
        f"{1:15d}",
        "heat_flux",
        "    in",
        "   /",
        "heat_flux",
        "    out",
        "   /",
        "/",
    ]
    # section sits right after FBAL's card (official exA18-2 order)
    assert lines[i - 2:i] == ["FBAL", f"{1:5d}:L"]


def test_flux_sum_absent_without_passage_values():
    """No list_summary values -> no FLUX_SUM section (ex4_e golden keeps
    byte parity; empty sections are omitted like PELTIER/CUTCELL)."""
    from s_export import build_sdat
    m = _model()
    s = build_sdat(m, _props())
    assert "FLUX_SUM" not in s


def test_flux_sum_quantity_gate():
    """A list_summary value with heat_flux unset emits nothing."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("list_summary", "passage1", [("heat_flux", "0", None)])
    m.bind_condition("region", "in", "passage1")
    assert "FLUX_SUM" not in build_sdat(m, _props())


def test_lfile_page_standardized_concentration_tab(qapp):
    """L File page: 10 STpre tabs including Standardized Concentration in
    Living Space; apply persists enable + cycle."""
    try:
        import sys

        from PyQt5.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt5 not available")
    QApplication.instance() or QApplication([sys.argv[0]])
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwOutputLFilePage(m)
    try:
        titles = [page.tabs.tabText(i) for i in range(page.tabs.count())]
        assert len(titles) == 10
        assert "Standardized Concentration in Living Space" in titles
        idx = titles.index("Standardized Concentration in Living Space")
        page.tabs.setCurrentIndex(idx)
        page.ncoz_on.setChecked(False)
        page.ncoz_cycle.setValue(7)
        page.apply()
        assert m.analysis_set_value("lfile_ncoz") == "F"
        assert m.analysis_set_value("lfile_ncoz_cycle") == "7"
        page.ncoz_on.setChecked(True)
        page.apply()
        assert m.analysis_set_value("lfile_ncoz") == "T"
    finally:
        page.deleteLater()

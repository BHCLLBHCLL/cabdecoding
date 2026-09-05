"""I5: region scalar family CW panel (o2/n2/h2/vofl/trt2/tret/tpor on
the Initial Condition page) + VFRE/WLTY/VFGO header flags on the
Solver Control tab — closing the D6 named gap from gap §0.4."""
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


def test_initial_page_region_scalars_panel(qapp):
    """UI rows -> o2/h2/tpor value storage + bindings -> official
    region-float cards."""
    from cab_wizards import _CwInitialPage
    m = _model()
    page = _CwInitialPage(m)
    assert "Region Scalars" in [page.tabs.tabText(i)
                                for i in range(page.tabs.count())]
    page._rs_add("O2", "0.23184", "直方体領域")
    page._rs_add("H2", "0.9984", "直方体領域")
    page._rs_add("TPOR", "20", "多孔質体")
    page.apply()
    assert m.find_value("RS_o2_直方体領域") is not None
    lines = _lines(m)
    i = lines.index("O2")
    assert lines[i:i + 4] == ["O2", f"{0.23184:29.14e}", "   直方体領域",
                              "   /"]
    j = lines.index("H2")
    assert lines[j + 1] == f"{0.9984:29.14e}"
    k = lines.index("TPOR")
    assert lines[k + 1] == f"{20.0:29.14e}"
    assert lines[k + 2] == "   多孔質体"
    # reload into a fresh page
    page2 = _CwInitialPage(m)
    assert page2.rs_table.rowCount() == 3


def test_initial_page_region_scalars_rebuild(qapp):
    """apply() rebuilds: deleting a row drops the value + binding."""
    from cab_wizards import _CwInitialPage
    m = _model()
    page = _CwInitialPage(m)
    page._rs_add("VOFL", "1.0", "Cylinder1")
    page.apply()
    assert m.find_value("RS_vofl_Cylinder1") is not None
    page.rs_table.selectRow(0)
    page._rs_del()  # remove the single row
    page.apply()
    assert m.find_value("RS_vofl_Cylinder1") is None
    assert "VOFL" not in _lines(m)


def test_solver_control_vfre_wlty_vfgo(qapp):
    """exA09-3b VFRE / exA15-1 WLTY / vf-ex2 VFGO through the Solver
    Control tab."""
    from cab_cwizard_pages import _CwSolverPage
    m = _model()
    page = _CwSolverPage(m)
    page.vfre_i.setValue(2)
    page.vfre_f.setValue(10.0)
    page.wlty.setValue(1)
    page.vfgo_a.setValue(1)
    page.vfgo_b.setValue(0)
    page.apply()
    assert m.analysis_set_value("vfre") == "2,10"
    assert m.analysis_set_value("wlty") == "1"
    assert m.analysis_set_value("vfgo") == "1,0"
    lines = _lines(m)
    i = lines.index("VFRE")
    assert lines[i + 1] == f"{2:12d}{10.0:26.14e}"
    assert lines[i + 2] == "FOUT"
    j = lines.index("WLTY")
    assert lines[j + 1] == f"{1:12d}"
    assert lines[lines.index("VFGO") + 1] == f"{1:12d}{0:12d}"
    assert lines[lines.index("VFGO") + 2] == "UNIT"
    k = lines.index("VFGO")
    assert lines[k + 1] == f"{1:12d}{0:12d}"
    # zeroing drops the storage -> no emission
    page2 = _CwSolverPage(m)
    page2.vfre_i.setValue(0)
    page2.vfre_f.setValue(0)
    page2.wlty.setValue(0)
    page2.vfgo_a.setValue(0)
    page2.vfgo_b.setValue(0)
    page2.apply()
    out = _lines(m)
    for cmd in ("VFRE", "WLTY", "VFGO"):
        assert cmd not in out, cmd

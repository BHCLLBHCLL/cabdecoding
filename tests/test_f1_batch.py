"""§25 F1 batch: condition emissions grounded in the Solver_eng manual —
STOP_VAR (stop points), PFOC_REGION (sum of pressure), NCOZ_OUTPUT
(standardized concentration)."""
from __future__ import annotations

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


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


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _stop_record(name, var, lo, lo_on, hi, hi_on):
    return f"{name}|{var}|{lo}|{lo_on}|{hi}|{hi_on}"


def test_stop_var_matches_manual_grammar():
    """stop_var records emit LVAR,X,Y,Z,VAR1,VAR2 lines with the point
    part base converted mm -> m and the manual variable codes."""
    from s_export import build_sdat
    m = _model()
    from xml.etree.ElementTree import SubElement
    from cabxml import _first, set_text
    for pname, base_txt in (("point1", "100,200,300"),
                            ("point2", "0,0,0")):
        m.add_part(name=pname, kind="point", attribute="point")
        info = next(p for p in m.parts() if p.name == pname)
        base = _first(info.elem, "base")
        if base is None:
            base = SubElement(info.elem, "base")
        set_text(base, base_txt)
    m.set_analysis_set_value("stop_var", ";".join([
        _stop_record("point1", "Temperature", "10", "1", "80", "1"),
        _stop_record("point2", "Pressure", "0", "0", "101325", "1"),
    ]))
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("STOP_VAR")
    assert lines[i + 1] == ",".join(
        ["TEMP"] + [f"{v:26.14e}" for v in (0.1, 0.2, 0.3, 10.0, 80.0)])
    # pressure point: lo disabled -> -1e30 sentinel; hi enabled
    assert lines[i + 2] == ",".join(
        ["PRES"] + [f"{v:26.14e}"
                    for v in (0.0, 0.0, 0.0, -1.0e30, 101325.0)])
    assert lines[i + 3] == "/"
    # STOP_VAR sits in the solver-control group (after AUTOFIXP)
    assert lines.index("STOP_VAR") > lines.index("AUTOFIXP")


def test_stop_var_absent_without_records():
    from s_export import build_sdat
    assert "STOP_VAR" not in build_sdat(_model(), _props())


def test_pfoc_region_matches_manual_grammar():
    """lfile_pressure_rgn (Pressure variables only) + cycle emit the
    PFOC_REGION card; non-pressure variables are skipped (LTYPE only
    'pressure' per the manual)."""
    from s_export import build_sdat
    m = _model()
    m.set_analysis_set_value(
        "lfile_pressure_rgn", "Xmin面|Pressure;Ymax面|Dynamic pressure")
    m.set_analysis_set_value("lfile_pressure_cycle", "5")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("PFOC_REGION")
    assert lines[i:i + 4] == [
        "PFOC_REGION",
        f"{5:12d}",
        "pressure",
        "   Xmin面",
    ]
    assert "   Ymax面" not in lines[i:i + 6]
    assert lines[i + 4] == "/"


def test_pfoc_region_absent_without_map():
    from s_export import build_sdat
    assert "PFOC_REGION" not in build_sdat(_model(), _props())


def test_ncoz_output_matches_manual_grammar():
    from s_export import build_sdat
    m = _model()
    m.set_analysis_set_value("lfile_ncoz", "T")
    m.set_analysis_set_value("lfile_ncoz_cycle", "10")
    m.set_analysis_set_value("lfile_ncoz_rgn", "Occupied zone")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("NCOZ_OUTPUT")
    assert lines[i:i + 4] == [
        "NCOZ_OUTPUT",
        f"{10:12d}",
        "   Occupied zone",
        "/",
    ]


def test_ncoz_output_gates():
    from s_export import build_sdat
    m = _model()
    m.set_analysis_set_value("lfile_ncoz", "F")
    m.set_analysis_set_value("lfile_ncoz_rgn", "Zone")
    assert "NCOZ_OUTPUT" not in build_sdat(m, _props())
    m.set_analysis_set_value("lfile_ncoz", "T")
    m.set_analysis_set_value("lfile_ncoz_rgn", "")
    assert "NCOZ_OUTPUT" not in build_sdat(m, _props())


def test_lfile_page_ncoz_region_persists(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwOutputLFilePage(m)
    try:
        page.ncoz_on.setChecked(True)
        page.ncoz_cycle.setValue(4)
        page.ncoz_rgn.setText("Living room")
        page.apply()
        assert m.analysis_set_value("lfile_ncoz_rgn") == "Living room"
        assert m.analysis_set_value("lfile_ncoz_cycle") == "4"
        from s_export import build_sdat
        s = build_sdat(m, _props())
        assert f"{4:12d}" in s and "   Living room" in s
    finally:
        page.deleteLater()

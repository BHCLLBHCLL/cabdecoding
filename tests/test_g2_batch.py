"""§26 G2: SURFLIST / OCSV_PARTS / PCL_RESTRICTION emissions from the
Solver_eng grammars (Solver Reference)."""
from __future__ import annotations

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _set(m, key, val):
    m.set_analysis_set_value(key, val)


def test_surf_list_matches_manual_grammar():
    from s_export import build_sdat
    m = _model()
    _set(m, "lfile_surflist", "passage_x|2;passage_y|1")
    _set(m, "lfile_surflist_cycle", "5")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("SURFLIST")
    assert lines[i:i + 7] == [
        "SURFLIST",
        f"{5:12d}",
        "areaflowratio",
        f"{2:12d}",
        "   passage_x",
        f"{1:12d}",
        "   passage_y",
    ]
    assert lines[i + 7] == "   /" and lines[i + 8] == "/"


def test_surf_list_absent_without_records():
    from s_export import build_sdat
    assert "SURFLIST" not in build_sdat(_model(), _props())


def test_ocsv_parts_matches_manual_grammar():
    """LABEL / NCTMG(1:L) / NPRT / PRT list / ITYPE / LVAR, PRT numbers
    are the 1-based PARTS positions."""
    from s_export import build_sdat
    m = _model()
    m.add_part(name="aa", kind="cube", attribute="solid")
    m.add_part(name="bb", kind="cube", attribute="solid")
    m.add_part(name="cc", kind="cube", attribute="solid")
    _set(m, "ocsv_parts", "aa|cc")
    _set(m, "lfile_ocsv_label", "ocsv")
    _set(m, "lfile_ocsv_itype", "2")
    _set(m, "lfile_ocsv_lvar", "TEMP")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("OCSV_PARTS")
    # sorted selection: aa(1), cc(3)
    assert lines[i:i + 7] == [
        "OCSV_PARTS",
        "ocsv",
        f"{1:12d}:L",
        f"{2:12d}",
        f"{1:12d}",
        f"{3:12d}",
        f"{2:12d}",
    ]
    assert lines[i + 7] == "   TEMP"
    assert lines[i + 8] == "/"


def test_ocsv_parts_absent_without_selection():
    from s_export import build_sdat
    assert "OCSV_PARTS" not in build_sdat(_model(), _props())


def test_pcl_restriction_all_five_types():
    from s_export import build_sdat
    m = _model()
    _set(m, "pcl_restriction", ";".join([
        "cuboid|0.0|0.0|0.0|0.1|0.1|0.1",
        "volume_region|Room1",
        "surface_region|InletX|1",
        "calc_time|5.0|20.0",
        "particle_gen_label|3",
    ]))
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("PCL_RESTRICTION")
    block = lines[i:i + 19]
    assert block[:5] == [
        "PCL_RESTRICTION",
        "cuboid",
        f"{0.0:26.14e} {0.0:26.14e} {0.0:26.14e}",
        f"{0.1:26.14e} {0.1:26.14e} {0.1:26.14e}",
        "   /",
    ]
    assert block[5:8] == ["volume_region", "   Room1", "   /"]
    assert block[8:10] == ["surface_region", "   InletX"]
    assert block[10] == "   1"
    assert block[12:14] == [
        "calc_time",
        f"{5.0:26.14e} {20.0:26.14e}",
    ]
    assert block[15:18] == ["particle_gen_label", f"{3:12d}", "   /"]
    assert block[18] == "/"


def test_pcl_restriction_absent_without_records():
    from s_export import build_sdat
    assert "PCL_RESTRICTION" not in build_sdat(_model(), _props())

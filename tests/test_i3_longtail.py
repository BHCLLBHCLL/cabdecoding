"""I3 long tail: 13 scattered commands — TPOR/H2 (region-float family),
WLTY/VFGO (header flags before UNIT), PROP (file family),
STEADY_CHECK/LOOP_OPTION/DYNA_OPTION/LUMI/FOUT_LUMI (keyword-value
cards), UPOS, AENT_POROUS, AIRCON_SET.  Byte-checked against official
samples; POROUS_MEDIA/TCMDL/STHM/LSOL_GENERATE/FANV_REGION/UPOS_SCRIPT
stay deferred (complex sub-record grammars, documented in the audit)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _lines(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def test_region_float_family_tpor_h2():
    """exA17-1b TPOR (porous initial temperature) + exA14-2 H2 (species
    fraction) share the region-float card shape."""
    m = _model()
    m.upsert_value("tpor", "多孔質体T", [("param", "20", None)])
    m.bind_condition("region", "多孔質体", "多孔質体T")
    m.upsert_value("h2", "H2init", [("param", "0.9984", None)])
    m.bind_condition("analysis", "直方体領域", "H2init")
    lines = _lines(m)
    i = lines.index("TPOR")
    assert lines[i:i + 4] == ["TPOR", f"{20.0:29.14e}", "   多孔質体",
                              "   /"]
    j = lines.index("H2")
    assert lines[j:j + 4] == ["H2", f"{0.9984:29.14e}", "   直方体領域",
                              "   /"]


def test_wlty_vfgo_before_unit():
    """exA15-1 WLTY (one 12-wide) + vf-ex2 VFGO (two 12-wide), directly
    before UNIT in the header."""
    m = _model()
    m.set_analysis_set_value("wlty", "1")
    m.set_analysis_set_value("vfgo", "1,0")
    lines = _lines(m)
    i = lines.index("WLTY")
    assert lines[i + 1] == f"{1:12d}"
    j = lines.index("VFGO")
    assert lines[j + 1] == f"{1:12d}{0:12d}"
    assert lines[j + 2] == "UNIT"
    assert lines.index("WLTY") < lines.index("UNIT")


def test_prop_header_file():
    """exA22-1 — PROP filename card in the file family."""
    m = _model()
    aset = m.ensure_analysis_set()
    files = aset.find("file")
    if files is None:
        files = ET.SubElement(aset, "file")
    ET.SubElement(files, "prop").text = "exA22-1.prop"
    lines = _lines(m)
    i = lines.index("PROP")
    assert lines[i + 1] == "exA22-1.prop"
    assert lines[i + 2] == "/"
    assert lines.index("HPT") < i < lines.index("UNIT")


def test_option_keyword_cards():
    """exA26-1a STEADY_CHECK + exA05-2a LOOP_OPTION (15-wide + 26-wide)
    + exA09-4 DYNA_OPTION (4-wide) + exA08-3 LUMI (right-10 + 26-wide)
    + FOUT_LUMI (4+8+12 rows)."""
    m = _model()
    aet = m.ensure_analysis_etc()
    sc = ET.SubElement(aet, "steady_check")
    ET.SubElement(sc, "heatbalance").text = "5,1e-05"
    lo = ET.SubElement(aet, "loop_option")
    ET.SubElement(lo, "hygrothermal").text = "5,1e-04"
    dyna = ET.SubElement(aet, "dyna_option")
    ET.SubElement(dyna, "print_dyna").text = "1"
    ET.SubElement(dyna, "print_dynr").text = "1"
    lumi = ET.SubElement(aet, "lumi")
    ET.SubElement(lumi, "EFSO").text = "120"
    fl = ET.SubElement(aet, "fout_lumi")
    ET.SubElement(fl, "LMCE").text = "0"
    lines = _lines(m)
    i = lines.index("STEADY_CHECK")
    assert lines[i:i + 4] == ["STEADY_CHECK", "heatbalance",
                              f"{5:>15d}{1e-05:26.14e}", "/"]
    j = lines.index("LOOP_OPTION")
    assert lines[j + 2] == f"{5:>15d}{1e-04:26.14e}"
    k = lines.index("DYNA_OPTION")
    assert lines[k:k + 5] == ["DYNA_OPTION", "print_dyna", f"{1:4d}",
                              "print_dynr", f"{1:4d}"]
    l = lines.index("LUMI")
    assert lines[l + 1] == f"{'EFSO':>10}{120.0:26.14e}"
    f = lines.index("FOUT_LUMI")
    assert lines[f + 1] == f"    {'LMCE':<8}{0:>12}"


def test_upos_card():
    """exA16-1 — UPOS filename + kind + single '/'."""
    m = _model()
    out = m.root.find("output")
    if out is None:
        out = ET.SubElement(m.root, "output")
    up = ET.SubElement(out, "upos")
    ET.SubElement(up, "file").text = "exA16-1_avrg.csv"
    ET.SubElement(up, "kind").text = "outlet"
    lines = _lines(m)
    i = lines.index("UPOS")
    assert lines[i:i + 4] == ["UPOS", "exA16-1_avrg.csv", "outlet", "/"]


def test_aent_porous_card():
    """exA17-1b — PMconduction record with 29/26-wide dual values and
    double terminator."""
    m = _model()
    m.upsert_value("aent_porous", "PM熱1", [
        ("kind", "PMconduction", None), ("no", "0", None),
        ("param1", "20", None), ("param2", "0.25", None)])
    m.bind_condition("region", "contact", "PM熱1")
    lines = _lines(m)
    i = lines.index("AENT_POROUS")
    assert lines[i:i + 6] == [
        "AENT_POROUS",
        "PMconduction   0",
        f"{20.0:29.14e}{0.25:26.14e}",
        "   contact",
        "   /",
        "/",
    ]


def test_aircon_set_card():
    """exA02-2a — '   {name}   !{comment}' + region rows + '/'."""
    m = _model()
    m.upsert_value("aircon_set", "_aircon1",
                   [("comment", "エアコン", None)])
    m.bind_condition("region", "吹出口", "_aircon1")
    lines = _lines(m)
    i = lines.index("AIRCON_SET")
    assert lines[i:i + 4] == ["AIRCON_SET", "   _aircon1   !エアコン",
                              "   吹出口", "/"]


def test_absent_without_storage():
    lines = _lines(_model())
    for cmd in ("TPOR", "H2", "WLTY", "VFGO", "PROP", "STEADY_CHECK",
                "LOOP_OPTION", "DYNA_OPTION", "LUMI", "FOUT_LUMI",
                "UPOS", "AENT_POROUS", "AIRCON_SET"):
        assert cmd not in lines, cmd

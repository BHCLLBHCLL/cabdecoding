"""§29 H1e batch — script / global-output / moving-body-init /
region-float family (11 commands), byte-checked against official samples.

Corpus rules verified:
- SCRIPT: 52/52 blocks 'context_start' + blank line + verbatim body +
  bare '/' terminator.
- OPERATION_VAR co-occurs with SCRIPT 12/12; header mode is 0 (10
  files) or 1 (2 files); kinds seen: flux only.
- GOUT_VAR ⇔ GOUT_VAR_CONTROL 8/8.
- MOVB_INIT/MOVB_AENT carry inner '   /' plus outer '/' terminators.
- O2/N2/VOFL/TRT2/TRET share the 29-wide value + 3-space region card.
"""
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


def _build(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def _aet(m):
    return m.ensure_analysis_etc()


def test_script_verbatim_block():
    """exA02-2a.s — SCRIPT / context_start / blank / body / '/'."""
    m = _model()
    ET.SubElement(_aet(m), "script").text = (
        "function _t_ac1_usc(){\n"
        "     var hacq,ma,ea,mw,ew,text1;\n"
        "     hacq = 1000;\n"
        "     return text1;\n"
        "}")
    lines = _build(m)
    i = lines.index("SCRIPT")
    assert lines[i:i + 4] == ["SCRIPT", "context_start", "",
                             "function _t_ac1_usc(){"]
    assert lines[i + 6] == "     return text1;"
    assert lines[i + 7] == "}"
    assert lines[i + 8] == "/"


def test_operation_var_multi_record():
    """exA02-2a.s:148-162 — mode header + ma_suc1/ea_suc1 records (bare
    name, '   flux', '   MASS|ENTL', 15-wide flag, 6-space region,
    '   /'), single '/' closes the section."""
    m = _model()
    ov = ET.SubElement(_aet(m), "operation_vars")
    ov.attrib["mode"] = "0"
    for name, vtype in (("ma_suc1", "MASS"), ("ea_suc1", "ENTL")):
        rec = ET.SubElement(ov, "var")
        rec.attrib.update(name=name, kind="flux", vtype=vtype,
                          flag="1", region="吸込口")
    lines = _build(m)
    i = lines.index("OPERATION_VAR")
    assert lines[i:i + 8] == [
        "OPERATION_VAR",
        f"{0:>15d}",
        "ma_suc1",
        "   flux",
        "   MASS",
        f"{1:>15d}",
        "      吸込口",
        "   /",
    ]
    assert lines[i + 8:i + 14] == [
        "ea_suc1",
        "   flux",
        "   ENTL",
        f"{1:>15d}",
        "      吸込口",
        "   /",
    ]
    assert lines[i + 14] == "/"


def test_gout_var_and_control_pair():
    """exA07-5.s:263-268 — GOUT_VAR '   IRLP' + '/' then
    GOUT_VAR_CONTROL overwrite + 15-wide 0 + '/'; exA27-1a carries two
    var rows."""
    m = _model()
    out = m.root.find("output")
    if out is None:
        out = ET.SubElement(m.root, "output")
    gv = ET.SubElement(out, "gout_var")
    gv.attrib["overwrite"] = "0"
    for v in ("IRLP",):
        ET.SubElement(gv, "var").text = v
    lines = _build(m)
    i = lines.index("GOUT_VAR")
    assert lines[i:i + 3] == ["GOUT_VAR", "   IRLP", "/"]
    j = lines.index("GOUT_VAR_CONTROL")
    assert lines[j:j + 4] == ["GOUT_VAR_CONTROL", "overwrite",
                              f"{0:>15d}", "/"]
    assert i < j


def test_movb_init_and_aent_double_terminator():
    """exA09-2.s:247-252 — MOVB_INIT TEMP + 29-wide 1000 + moving_object
    + '   /' + '/'; MOVB_AENT conduction card shares the shape."""
    m = _model()
    m.upsert_value("body_move", "Move1",
                   [("kind", "rotation", None),
                    ("init_kind", "TEMP", None),
                    ("init_value", "1000", None),
                    ("aent_kind", "conduction", None),
                    ("aent_value", "0", None)])
    lines = _build(m)
    i = lines.index("MOVB_INIT")
    assert lines[i:i + 6] == [
        "MOVB_INIT",
        "TEMP",
        f"{1000.0:29.14e}",
        "   moving_object",
        "   /",
        "/",
    ]
    j = lines.index("MOVB_AENT")
    assert lines[j:j + 6] == [
        "MOVB_AENT",
        "conduction",
        f"{0.0:29.14e}",
        "   moving_object",
        "   /",
        "/",
    ]


def test_region_float_family_o2_n2():
    """exA14-3.s — O2/N2 initial mole fractions per region (29-wide
    value + 3-space region + '   /')."""
    m = _model()
    m.upsert_value("o2", "O2init", [("param", "0.23184", None)])
    m.bind_condition("analysis", "直方体領域", "O2init")
    m.upsert_value("n2", "N2init", [("param", "0.76816", None)])
    m.bind_condition("analysis", "直方体領域", "N2init")
    lines = _build(m)
    i = lines.index("O2")
    assert lines[i:i + 4] == ["O2", f"{0.23184:29.14e}",
                              "   直方体領域", "   /"]
    j = lines.index("N2")
    assert lines[j:j + 4] == ["N2", f"{0.76816:29.14e}",
                              "   直方体領域", "   /"]


def test_region_float_family_vofl_trt2_tret():
    """exA10-1 VOFL (liquid fraction), exB16b TRT2/TRET (radiation
    relaxation times) — same card shape, one block per bound region."""
    m = _model()
    m.upsert_value("vofl", "VOFL1", [("param", "1.0", None)])
    m.bind_condition("region", "Cylinder1", "VOFL1")
    m.upsert_value("trt2", "TRT2暖気", [("param", "0.01", None)])
    m.bind_condition("region", "暖気領域", "TRT2暖気")
    m.upsert_value("tret", "TRET暖気", [("param", "0.04113", None)])
    m.bind_condition("region", "暖気領域", "TRET暖気")
    lines = _build(m)
    i = lines.index("VOFL")
    assert lines[i:i + 4] == ["VOFL", f"{1.0:29.14e}",
                              "   Cylinder1", "   /"]
    j = lines.index("TRT2")
    assert lines[j:j + 4] == ["TRT2", f"{0.01:29.14e}",
                              "   暖気領域", "   /"]
    k = lines.index("TRET")
    assert lines[k:k + 4] == ["TRET", f"{0.04113:29.14e}",
                              "   暖気領域", "   /"]


def test_all_absent_without_storage():
    lines = _build(_model())
    for cmd in ("SCRIPT", "OPERATION_VAR", "GOUT_VAR", "GOUT_VAR_CONTROL",
                "MOVB_INIT", "MOVB_AENT", "O2", "N2", "VOFL", "TRT2",
                "TRET"):
        assert cmd not in lines, cmd


def test_ex4e_golden_zero_leak():
    from cab_container import CabArchive
    from cabxml import parse_stpre
    from s_export import build_sdat
    arch = CabArchive.parse(open("tests/ex4_e.cab", "rb").read())
    members = {mm.name: mm for mm in arch.fill_member_data()}
    m = StpreModel(parse_stpre(members["ex4_e.xml"].data))
    props = PropertyModel(parse_property(new_property_bytes()))
    s = build_sdat(m, props)
    for cmd in ("SCRIPT", "OPERATION_VAR", "GOUT_VAR", "MOVB_INIT",
                "MOVB_AENT", "VOFL", "TRT2", "TRET"):
        assert f"\r\n{cmd}\r\n" not in s, cmd

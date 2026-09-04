"""§29 H1b batch — corpus-frequency solver commands (11 cards).

Every assertion is byte-checked against the official sample named in
the docstring: RI/TM header (exA05-2a / exA09-2), CYLD (exA04-1),
LESM/PCTY (exB18), JFNK (exA28-1_step1), WALL_MODEL (exA02-3),
RHUM (exA05-2a), LES_INIT (exB18), AHSO_REGION (exA15-7),
MOVB_AMOM (exA09-3a).
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


def _set_file(m, tag, text):
    aset = m.ensure_analysis_set()
    files = aset.find("file")
    if files is None:
        files = ET.SubElement(aset, "file")
    el = files.find(tag)
    if el is None:
        el = ET.SubElement(files, tag)
    el.text = text


def test_header_ri_before_ro():
    """exA05-2a.s:8-9 — RI + restart file sits between the project name
    and RO."""
    lines = _build(_model())
    assert "RI" not in lines  # absent without storage
    m = _model()
    _set_file(m, "ri", "exA05-2.r")
    lines = _build(m)
    assert lines[lines.index("RI") + 1] == "exA05-2.r"
    assert lines.index("POST") < lines.index("exA05-2.r") - 1
    assert lines.index("RI") < lines.index("RO")


def test_header_tm_not_storage_driven():
    """Official corpus: TM/TMSR co-occur 18/18 with zero exceptions, and
    ex4_e stores a tm filename yet its golden .s has no TM card — TM is
    condition-driven (TMSR, H1c output family), never emitted from the
    file/tm name alone."""
    m = _model()
    _set_file(m, "tm", "exA09-2_tm.csv")
    lines = _build(m)
    assert "TM" not in lines


def test_cyld_before_equa():
    """exA04-1.s — CYLD '1 1' (two 12-wide ints) precedes EQUA."""
    m = _model()
    m.set_analysis_set_value("cyl_coord", "1,1")
    lines = _build(m)
    assert lines[lines.index("CYLD") + 1] == f"{1:12d}{1:12d}"
    assert lines.index("CYLD") < lines.index("EQUA")


def test_lesm_before_equa():
    """exB18.s:20-22 — LESM '2' then '5 5' (15-wide, 15+12-wide)."""
    m = _model()
    m.set_analysis_set_value("lesm", "2,5,5")
    lines = _build(m)
    i = lines.index("LESM")
    assert lines[i + 1] == f"{2:>15d}"
    assert lines[i + 2] == f"{5:>15d}{5:12d}"
    assert lines.index("LESM") < lines.index("EQUA")


def test_pcty_after_equa():
    """exB18.s:23-24 — PCTY 3 (12-wide) sits between EQUA and the
    cycle command."""
    m = _model()
    m.set_analysis_set_value("pcty", "3")
    lines = _build(m)
    assert lines[lines.index("PCTY") + 1] == f"{3:12d}"
    assert lines.index("EQUA") < lines.index("PCTY") < lines.index("CYCS")


def test_jfnk_after_equa_bare_int():
    """exA28-1_step1.s:17-18 — JFNK data line is a bare unpadded int."""
    m = _model()
    m.set_analysis_set_value("jfnk", "10")
    lines = _build(m)
    assert lines[lines.index("JFNK") + 1] == "10"
    assert lines.index("EQUA") < lines.index("JFNK")


def test_wall_model_before_gogo():
    """exA02-3.s:334-335 — WALL_MODEL 2 (15-wide) directly precedes
    GOGO."""
    m = _model()
    m.set_analysis_set_value("wall_model", "2")
    lines = _build(m)
    i = lines.index("WALL_MODEL")
    assert lines[i + 1] == f"{2:>15d}"
    assert lines[i + 2] == "GOGO"


def test_rhum_init_region_fluid_and_solid():
    """exA05-2a.s:193-224 — fluid-side RHUM blocks precede the initial
    TEMP, solid-side RHUM blocks follow the solid TEMP block; card is
    29-wide value + 3-space region + '   /'."""
    m = _model()
    m.upsert_value("init_humidity", "初期湿度1",
                   [("param", "0.66", None)])
    m.bind_condition("analysis", "直方体領域", "初期湿度1")
    m.upsert_value("init_humidity", "初期湿度2",
                   [("param", "0.66", None)])
    m.bind_condition("parts", "外装材", "初期湿度2")
    lines = _build(m)
    start = lines.index("INIT_REGION")
    temp1 = lines.index("TEMP", start)
    assert lines[start:start + 4] == [
        "INIT_REGION",
        "RHUM",
        f"{0.66:29.14e}",
        "   直方体領域",
    ]
    assert lines[temp1 - 1] == "   /"  # RHUM block closed before TEMP
    # solid-side block: after the solid TEMP region list, before the
    # INIT_REGION terminator
    end = lines.index("/", temp1 + 4)  # first bare '/' after solid TEMP
    solid_start = lines.index("RHUM", temp1 + 4)
    assert lines[solid_start:solid_start + 3] == [
        "RHUM",
        f"{0.66:29.14e}",
        "   外装材",
    ]
    assert solid_start < end


def test_les_init_block():
    """exB18.s:127-132 — LES_INIT 'random  ! 条件7' + 29/26/26-wide
    scales + driver region + inner/outer terminators."""
    m = _model()
    aet = m.ensure_analysis_etc()
    li = ET.SubElement(aet, "les_init")
    for tag, text in (("method", "random"), ("name", "条件7"),
                      ("r1", "1.0"), ("r2", "3.0"), ("r3", "3.0"),
                      ("region", "ドライバー領域")):
        ET.SubElement(li, tag).text = text
    lines = _build(m)
    i = lines.index("LES_INIT")
    assert lines[i:i + 5] == [
        "LES_INIT",
        "random  ! 条件7",
        f"{1.0:29.14e}{3.0:26.14e}{3.0:26.14e}",
        "   ドライバー領域",
        "   /",
    ]
    assert lines[i + 5] == "/"


def test_les_init_absent_without_storage():
    assert "LES_INIT" not in _build(_model())


def test_ahso_region_matches_official_bytes():
    """exA15-7.s:221-226 — AHSO_REGION 面発熱1: value line is 26-wide
    float + 12-wide kind 2 (VENT_REGION's volume variant is 29 + '   2')."""
    m = _model()
    m.upsert_value("area_heat_source", "面発熱1",
                   [("source", "3000", "W")])
    m.bind_condition("region", "Bottom_", "面発熱1")
    lines = _build(m)
    i = lines.index("AHSO_REGION")
    assert lines[i:i + 5] == [
        "AHSO_REGION",
        "source    0   ! 面発熱1",
        f"{3000.0:26.14e}{2:12d}",
        "   Bottom_",
        "   /",
    ]
    assert lines[i + 5] == "/"


def test_ahso_absent_without_storage():
    m = _model()
    # volume heat source only -> VENT_REGION, never AHSO_REGION
    m.upsert_value("heat_source", "体積発熱1", [("source", "20", "W")])
    m.bind_condition("parts", "Heater", "体積発熱1")
    lines = _build(m)
    assert "AHSO_REGION" not in lines
    assert "VENT_REGION" in lines


def test_movb_amom_noslip():
    """exA09-3a.s:243-247 — MOVB_AMOM noslip + moving_object list with
    inner/outer terminators; one block regardless of value count."""
    m = _model()
    m.upsert_value("body_move", "Move1",
                   [("kind", "rotation", None),
                    ("amom_noslip", "1", None)])
    lines = _build(m)
    i = lines.index("MOVB_AMOM")
    assert lines[i:i + 5] == [
        "MOVB_AMOM",
        "noslip",
        "   moving_object",
        "   /",
        "/",
    ]
    assert lines.count("MOVB_AMOM") == 1


def test_movb_amom_absent_without_storage():
    assert "MOVB_AMOM" not in _build(_model())


def test_ex4e_golden_parity_untouched():
    """None of the H1b storage is present in the ex4_e fixture — its
    render must stay byte-identical (structural parity guard)."""
    from cab_container import CabArchive
    from cabxml import parse_stpre
    from s_export import build_sdat
    arch = CabArchive.parse(open("tests/ex4_e.cab", "rb").read())
    members = {mm.name: mm for mm in arch.fill_member_data()}
    m = StpreModel(parse_stpre(members["ex4_e.xml"].data))
    props = PropertyModel(parse_property(new_property_bytes()))
    s = build_sdat(m, props)
    for cmd in ("RI", "CYLD", "LESM", "PCTY", "JFNK", "WALL_MODEL",
                "RHUM", "LES_INIT", "AHSO_REGION", "MOVB_AMOM"):
        assert f"\r\n{cmd}\r\n" not in s, cmd

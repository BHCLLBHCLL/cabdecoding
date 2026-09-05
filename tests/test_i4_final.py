"""I4-final: the six deferred subsystem cards — UPOS_SCRIPT (verbatim
script wrapper), LSOL_GENERATE (five sub-records), TCMDL (thermal
network nodes/branches), STHM (NASA polynomials, verbatim),
POROUS_MEDIA (heterogeneous rows verbatim + structured tail),
FANV_REGION (axial-fan region with @T: table reference)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _lines(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def test_upos_script_verbatim():
    """exA26-2 — UPOS_SCRIPT '#' + SCRIPT wrapper around the verbatim
    body, context_start/context_end + '/'."""
    m = _model()
    out = m.root.find("output")
    if out is None:
        out = __import__("xml.etree.ElementTree",
                         fromlist=["SubElement"]).SubElement(m.root,
                                                             "output")
    from xml.etree import ElementTree as ET
    us = ET.SubElement(out, "upos_script")
    us.text = "var FireDuration = 1200;\n\nfunction sc1()\n{\n}"
    lines = _lines(m)
    i = lines.index("UPOS_SCRIPT")
    assert lines[i:i + 5] == ["UPOS_SCRIPT", "#", "SCRIPT",
                              "context_start",
                              "var FireDuration = 1200;"]
    assert "context_end" in lines
    assert lines[lines.index("context_end") + 1] == "/"


def test_lsol_generate_subrecords():
    """exA07-4 — generator name + property/shape/position/timing/
    condition records with exact widths."""
    m = _model()
    m.ensure_analysis_etc_section("lsol_generate")
    el = m.root.find("analysis_etc/lsol_generate")
    el.attrib.update(
        name="pcle1", pno="1", pname="pmat1",
        shape_kind="sphere", shape_size="0.01",
        pos_kind="cuboid",
        pos_p1="0.25,0,1.1", pos_p2="0.75,0.01,1.3",
        pos_n="40,1,15", pos_flag="0",
        timing_kind="cycle", timing_t="1,99999,99999",
        cond_kind="velocity_random", cond_vals="0.05,0,0.05")
    lines = _lines(m)
    i = lines.index("LSOL_GENERATE")
    assert lines[i:i + 8] == [
        "LSOL_GENERATE",
        "pcle1",
        " property",
        f"{1:12d}      ! pmat1",
        " shape",
        "      sphere",
        f"{0.01:29.14e}",
        " position",
    ]
    assert lines[i + 9] == (
        f"{0.25:29.14e}{0.0:26.14e}{1.1:26.14e}")
    assert lines[i + 11] == f"{40:12d}{1:12d}{15:12d}"
    assert lines[i + 14] == "   cycle"
    assert lines[i + 15] == f"{1:12d}{99999:12d}{99999:12d}"
    assert lines[i + 18] == f"{0.05:29.14e}{0.0:26.14e}{0.05:26.14e}"
    assert lines[i + 19] == "   /"


def test_tcmdl_network():
    """exA22-1 — index + name + J/T/B/S node records + branch table
    (non-terminated)."""
    m = _model()
    m.ensure_analysis_etc_section("tcmdl")
    el = m.root.find("analysis_etc/tcmdl")
    el.attrib.update(index="1", name="熱回路網モデル1")
    from xml.etree import ElementTree as ET
    ET.SubElement(el, "node").attrib.update(
        kind="J", params="0,1,20")
    for kind, nm in (("T", "_熱回路網モデル1_T"), ("B", "_熱回路網モデル1_B"),
                     ("S", "_熱回路網モデル1_S")):
        ET.SubElement(el, "node").attrib.update(
            kind=kind, params="0,0,20", name=nm, flag="1")
    for a, b, v in (("J", "T", "10"), ("J", "B", "5"), ("T", "S", "0.1")):
        ET.SubElement(el, "branch").attrib.update(a=a, b=b, value=v)
    lines = _lines(m)
    i = lines.index("TCMDL")
    assert lines[i + 1] == f"{1:12d}"
    assert lines[i + 2] == "   熱回路網モデル1"
    assert lines[i + 3] == f"{4:12d}"
    assert lines[i + 4] == "   J"
    assert lines[i + 5] == (
        "      " + f"{0.0:26.14e}{1.0:26.14e}{20.0:26.14e}")
    assert lines[i + 6] == "   T"
    assert lines[i + 7] == (
        "      " + f"{0.0:26.14e}{0.0:26.14e}{20.0:26.14e}"
        + f"{1:12d}")
    assert lines[i + 8] == "      _熱回路網モデル1_T"
    assert lines[i + 15] == f"{3:12d}"
    assert lines[i + 16] == (
        "      J" + f"{'T':>13}" + f"{10.0:>38.14e}")
    assert lines[i + 18] == (
        "      T" + f"{'S':>13}" + f"{0.1:>38.14e}")


def test_sthm_verbatim():
    """exA14-3 — NASA polynomial rows pass through byte-exact."""
    m = _model()
    m.ensure_analysis_etc_section("sthm")
    el = m.root.find("analysis_etc/sthm")
    el.attrib["lines"] = "|".join((
        "   5   2",
        "   2  NONE  : H2",
        f"{300.0:29.14e}{1000.0:26.14e}",
        f"{3.298124:26.14e}{8.249441e-4:26.14e}",
    ))
    lines = _lines(m)
    i = lines.index("STHM")
    assert lines[i + 1] == "   5   2"
    assert lines[i + 2] == "   2  NONE  : H2"
    assert lines[i + 3] == f"{300.0:29.14e}{1000.0:26.14e}"


def test_porous_media_card():
    """exA17-1b — kind header + verbatim rows + tail + region + double
    terminator."""
    m = _model()
    m.ensure_analysis_etc_section("porous_media")
    el = m.root.find("analysis_etc/porous_media")
    el.attrib.update(kind="anisotropic", no="0",
                     rows="|".join((
                         f"{8390.0:29.14e}{375.0:26.14e}"
                         f"{123.0:26.14e}{0.9:26.14e}",
                         f"{0.75:29.14e}{250.0:26.14e}")),
                     tail_v="1", tail_f="0", region="多孔質体")
    lines = _lines(m)
    i = lines.index("POROUS_MEDIA")
    assert lines[i:i + 3] == [
        "POROUS_MEDIA",
        "anisotropic   0",
        f"{8390.0:29.14e}{375.0:26.14e}{123.0:26.14e}{0.9:26.14e}",
    ]
    assert lines[i + 4] == f"{1:>15d}{0.0:26.14e}"
    assert lines[i + 5] == "   多孔質体"
    assert lines[i + 6] == "   /"
    assert lines[i + 7] == "/"


def test_fanv_region_card():
    """exA13-1 — axial_fan header + values + @T:fanpq table reference +
    multiple region records."""
    m = _model()
    m.ensure_analysis_etc_section("fanv_region")
    el = m.root.find("analysis_etc/fanv_region")
    el.attrib.update(
        kind="axial_fan", no="0", name="ファン1",
        v12="0.098,0.27",
        v6="0,0,0,1,0,0", flag="2", table_ref="@T:fanpq",
        t3="3,3,0", t1="3", t4="1000,70,1",
        regions="軸流ファン,軸流ファン_inlet")
    lines = _lines(m)
    i = lines.index("FANV_REGION")
    assert lines[i:i + 3] == [
        "FANV_REGION",
        "axial_fan   0  ! ファン1",
        f"{0.098:29.14e}{0.27:26.14e}",
    ]
    assert lines[i + 4] == f"{2:12d}"
    assert lines[i + 5] == "   @T:fanpq"
    assert lines[i + 6] == f"{3:>15d}{3:>15d}{0.0:26.14e}"
    assert lines[i + 8] == f"{1000.0:29.14e}{70.0:26.14e}{1.0:26.14e}"
    assert lines[i + 9] == "   軸流ファン"
    assert lines[i + 10] == "   /"
    assert lines[i + 11] == "   軸流ファン_inlet"
    assert lines[i + 13] == "/"


def test_all_absent_without_storage():
    lines = _lines(_model())
    for cmd in ("UPOS_SCRIPT", "LSOL_GENERATE", "TCMDL", "STHM",
                "POROUS_MEDIA", "FANV_REGION"):
        assert cmd not in lines, cmd

"""§29 H1c batch — output-monitor family (TM/SUFL/TMSR/SURF_OUTPUT/
GOUT_AVRG), byte-checked against official samples.

Corpus rules verified across all 295 samples:
- TM ⇔ TMSR co-occur 18/18; SUFL ⇔ SURF_OUTPUT co-occur 20/20
  (zero exceptions); ex4_e stores tm/sufl filenames yet its golden .s
  has neither card — filename storage alone never emits.
- TMSR cycle header is '    1:L    0' in all 18 samples.
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


def _output_el(m):
    out = m.root.find("output")
    if out is None:
        out = ET.SubElement(m.root, "output")
    return out


def _add_point(parent, name, vals, var="TEMP"):
    pt = ET.SubElement(parent, "point")
    if name:
        ET.SubElement(pt, "name").text = name
    for i, v in enumerate(vals, 1):
        ET.SubElement(pt, f"v{i}").text = str(v)
    ET.SubElement(pt, "var").text = var
    return pt


def test_tmsr_block_and_tm_header_pair():
    """exA09-2.s:253-258 — TMSR '    1:L    0' + P1/P2 point records
    (29/26/26-wide coords, '   TEMP', '   /'), and the TM header card
    between RO and VF."""
    m = _model()
    tmsr = ET.SubElement(_output_el(m), "tmsr")
    _add_point(tmsr, "P1", (1.0, 0.2, 0.7))
    _add_point(tmsr, "P2", (2.0, 0.2, 0.7))
    lines = _build(m)
    i = lines.index("TMSR")
    assert lines[i:i + 5] == [
        "TMSR",
        "    1:L    0",
        f"    P1{1.0:29.14e}{0.2:26.14e}{0.7:26.14e}",
        "   TEMP",
        "   /",
    ]
    assert lines[i + 5:i + 8] == [
        f"    P2{2.0:29.14e}{0.2:26.14e}{0.7:26.14e}",
        "   TEMP",
        "   /",
    ]
    assert lines[i + 8] == "/"
    # TM header pair, project-derived filename
    assert lines[lines.index("TM") + 1] == "T_tm.csv"
    assert lines.index("RO") < lines.index("TM") < lines.index("VF")


def test_tm_uses_stored_filename():
    m = _model()
    tmsr = ET.SubElement(_output_el(m), "tmsr")
    _add_point(tmsr, "P1", (1.0, 0.2, 0.7))
    aset = m.ensure_analysis_set()
    files = ET.SubElement(aset, "file")
    ET.SubElement(files, "tm").text = "exA09-2_tm.csv"
    lines = _build(m)
    assert lines[lines.index("TM") + 1] == "exA09-2_tm.csv"


def test_tm_absent_from_filename_storage_alone():
    """ex4_e rule: file/tm stored (ex4_e_tm.csv) with no TMSR condition
    -> no TM card, golden .s parity."""
    m = _model()
    aset = m.ensure_analysis_set()
    files = ET.SubElement(aset, "file")
    ET.SubElement(files, "tm").text = "ex4_e_tm.csv"
    assert "TM" not in _build(m)


def test_surf_output_and_sufl_pair():
    """exB13.s:10-12 (SUFL) + :129-134 (SURF_OUTPUT) — keyword,
    15/12-wide mode row, 29/26/26/26-wide point row + '   level1',
    '   /' + '/' terminators; SUFL header after RO."""
    m = _model()
    so = ET.SubElement(_output_el(m), "surf_output")
    ET.SubElement(so, "mode").text = "1,2"
    pt = ET.SubElement(so, "point")
    ET.SubElement(pt, "name").text = "level1"
    for i, v in enumerate((0.0, 0.0, 0.5, 4.0), 1):
        ET.SubElement(pt, f"v{i}").text = str(v)
    lines = _build(m)
    i = lines.index("SURF_OUTPUT")
    assert lines[i:i + 6] == [
        "SURF_OUTPUT",
        "surfacelevel_tm",
        f"{1:>15d}{2:12d}",
        f"{0.0:29.14e}{0.0:26.14e}{0.5:26.14e}{4.0:26.14e}   level1",
        "   /",
        "/",
    ]
    assert lines[lines.index("SUFL") + 1] == "T_sufl_tm.csv"
    assert lines.index("RO") < lines.index("SUFL") < lines.index("VF")


def test_surf_output_multimode_two_points():
    """exB14a.s — mode '2,2' with two point rows (10-row exB15a shares
    the same header shape)."""
    m = _model()
    so = ET.SubElement(_output_el(m), "surf_output")
    ET.SubElement(so, "mode").text = "2,2"
    for name, v1 in (("P1", 1e-3), ("P2", 0.999)):
        pt = ET.SubElement(so, "point")
        ET.SubElement(pt, "name").text = name
        for i, v in enumerate((v1, 0.0, 0.05, 1.0), 1):
            ET.SubElement(pt, f"v{i}").text = str(v)
    lines = _build(m)
    i = lines.index("SURF_OUTPUT")
    assert lines[i + 2] == f"{2:>15d}{2:12d}"
    assert lines[i + 3] == (
        f"{1e-3:29.14e}{0.0:26.14e}{0.05:26.14e}{1.0:26.14e}   P1")
    assert lines[i + 4] == (
        f"{0.999:29.14e}{0.0:26.14e}{0.05:26.14e}{1.0:26.14e}   P2")
    assert lines[i + 5] == "   /" and lines[i + 6] == "/"


def test_gout_avrg_nested_meix_var():
    """exB19a.s — GOUT_AVRG 15-wide enable + '010' option code + nested
    MEIX_VAR (4×12-wide header + 4-space var rows) + single '/'."""
    m = _model()
    g = ET.SubElement(_output_el(m), "gout_avrg")
    ET.SubElement(g, "enable").text = "1"
    ET.SubElement(g, "code").text = "010"
    ET.SubElement(g, "cycle").text = "1"
    ET.SubElement(g, "kind").text = "1,1,2"
    for v in ("UNOR", "VNOR", "WNOR", "PRES", "TEMP"):
        ET.SubElement(g, "var").text = v
    lines = _build(m)
    i = lines.index("GOUT_AVRG")
    assert lines[i:i + 11] == [
        "GOUT_AVRG",
        f"{1:>15d}",
        "010",
        "MEIX_VAR",
        f"{1:12d}{1:12d}{1:12d}{2:12d}",
        "    UNOR",
        "    VNOR",
        "    WNOR",
        "    PRES",
        "    TEMP",
        "/",
    ]


def test_gout_avrg_exb18_shape():
    """exB18.s — code '000', vars UNOR/VNOR/WNOR/PRES/EVIS."""
    m = _model()
    g = ET.SubElement(_output_el(m), "gout_avrg")
    ET.SubElement(g, "enable").text = "1"
    ET.SubElement(g, "code").text = "000"
    for v in ("UNOR", "VNOR", "WNOR", "PRES", "EVIS"):
        ET.SubElement(g, "var").text = v
    lines = _build(m)
    i = lines.index("GOUT_AVRG")
    assert lines[i + 2] == "000"
    assert lines[i + 9] == "    EVIS"
    assert lines[i + 10] == "/"


def test_output_family_absent_without_storage():
    lines = _build(_model())
    for cmd in ("TM", "SUFL", "TMSR", "SURF_OUTPUT", "GOUT_AVRG"):
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
    for cmd in ("TMSR", "SURF_OUTPUT", "GOUT_AVRG"):
        assert f"\r\n{cmd}\r\n" not in s, cmd
    for token in ("\r\nTM\r\n", "\r\nSUFL\r\n"):
        assert token not in s, token

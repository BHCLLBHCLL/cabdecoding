"""§29 H1f batch — phase-change (PCM) and radiation solver family
(PHASE_TRANSITION / RADD / RADC_MATERIAL / RADB_REGION), byte-checked
against official samples exA15-4a and exA01-1.

ex4_e carries <radiation type='vf'> with solver params but neither a
<radd>/<radc_material>/<radb_region> subtree nor a pcm value — golden
parity stays intact.
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


def _rad(m):
    return m.set_radiation_type("vf") and m.radiation_element()


def test_phase_transition_official_card():
    """exA15-4a.s — fixed keyword structure with 29/26/26/26 and
    29/26/26 value rows."""
    m = _model()
    m.upsert_value("pcm", "PCM_default", [
        ("melting_temp", "232.95", "C"),
        ("latent_heat", "60600", "J/kg"),
    ])
    lines = _build(m)
    i = lines.index("PHASE_TRANSITION")
    assert lines[i:i + 8] == [
        "PHASE_TRANSITION",
        "solidification_melting",
        "phase_diagram",
        "constant_melt",
        f"{232.95:29.14e}{232.95:26.14e}{60600.0:26.14e}{0.6:26.14e}",
        "solid_property",
        f"{7170.0:29.14e}{228.0:26.14e}{66.6:26.14e}",
        "conservation",
    ]
    assert lines[i + 8] == f"{2:>15d}"
    assert lines[i + 9:i + 13] == ["phase_function", "linear",
                                   "solid_resistance", "darcy"]
    assert lines[i + 13] == f"{1e-10:26.14e}"
    assert lines[i + 14] == "/"


def test_phase_transition_uses_cw_defaults():
    """CW PCM page writes only melting_temp/latent_heat — the rest of
    the card comes from exA15-4a sample defaults."""
    m = _model()
    m.upsert_value("pcm", "PCM_default", [
        ("melting_temp", "28", "C"),
        ("latent_heat", "200000", "J/kg"),
    ])
    lines = _build(m)
    i = lines.index("PHASE_TRANSITION")
    assert lines[i + 4] == (
        f"{28.0:29.14e}{28.0:26.14e}{200000.0:26.14e}{0.6:26.14e}")


def test_phase_transition_absent_without_pcm():
    assert "PHASE_TRANSITION" not in _build(_model())


def test_radd_keyword_table():
    """exA01-1.s — RADD keyword rows (ints right-justified width 8,
    floats %.5e width 15), '/' terminated; optional NPRQ emitted only
    when stored."""
    m = _model()
    rad = _rad(m)
    radd = ET.SubElement(rad, "radd")
    for kw, v in (("MTDSR", "4"), ("ITRSR", "5"), ("EQCSR", "1e-4"),
                  ("UNDSR", "1.0"), ("ITRR", "2"), ("REPS", "1e-3"),
                  ("INRD", "0"), ("MTCR", "1"), ("NPRQ", "10")):
        ET.SubElement(radd, kw).text = v
    lines = _build(m)
    i = lines.index("RADD")
    assert lines[i:i + 10] == [
        "RADD",
        "   MTDSR       4",
        "   ITRSR       5",
        "   EQCSR    1.00000e-04",
        "   UNDSR    1.00000e+00",
        "   ITRR        2",
        "   REPS     1.00000e-03",
        "   INRD        0",
        "   MTCR        1",
        "   NPRQ       10",
    ]
    assert lines[i + 10] == "/"


def test_radd_omits_absent_keywords():
    """exA09-3c.s — no NPRQ row when not stored."""
    m = _model()
    rad = _rad(m)
    radd = ET.SubElement(rad, "radd")
    for kw, v in (("MTDSR", "4"), ("MTCR", "1")):
        ET.SubElement(radd, kw).text = v
    lines = _build(m)
    i = lines.index("RADD")
    assert lines[i + 1] == "   MTDSR       4"
    assert lines[i + 2] == "   MTCR        1"
    assert lines[i + 3] == "/"


def test_radc_material_rows():
    """exA01-1.s — per-material rows: 12-wide no + 3×26-wide values."""
    m = _model()
    rad = _rad(m)
    radc = ET.SubElement(rad, "radc_material")
    for no, v1 in (("1", "-1.0"), ("2", "0.9")):
        r = ET.SubElement(radc, "row")
        r.attrib.update(no=no, v1=v1, v2="0.0", v3="0.0")
    lines = _build(m)
    i = lines.index("RADC_MATERIAL")
    assert lines[i:i + 3] == [
        "RADC_MATERIAL",
        f"{1:12d}{-1.0:26.14e}{0.0:26.14e}{0.0:26.14e}",
        f"{2:12d}{0.9:26.14e}{0.0:26.14e}{0.0:26.14e}",
    ]
    assert lines[i + 3] == "/"


def test_radb_region_mirror_records():
    """exA01-1.s — mirror boundary records '{kind:<6}    {no}   ! {name}'
    + region + '   /', outer '/'."""
    m = _model()
    rad = _rad(m)
    radb = ET.SubElement(rad, "radb_region")
    rec = ET.SubElement(radb, "record")
    rec.attrib.update(kind="mirror", no="0", name="対称面1",
                      region="Ymax面")
    lines = _build(m)
    i = lines.index("RADB_REGION")
    assert lines[i:i + 4] == [
        "RADB_REGION",
        "mirror    0   ! 対称面1",
        "   Ymax面",
        "   /",
    ]
    assert lines[i + 4] == "/"


def test_radiation_sections_absent_in_ex4e_shape():
    """ex4_e has <radiation type='vf'> but no radd/radc/radb subtrees —
    nothing emits (golden parity guard)."""
    m = _model()
    _rad(m)
    lines = _build(m)
    for cmd in ("RADD", "RADC_MATERIAL", "RADB_REGION",
                "PHASE_TRANSITION"):
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
    for cmd in ("PHASE_TRANSITION", "RADD", "RADC_MATERIAL",
                "RADB_REGION"):
        assert f"\r\n{cmd}\r\n" not in s, cmd

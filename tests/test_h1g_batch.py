"""§29 H1g batch — chemical reaction, electric-current and solar
subsystems (SNAM / CDIF / REAC_REGION / VDFU_REGION / ECUR /
ECUR_MAGFIELD / ECUR_PROPERTY / SOLAR / SOLA_DEFAULT / SOLA_REGION),
byte-checked against official samples exA04-1, exA03-1, exA12-1,
exA08-1 and exA07-5.

Corpus structure rules:
- SNAM is a non-terminated header block between GRAV and HSOL, rows
  '   {name:<16}' for the fixed R1/R2/P1/P2 registers.
- VDFU_REGION: repeated species line + source record per row, single
  '/' terminator (CN01 is a data line, not a command).
- SOLA_REGION is independent of the SOLAR+SOLA_DEFAULT head (corpus
  10 vs 6/6 co-occurrence; exA07-5 has regions but no head).
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


def test_snam_header_position():
    """exA04-1:26-32 — SNAM sits after GRAV, before HSOL; rows are
    name left-justified width 16 with 3-space prefix."""
    m = _model()
    m.set_analysis_set_value("heat", "1")
    chem = ET.SubElement(_aet(m), "chem")
    sn = ET.SubElement(chem, "snam")
    sn.attrib.update(r1="R1", r2="R2", p1="P1", p2="P2")
    lines = _build(m)
    i = lines.index("SNAM")
    assert lines[i:i + 5] == [
        "SNAM",
        "   R1              ",
        "   R2              ",
        "   P1              ",
        "   P2              ",
    ]
    assert lines.index("GRAV") < i < lines.index("HSOL")


def test_chem_cdif_reac_vdfu_group():
    """exA04-1:165-171 (REAC) + exA03-1:137-151 (CDIF/VDFU)."""
    m = _model()
    chem = ET.SubElement(_aet(m), "chem")
    d = ET.SubElement(chem, "dif")
    d.attrib.update(species="cn1", value="0.0")
    r = ET.SubElement(chem, "reac")
    r.attrib.update(no="1", formula="R1 + 2R2 => P1 + 2P2",
                    a="1.5", b="0", c="0", e="10000", x1="1", x2="2",
                    x3="0", tail="0", region="円柱領域")
    v = ET.SubElement(chem, "vdfu")
    v.attrib.update(species="CN01", name="拡散1", value="3.0",
                    region="煙H")
    lines = _build(m)
    i = lines.index("CDIF")
    assert lines[i + 1] == f"{0.0:29.14e}  ! cn1"
    j = lines.index("REAC_REGION")
    assert lines[j:j + 7] == [
        "REAC_REGION",
        f"{1:>15d}",
        "    R1 + 2R2 => P1 + 2P2",
        f"{1.5:29.14e}{0.0:26.14e}{0.0:26.14e}{10000.0:26.14e}"
        f"{1.0:26.14e}{2.0:26.14e}{0.0:26.14e}  0",
        "   円柱領域",
        "   /",
        "/",
    ]
    k = lines.index("VDFU_REGION")
    assert lines[k:k + 6] == [
        "VDFU_REGION",
        "CN01",
        "source    0   ! 拡散1",
        f"{3.0:29.14e}",
        "   煙H",
        "   /",
    ]
    assert lines[k + 6] == "/"


def test_vdfu_multi_record_single_terminator():
    """exA03-1:139-151 — two records share one VDFU_REGION with a
    single '/' (species line repeated per record)."""
    m = _model()
    chem = ET.SubElement(_aet(m), "chem")
    for name, val, region in (("拡散1", "3.0", "煙H"),
                              ("拡散2", "1.0", "煙L")):
        v = ET.SubElement(chem, "vdfu")
        v.attrib.update(species="CN01", name=name, value=val,
                        region=region)
    lines = _build(m)
    k = lines.index("VDFU_REGION")
    assert lines.count("CN01") == 2
    assert lines[k + 10] == "   /"  # second record terminator
    assert lines[k + 11] == "/"     # single section terminator


def test_ecur_trio():
    """exA12-1:88-96 — ECUR 3×12-wide, ECUR_MAGFIELD '{kind:<10}{no}' +
    '     {region}' + 2×26-wide, ECUR_PROPERTY rows + '/'."""
    m = _model()
    ec = ET.SubElement(_aet(m), "ecur")
    ec.attrib.update(i1="1", i2="0", i3="0", mag_kind="uniform",
                     mag_no="0", mag_region="@S:rbmx", mag_v1="0",
                     mag_v2="0")
    for no, v in (("1", "1e6"), ("2", "1e6")):
        p = ET.SubElement(ec, "prop")
        p.attrib.update(no=no, v=v)
    lines = _build(m)
    i = lines.index("ECUR")
    assert lines[i:i + 8] == [
        "ECUR",
        f"{1:12d}{0:12d}{0:12d}",
        "ECUR_MAGFIELD",
        "uniform   0",
        f"     @S:rbmx{0.0:26.14e}{0.0:26.14e}",
        "ECUR_PROPERTY",
        f"{1:12d}{1e6:26.14e}",
        f"{2:12d}{1e6:26.14e}",
    ]
    assert lines[i + 8] == "/"


def test_ecur_head_only_without_magfield():
    m = _model()
    ec = ET.SubElement(_aet(m), "ecur")
    ec.attrib.update(i1="1", i2="0", i3="0")
    p = ET.SubElement(ec, "prop")
    p.attrib.update(no="1", v="1e6")
    lines = _build(m)
    assert "ECUR_MAGFIELD" not in lines
    i = lines.index("ECUR")
    assert lines[i + 2] == "ECUR_PROPERTY"


def test_solar_head_and_default():
    """exA08-1 — SOLAR fixed card (%11.3f rows, ASHRAE 26-wide,
    12×%11.3f monthly) + SOLA_DEFAULT keyword table (ints right-9,
    floats right-17 %.5e)."""
    m = _model()
    so = ET.SubElement(_aet(m), "solar")
    so.attrib.update(
        mode="latitude_dec", lat="35.680", lon="139.770",
        meridian="135.000", a1="0", a2="0", a3="0", a4="14.000",
        a5="0", ashrae_kind="ASHRAE", ashrae_val="0.1", n1="9", n2="1",
        monthly1="0.392,0.434,0.496,0.534,0.544,0.541,0.510,0.502,"
                 "0.457,0.430,0.415,0.368",
        monthly2="2.323,2.154,1.965,1.862,1.836,1.884,2.021,2.073,"
                 "2.268,2.325,2.333,2.450")
    d = ET.SubElement(so, "default")
    d.attrib.update(IDRF="1", SKY="1.0", GND="0.2", INFO="1",
                    MPCL="20000", MAXM="4000", ASHRAE="2013")
    lines = _build(m)
    i = lines.index("SOLAR")
    assert lines[i:i + 8] == [
        "SOLAR",
        " latitude_dec",
        "     35.680    139.770    135.000",
        "      0.000      0.000",
        "      0.000",
        "     14.000      0.000",
        " ASHRAE      1.00000000000000e-01",
        f"{9:12d}{1:12d}",
    ]
    assert lines[i + 8] == (
        "      0.392      0.434      0.496      0.534      0.544"
        "      0.541      0.510      0.502      0.457      0.430"
        "      0.415      0.368")
    assert lines[i + 9].startswith("      2.323      2.154")
    j = lines.index("SOLA_DEFAULT")
    assert lines[j:j + 8] == [
        "SOLA_DEFAULT",
        "    IDRF        1",
        "    SKY      1.00000e+00",
        "    GND      2.00000e-01",
        "    INFO        1",
        "    MPCL    20000",
        "    MAXM     4000",
        "    ASHRAE     2013",
    ]
    assert lines[j + 8] == "/"


def test_sola_region_independent():
    """exA07-5:226 — SOLA_REGION emits without the SOLAR/SOLA_DEFAULT
    head (corpus 10 vs 6/6); floats %28.14e/%27.14e + '  ! name'."""
    m = _model()
    so = ET.SubElement(_aet(m), "solar")
    rec = ET.SubElement(so, "region")
    rec.attrib.update(kind="body_d", name="吸収体", v1="1.0", v2="0",
                      v3="0", v4="0", flag="0", region="Duct_case")
    lines = _build(m)
    assert "SOLAR" not in lines and "SOLA_DEFAULT" not in lines
    i = lines.index("SOLA_REGION")
    assert lines[i:i + 6] == [
        "SOLA_REGION",
        "body_d",
        f"{1.0:28.14e}{0.0:27.14e}{0.0:27.14e}{0.0:27.14e}  ! 吸収体",
        "   0",
        "   Duct_case",
        "   /",
    ]
    assert lines[i + 6] == "/"


def test_all_absent_without_storage():
    lines = _build(_model())
    for cmd in ("SNAM", "CDIF", "REAC_REGION", "VDFU_REGION", "ECUR",
                "ECUR_MAGFIELD", "ECUR_PROPERTY", "SOLAR",
                "SOLA_DEFAULT", "SOLA_REGION"):
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
    for cmd in ("SNAM", "CDIF", "REAC_REGION", "VDFU_REGION", "ECUR",
                "SOLAR", "SOLA_DEFAULT", "SOLA_REGION"):
        assert f"\r\n{cmd}\r\n" not in s, cmd

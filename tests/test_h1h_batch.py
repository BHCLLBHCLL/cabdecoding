"""§29 H1h batch — scattered low-frequency cards (UPWD / TBEC /
LES_OPTION / TOPOPT / HUMD_CONTROL / HUMC+HUMF_REGION / SURF_1MARS /
SURF_AENT / VFRT_SPC / PBAS_MATERIAL / STMC / TABLE / VMOM_REGION /
VARLIST), byte-checked against official samples.

Samples: exA23-1a (UPWD), exA01-1 (TBEC), exB18 (LES_OPTION),
exA28-1_step2 (TOPOPT), exA05-1 (HUMD/HUMC/HUMF), exA15-3 (SURF_1MARS),
exA15-1 (SURF_AENT), exA02-2a (VFRT_SPC), exA14-1 (PBAS_MATERIAL),
exA23-4 (STMC), exA13-1 (TABLE), exA05-2 (VMOM_REGION), exB02 (VARLIST).
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


def test_upwd_mask_and_tbec_flag():
    """exA23-1a (UPWD 8-digit mask) + exA01-1 (TBEC 12-wide flag)."""
    m = _model()
    m.set_analysis_set_value("upwd_mask", "11000000")
    m.set_analysis_set_value("tbec", "1")
    lines = _build(m)
    assert lines[lines.index("UPWD") + 1] == "11000000"
    assert lines[lines.index("TBEC") + 1] == f"{1:12d}"
    # both live in the header area after EQUA, before the mesh
    assert lines.index("EQUA") < lines.index("UPWD") < lines.index("CXYZ")
    assert lines.index("EQUA") < lines.index("TBEC") < lines.index("CXYZ")


def test_les_option_keyword_table():
    """exB18 — wiggle_sensor/time_integration rows, 15-wide, '/'-closed."""
    m = _model()
    lo = ET.SubElement(_aet(m), "les_option")
    ET.SubElement(lo, "wiggle_sensor").text = "1"
    ET.SubElement(lo, "time_integration").text = "0"
    lines = _build(m)
    i = lines.index("LES_OPTION")
    assert lines[i:i + 5] == ["LES_OPTION", "wiggle_sensor", f"{1:>15d}",
                              "time_integration", f"{0:>15d}"]
    assert lines[i + 5] == "/"


def test_topopt_head_before_region():
    """exA28-1_step2 — TOPOPT head card; region still emitted below."""
    m = _model()
    top = ET.SubElement(_aet(m), "topology_optimize")
    top.attrib.update(penalization="1.5", penalty_flag="1",
                      cons_flag="1", cons_vals="100,100,100")
    m.upsert_value("topo_design_space", "DS1", [
        ("vol_constraint_type", "1", None),
        ("vol_constraint", "0.12", None)])
    m.bind_condition("parts", "Design_space", "DS1")
    m.upsert_value("topo_obj_func", "OF1", [("kind", "volume", None)])
    m.bind_condition("parts", "Design_space", "OF1")
    lines = _build(m)
    i = lines.index("TOPOPT")
    assert lines[i:i + 7] == [
        "TOPOPT",
        "penalization",
        f"{1:>15d}",
        f"{1.5:26.14e}",
        "constrained_optimization",
        f"{1:>15d}",
        f"{100.0:29.14e}{100.0:26.14e}{100.0:26.14e}",
    ]
    assert lines[i + 7] == "/"
    assert i < lines.index("TOPOPT_REGION")


def test_humd_humc_humf_family():
    """exA05-1 — HUMD_CONTROL keyword pairs, HUMC 29-wide concentration
    (non-terminated, immediately before HUMF_REGION), fluxhumid cards
    with 29/26-wide dual values."""
    m = _model()
    ctrl = ET.SubElement(_aet(m), "humd_control")
    ET.SubElement(ctrl, "evaporation").text = "1"
    ET.SubElement(ctrl, "upper_limit").text = "1"
    ET.SubElement(_aet(m), "humc").text = "2.56e-05"
    m.upsert_value("humidity", "湿度1", [
        ("kind", "boundary", None), ("type", "4", None),
        ("param1", "-0.000309", None), ("param2", "0.0", None)])
    m.bind_condition("region", "風呂湯面", "湿度1")
    lines = _build(m)
    i = lines.index("HUMD_CONTROL")
    assert lines[i:i + 5] == ["HUMD_CONTROL", "evaporation", f"{1:>15d}",
                              "upper_limit", f"{1:>15d}"]
    j = lines.index("HUMC")
    assert lines[j] == "HUMC"
    assert lines[j + 1] == f"{2.56e-05:29.14e}"
    assert lines[j + 2] == "HUMF_REGION"
    assert lines[j + 3] == "fluxhumid    0   ! 湿度1"
    assert lines[j + 4] == f"{-0.000309:29.14e}{0.0:26.14e}"
    assert lines[j + 5] == "   風呂湯面"
    assert lines[j + 6] == "   /"
    assert lines[j + 7] == "/"


def test_humf_requires_type4_humc_not_alone():
    """HUMC (non-terminated) never emits without a following HUMF block."""
    m = _model()
    ET.SubElement(_aet(m), "humc").text = "2.56e-05"
    assert "HUMC" not in _build(m)


def test_surf_1mars_aent_vfrt():
    """exA15-3 (SURF_1MARS 15/12-wide) + exA15-1 (SURF_AENT kind +
    26-wide) + exA02-2a (VFRT_SPC 4-space region)."""
    m = _model()
    m.analysis_etc_section("free_surf")
    for k, v in (("tension", "0,0.0727"), ("surf_1mars", "2,0"),
                 ("surf_aent_kind", "adiabatic"),
                 ("surf_aent_value", "0"), ("vfrt_spc_region", "直方体領域")):
        m.set_free_surf_attr(k, v)
    lines = _build(m)
    i = lines.index("SURF_1MARS")
    assert lines[i + 1] == f"{2:>15d}{0:12d}"
    j = lines.index("SURF_AENT")
    assert lines[j:j + 3] == ["SURF_AENT", "   adiabatic",
                              f"{0.0:26.14e}"]
    k = lines.index("VFRT_SPC")
    assert lines[k:k + 3] == ["VFRT_SPC", "    直方体領域", "/"]
    assert i < j < lines.index("SURF_PROPERTY") < k


def test_pbas_material_rows():
    """exA14-1 — 12-wide material no + 26-wide pressure + temperature."""
    m = _model()
    pb = ET.SubElement(_aet(m), "pbas_material")
    r = ET.SubElement(pb, "row")
    r.attrib.update(no="1", p="101325", t="0")
    lines = _build(m)
    i = lines.index("PBAS_MATERIAL")
    assert lines[i:i + 2] == ["PBAS_MATERIAL",
                              f"{1:12d}{101325.0:26.14e}{0.0:26.14e}"]
    assert lines[i + 2] == "/"


def test_stmc_variable_arity_rows():
    """exA23-4 — flag + UNDR rows with 3-value and 1-value arities."""
    m = _model()
    st = ET.SubElement(_aet(m), "stmc")
    st.attrib["flag"] = "1"
    for no, vals in (("1", "0.99,0.5,0.0001"), ("5", "0.9999")):
        r = ET.SubElement(st, "row")
        r.attrib.update(no=no, vals=vals)
    lines = _build(m)
    i = lines.index("STMC")
    assert lines[i:i + 4] == [
        "STMC",
        f"{1:>15d}",
        "UNDR",
        f"{1:12d}{0.99:26.14e}{0.5:26.14e}{0.0001:26.14e}",
    ]
    assert lines[i + 4] == f"{5:12d}{0.9999:26.14e}"
    assert lines[i + 5] == "/"


def test_table_fanpq():
    """exA13-1 — name header + simple + 7-wide count + 27/25-wide rows."""
    m = _model()
    m.upsert_value("table", "fanpq", [("kind", "simple", None)])
    val = m.find_value("fanpq")
    for v1, v2 in ((0.6166666666666667, 127.4), (1.3333333333333333, 0.0)):
        r = ET.SubElement(val, "row")
        r.attrib.update(v1=f"{v1!r}", v2=f"{v2!r}")
    lines = _build(m)
    i = lines.index("TABLE")
    assert lines[i:i + 5] == [
        "TABLE",
        "   fanpq   ! fanpq",
        "   simple",
        f"{2:>7d}",
        f"{0.6166666666666667:>27.14e}{127.4:>25.14e}",
    ]
    assert lines[i + 5] == f"{1.3333333333333333:>27.14e}{0.0:>25.14e}"
    assert lines[i + 6] == "/"


def test_vmom_region_fixv():
    """exA05-2 — fixV card with 29/26/26 components, region, inner+outer
    terminators."""
    m = _model()
    m.upsert_value("vmom", "速度固定1",
                   [("source", "0.1,0,0", None)])
    m.bind_condition("region", "ファン_vfix1", "速度固定1")
    lines = _build(m)
    i = lines.index("VMOM_REGION")
    assert lines[i:i + 6] == [
        "VMOM_REGION",
        "fixV    0   ! 速度固定1",
        f"{0.1:29.14e}{0.0:26.14e}{0.0:26.14e}",
        "   ファン_vfix1",
        "   /",
        "/",
    ]


def test_varlist_passthrough():
    """exB02 — bare verbatim row + '/'."""
    m = _model()
    out = m.root.find("output")
    if out is None:
        out = ET.SubElement(m.root, "output")
    ET.SubElement(out, "varlist").text = (
        "WNOR 5 9999 0.001 0.49999 0.0001 6.28 99 100.39")
    lines = _build(m)
    i = lines.index("VARLIST")
    assert lines[i:i + 3] == [
        "VARLIST",
        "WNOR 5 9999 0.001 0.49999 0.0001 6.28 99 100.39",
        "/",
    ]


def test_all_absent_without_storage():
    lines = _build(_model())
    for cmd in ("UPWD", "TBEC", "LES_OPTION", "TOPOPT", "HUMD_CONTROL",
                "HUMC", "HUMF_REGION", "SURF_1MARS", "SURF_AENT",
                "VFRT_SPC", "PBAS_MATERIAL", "STMC", "TABLE",
                "VMOM_REGION", "VARLIST"):
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
    for cmd in ("UPWD", "TBEC", "LES_OPTION", "TOPOPT", "HUMD_CONTROL",
                "HUMC", "HUMF_REGION", "SURF_1MARS", "SURF_AENT",
                "VFRT_SPC", "PBAS_MATERIAL", "STMC", "TABLE",
                "VMOM_REGION", "VARLIST"):
        assert f"\r\n{cmd}\r\n" not in s, cmd

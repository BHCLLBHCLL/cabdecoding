"""§25 F2 batch: Solver_eng-grounded emissions — AMOM wall-shear
variants, HUMW type=1 (hum_ltype) / HUMH_REGION, MOVB_ESF_SORC, the
LSOL_FORCE_MODEL name tables, and the corrected TOPOPT_REGION mapping."""
from __future__ import annotations

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


# ------------------------------------------------- AMOM variants

def test_amom_rough_variant():
    """rough wall -> 'rough  static    0' card with AKS,SCAL lines."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("wall", "RoughWall", [
        ("kind", "rough", None), ("option", "1", None),
        ("roughness", "0.5", "mm"), ("rough_const", "9", None)])
    m.bind_condition("region", "Zmin面", "RoughWall")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("AMOM_REGION")
    assert lines[i + 1:i + 4] == [
        "rough  static    0   ! RoughWall",
        f"{0.5:29.14e}",
        f"{9.0:29.14e}",
    ]


def test_amom_power_variant():
    from s_export import build_sdat
    m = _model()
    m.upsert_value("wall", "PowerWall", [
        ("kind", "power_law", None), ("option", "1", None),
        ("exponent", "0.16", None)])
    m.bind_condition("region", "Zmax面", "PowerWall")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("AMOM_REGION")
    assert lines[i + 1] == "power  static    0   ! PowerWall"
    assert lines[i + 2] == f"{0.16:29.14e}"


def test_amom_noslip_unchanged():
    from s_export import build_sdat
    m = _model()
    m.upsert_value("wall", "Wall1", [("kind", "no_slip", None)])
    m.bind_condition("region", "Xmin面", "Wall1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("AMOM_REGION")
    assert lines[i + 1] == "noslip  static    0   ! Wall1"


# ------------------------------------------------- HUMW type=1 / HUMH

def test_humw_type1_with_ltype():
    """type=1 with hum_ltype emits the lewislaw/diffusion saturation
    cards; without hum_ltype it stays unemitted (mapping ambiguity)."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("humidity", "湿度2", [
        ("kind", "boundary", None), ("type", "1", None),
        ("param1", "-1.5", "m/s"), ("hum_ltype", "lewislaw", None)])
    m.bind_condition("region", "領域ペア1", "湿度2")
    m.upsert_value("humidity", "湿度3", [
        ("kind", "boundary", None), ("type", "1", None),
        ("param1", "-1", "m/s")])
    m.bind_condition("region", "領域ペア2", "湿度3")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("HUMW_REGION")
    assert "lewislaw  saturation    0   ! 湿度2" in lines[i:i + 10]
    assert "diffusion  saturation    0   ! 湿度3" not in lines


def test_humh_region_emission():
    """type=3 humidity values emit HUMH_REGION wallwater cards
    (Initial Moisture)."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("humidity", "初湿1", [
        ("kind", "boundary", None), ("type", "3", None),
        ("param1", "0.02", "m/s")])
    m.bind_condition("region", "Ymin面", "初湿1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("HUMH_REGION")
    assert lines[i + 1:i + 5] == [
        "wallwater    0   ! 初湿1",
        f"{0.02:26.14e}",
        "   Ymin面",
        "   /",
    ]


# ------------------------------------------------- LSOL name tables

def test_lsol_model_names_mapped():
    """dem model codes map onto the Solver_eng name tables (hertz_mindlin,
    none, JKR); unknown codes fall back to the defaults."""
    from s_export import build_sdat
    m = _model()
    m.set_analysis_etc_child("dem", "dem_motion", "1")
    m.set_analysis_etc_child("dem", "dem_contact_model", "2")
    m.set_analysis_etc_child("dem", "dem_rolling_resistance_model", "0")
    m.set_analysis_etc_child("dem", "dem_adhesion", "2")
    s = build_sdat(m, _props())
    assert "   hertz_mindlin" in s
    assert "rolling_resistance_model\r\n   none" in s
    assert "cohesion_model\r\n   JKR" in s


# ------------------------------------------------- MOVB_ESF_SORC

def test_movb_esf_sorc_emission():
    """movb_fixed e_field values emit MOVB_ESF_SORC fixE cards after
    ES_FIELD_BC."""
    from s_export import build_sdat
    m = _model()
    m.add_part(name="MObj", kind="cube", attribute="solid")
    m.upsert_value("e_field", "MovbV", [
        ("e_potential", "5", "V"), ("movb_fixed", "T", None)])
    m.bind_condition("parts", "MObj", "MovbV")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("MOVB_ESF_SORC")
    assert lines[i + 1:i + 4] == [
        "fixE    0   ! MovbV",
        f"{5.0:26.14e}",
        "   MObj",
    ]
    assert "ES_FIELD_BC" not in s  # no region-bound e_field values


def test_movb_esf_sorc_absent_without_movb():
    from s_export import build_sdat
    m = _model()
    m.upsert_value("e_field", "Plain", [("e_potential", "1", "V")])
    m.bind_condition("region", "Xmin面", "Plain")
    assert "MOVB_ESF_SORC" not in build_sdat(m, _props())


# ------------------------------------------------- TOPOPT mapping fix

def test_topopt_region_uses_obj_func_fields():
    """The (1,1) pair is IOBJ=obj1_func_type + ICNS=1, LOLM comes from
    obj1_constraint_base — not pinned constants."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("topo_obj_func", "体積目的関数1", [
        ("kind", "volumetric_object_function", None),
        ("obj1_func_type", "2", None),
        ("obj1_constraint_base", "0.05", None),
        ("obj2_func_type", "0", None),
        ("obj2_set_tolerance", "F", None),
        ("obj2_tolerance", "0", None)])
    m.upsert_value("topo_design_space", "設計空間1", [
        ("vol_constraint_type", "upper", None),
        ("vol_constraint", "0.12", None)])
    m.bind_condition("parts", "Design_space", "体積目的関数1")
    m.bind_condition("parts", "Design_space", "設計空間1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("TOPOPT_REGION")
    assert lines[i + 2] == f"{2:15d}{1:12d}"
    assert lines[i + 3] == f"{0.05:29.14e}" + f"{0.12:26.14e}"

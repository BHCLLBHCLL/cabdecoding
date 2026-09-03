"""§26 G1: PCLE_CREATE spray emission — the exA07-3 card reproduced
verbatim from the official <value type="spray"> storage."""
from __future__ import annotations

from xml.etree.ElementTree import SubElement

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model_with_spray():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="点1", kind="point", attribute="point")
    info = next(p for p in m.parts() if p.name == "点1")
    coord = SubElement(info.elem, "coord")
    coord.attrib["unit"] = "mm"
    coord.text = " 5,50,50 "
    assert m.upsert_value("spray", "噴霧1", [
        ("property", "ep", None),
        ("particle_mass", "0.0001", "default"),
        ("particle_num", "100", None),
        ("time_start", "0", None),
        ("time_end", "10", None),
        ("time_inc", "0.003", None),
        ("gravity_system", "0,0", None),
        ("normal", "1,0,0", None),
        ("velocity", "2", "m/s"),
        ("temperature", "0", "C"),
        ("angle", "50,70", None),
        ("diameter", "2.5", "mm"),
        ("charge", "3e-11", None),
        ("pcl_restrict", "-1", None),
        ("mars_option", "0,0,0,0,0", None),
    ])
    assert m.bind_condition("parts", "点1", "噴霧1")
    return m


def test_pcle_create_matches_official_layout():
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = _model_with_spray()
    s = build_sdat(m, PropertyModel(
        parse_property(new_property_bytes())))
    lines = s.split("\r\n")
    i = lines.index("PCLE_CREATE")
    assert lines[i:i + 13] == [
        "PCLE_CREATE",
        "mass-standard",
        "spray-cone           1",
        f"{1.0e-4:29.14e}",
        f"{2.0:29.14e}",
        " " * 3 + "".join(f"{v:26.14e}" for v in
                       (1.0e3, -1.0, 1.0e-4, 1.0e-1)) + "   0",
        " " * 3 + "".join(f"{v:26.14e}"
                       for v in (0.0, 10.0, 3.0e-3)),
        f"{100:15d}{1:12d}{0:12d}",
        f"{0:15d}" + "".join(f"{v:26.14e}" for v in
                                     (5.0e-3, 5.0e-2, 5.0e-2,
                                      1.0, 0.0, 0.0)),
        " " * 3 + "".join(f"{v:26.14e}" for v in (50.0, 70.0, 2.5e-3)),
        "    echarge",
        f"{3.0e-11:29.14e}",
        "   /",
    ]
    assert lines[i + 13] == "/"
    assert lines.index("PCLE_CREATE") < lines.index("FOUT")


def test_pcle_create_absent_without_spray():
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    assert "PCLE_CREATE" not in build_sdat(
        _model_with_spray.__wrapped__() if False else StpreModel(
            parse_stpre(new_stpre_bytes("T"))),
        PropertyModel(parse_property(new_property_bytes())))


def test_pcle_create_no_charge_no_iatrb():
    """A spray without a charge child emits IATRB=0 and no echarge
    block."""
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="点1", kind="point", attribute="point")
    info = next(p for p in m.parts() if p.name == "点1")
    coord = SubElement(info.elem, "coord")
    coord.attrib["unit"] = "mm"
    coord.text = " 5,50,50 "
    m.upsert_value("spray", "噴霧1", [
        ("particle_mass", "0.0001", "default"),
        ("particle_num", "100", None),
        ("time_start", "0", None), ("time_end", "10", None),
        ("time_inc", "0.003", None), ("normal", "1,0,0", None),
        ("velocity", "2", "m/s"), ("angle", "50,70", None),
        ("diameter", "2.5", "mm")])
    m.bind_condition("parts", "点1", "噴霧1")
    s = build_sdat(m, PropertyModel(
        parse_property(new_property_bytes())))
    lines = s.split("\r\n")
    i = lines.index("PCLE_CREATE")
    assert lines[i + 2] == "spray-cone           0"
    assert "echarge" not in lines[i:i + 12]


# ------------------------------------------------- G1 余项: ES_FIELD 头

def test_es_field_heads_emission():
    """ES_FIELD (LEQ_ESF from partcile_echarge, LSOLV=0) + ES_FIELD_PROP
    material 1 = eps0 * relative permittivity."""
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = _model_with_spray()
    m.set_analysis_etc_value("partcile_echarge", "2")
    m.set_project_value("electrostatic_permittivity", "2.0")
    s = build_sdat(m, PropertyModel(
        parse_property(new_property_bytes())))
    lines = s.split("\r\n")
    i = lines.index("ES_FIELD")
    assert lines[i + 1] == f"{2:15d}{0:12d}"
    assert lines[i + 2] == "ES_FIELD_PROP"
    assert lines[i + 3] == f"{1:15d}{8.85937637406252e-12 * 2.0:26.14e}"
    assert lines[i + 4] == "/"
    assert lines.index("ES_FIELD") < lines.index("FOUT")


def test_es_field_heads_absent_when_off():
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = _model_with_spray()
    assert "ES_FIELD\r" not in build_sdat(
        m, PropertyModel(parse_property(new_property_bytes())))[:200]


def test_lsol_force_ip_group():
    """dem enabled -> LSOL_FORCE_IP contact group with CONT_TYPE='follow'
    (conforms to LSOL_FORCE_MODEL), no section terminator."""
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = _model_with_spray()
    m.set_analysis_etc_child("dem", "dem_motion", "1")
    m.set_analysis_etc_child("dem", "dem_contact_model", "1")
    m.set_analysis_etc_child("dem", "dem_rolling_resistance_model", "1")
    m.set_analysis_etc_child("dem", "dem_adhesion", "0")
    s = build_sdat(m, PropertyModel(
        parse_property(new_property_bytes())))
    lines = s.split("\r\n")
    i = lines.index("LSOL_FORCE_IP")
    assert lines[i + 1:i + 4] == [
        "contact",
        " follow" + f"{0:12d}{0:12d}",
        "/",
    ]
    assert lines.index("LSOL_FORCE_IP") > lines.index("LSOL_TIME_STEP")


# ------------------------------------------------- R3: ES_FIELD 多材质

def test_es_field_prop_multi_material():
    """es_material storage emits one ES_FIELD_PROP line per material;
    negative permittivity = metal marker (exA07-3 material 2 = -1)."""
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = _model_with_spray()
    m.set_analysis_etc_value("partcile_echarge", "2")
    m.set_es_material(1, 8.85937637406252e-12)
    m.set_es_material(2, -1.0)
    s = build_sdat(m, PropertyModel(
        parse_property(new_property_bytes())))
    lines = s.split("\r\n")
    i = lines.index("ES_FIELD_PROP")
    # stored permittivity is passed through verbatim with a 26-width float
    assert lines[i + 1] == f"{1:15d}{8.85937637406252e-12:26.14e}"
    assert lines[i + 2] == f"{2:15d}{-1.0:26.14e}"
    # the .14g round-trip in the XML storage slightly trims the digits
    assert lines[i + 1].endswith("e-12") or lines[i + 1].endswith("e-11")
    assert lines[i + 3] == "/"


# ------------------------------------------------- R3: LSOL_FORCE_BC 材料对

def test_lsol_force_bc_property_group():
    """dem_ip_group emits the LSOL_FORCE_BC contact property block in the
    exA07-4 layout (param name + _f value lines)."""
    from s_export import build_sdat
    from cabxml import PropertyModel, parse_property, new_property_bytes
    m = _model_with_spray()
    m.set_analysis_etc_child("dem", "dem_motion", "1")
    m.set_dem_ip_group({
        "normal_spring_stiffness": 5.0e3,
        "tangential_spring_stiffness": 5.0e3,
        "friction_coefficient": 0.3,
        "young_modulus": 1.872e8,
        "poisson_ratio": 0.17,
    })
    s = build_sdat(m, PropertyModel(
        parse_property(new_property_bytes())))
    lines = s.split("\r\n")
    i = lines.index("LSOL_FORCE_BC")
    assert lines[i:i + 6] == [
        "LSOL_FORCE_BC",
        "contact",
        " follow" + f"{0:12d}{0:12d}",
        "      normal_spring_stiffness",
        f"{5.0e3:29.14e}",
        "      tangential_spring_stiffness",
    ]
    assert f"{1.872e8:29.14e}" in lines[i:i + 14]

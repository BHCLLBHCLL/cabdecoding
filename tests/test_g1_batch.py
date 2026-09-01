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
        f"{1.0e-4:26.14e}",
        f"{2.0:26.14e}",
        f"{1.0e3:26.14e}{-1.0:26.14e}{1.0e-4:26.14e}"
        f"{1.0e-1:26.14e}{0:4d}",
        f"{0.0:26.14e}{10.0:26.14e}{3.0e-3:26.14e}",
        f"{100:12d}{1:12d}{0:12d}",
        f"{0:15d}{5.0e-3:26.14e}{5.0e-2:26.14e}{5.0e-2:26.14e}"
        f"{1.0:26.14e}{0.0:26.14e}{0.0:26.14e}",
        f"{50.0:26.14e}{70.0:26.14e}{2.5e-3:26.14e}",
        "    echarge",
        f"{3.0e-11:26.14e}",
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

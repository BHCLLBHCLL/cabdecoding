"""W3: data-layer gold lock — cab / material / unit round-trip."""
from __future__ import annotations

from pathlib import Path

import cab_materials
from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
EX4 = ROOT / "tests" / "ex4_e.cab"


def test_ex4_cab_members_roundtrip_bytes():
    raw = EX4.read_bytes()
    arch = CabArchive.parse(raw)
    members = {m.name: m.data for m in arch.fill_member_data()}
    rebuilt = arch.to_bytes(preserve_source_blocks=True)
    again = CabArchive.parse(rebuilt)
    again_m = {m.name: m.data for m in again.fill_member_data()}
    assert set(again_m) == set(members)
    for name, data in members.items():
        assert again_m[name] == data


def test_stpre_and_property_xml_byte_lock():
    arch = CabArchive.parse(EX4.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    xml = members["ex4_e.xml"]
    prop = members["_ex4_e_property.xml"]
    assert parse_stpre(xml).serialize() == xml
    assert parse_property(prop).serialize() == prop


def test_unit_and_material_library_lock():
    arch = CabArchive.parse(EX4.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    model = StpreModel(parse_stpre(members["ex4_e.xml"]))
    assert model.units["display"] == "mm"
    assert model.units["geometry"] == "m"
    assert model.set_unit("display", "m")
    again = StpreModel(parse_stpre(model.doc.serialize()))
    assert again.units["display"] == "m"
    assert again.units["geometry"] == "m"

    std = cab_materials.standard_property_model()
    names = std.material_names()
    assert len(names) == 239
    assert "iron(Fe)(300K)" in names
    assert "air(incompressible/20C)" in names
    props = PropertyModel(parse_property(members["_ex4_e_property.xml"]))
    assert "diecast_magnesium(300K)" in props.material_names()

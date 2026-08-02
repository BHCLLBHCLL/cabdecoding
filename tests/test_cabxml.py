"""P1: byte-stable XML models and metadata editing."""

import os

import cabxml
from cab_container import CabArchive
from cabxml import (PropertyDoc, PropertyModel, StpreDoc, StpreModel,
                    parse_property, parse_stpre)


HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")


def _members() -> dict[str, bytes]:
    arch = CabArchive.parse(open(CAB, "rb").read())
    return {m.name: m.data for m in arch.fill_member_data()}


def test_stpre_roundtrip_byte_identical():
    data = _members()["ex4_e.xml"]
    doc = parse_stpre(data)
    assert isinstance(doc, StpreDoc)
    assert doc.root.tag == "stpre"
    assert doc.serialize() == data


def test_property_roundtrip_byte_identical():
    data = _members()["_ex4_e_property.xml"]
    doc = parse_property(data)
    assert isinstance(doc, PropertyDoc)
    assert doc.root.tag == "property"
    assert doc.serialize() == data


def test_stpre_model_accessors():
    model = StpreModel(parse_stpre(_members()["ex4_e.xml"]))
    assert model.project_name == "ex4_e"
    assert model.units["display"] == "mm"
    assert model.units["geometry"] == "m"
    parts = model.parts()
    assert len(parts) == 31
    by_name = {p.name: p for p in parts}
    assert by_name["lower_cover_01"].property == "diecast_magnesium(300K)"
    assert by_name["lower_cover_01"].group == "cellular_phone"
    assert by_name["(cuboid)_IC_01"].kind == "cube"
    assert model.find_part("speaker") is not None
    axes = model.mesh_axes()
    assert [len(v) for v in axes.values()] == [99, 243, 63]
    assert abs(axes["x"][0] - (-100.0)) < 1e-9
    assert len(model.regions()) == 5
    ar = model.analysis_region()
    assert ar is not None
    from cabxml import _children
    assert len(_children(ar, "region")) == 6
    assert len(model.values()) == 25
    assert len(model.conditions()) == 24
    boxes = model.part_boxes("lower_cover_01")
    assert boxes and boxes[0][:6] == [35, 65, 19, 25, 18, 18]


def test_property_model_accessors():
    model = PropertyModel(parse_property(_members()["_ex4_e_property.xml"]))
    names = model.material_names()
    assert "air(incompressible/20C)" in names
    assert "diecast_magnesium(300K)" in names
    ent = model.find_entry("air(incompressible/20C)")
    assert ent is not None


def test_edit_part_metadata_roundtrip():
    data = _members()["ex4_e.xml"]
    model = StpreModel(parse_stpre(data))
    assert model.rename_part("speaker", "speaker_v2")
    assert model.set_part_property("speaker_v2", "epoxy_resin(300K)")
    assert model.set_part_color("speaker_v2", (1, 2, 3, 255))
    out = model.doc.serialize()
    # only the expected node changed -> reparse and verify values
    model2 = StpreModel(parse_stpre(out))
    p = model2.find_part("speaker_v2")
    assert p is not None
    from cabxml import _first
    assert _first(p, "name").text.strip() == "speaker_v2"
    assert _first(p, "property").text.strip() == "epoxy_resin(300K)"
    assert _first(p, "color").text.strip() == "1,2,3,255"
    assert model2.find_part("speaker") is None
    assert len(model2.parts()) == 31
    # untouched parts still present
    assert model2.find_part("battery") is not None
    # original doc still serializes byte-identically
    assert StpreModel(parse_stpre(data)).doc.serialize() == data


def test_edit_value_and_material():
    data = _members()["ex4_e.xml"]
    model = StpreModel(parse_stpre(data))
    assert model.set_value_param("HeatSource1", "source", "0.5")
    model2 = StpreModel(parse_stpre(model.doc.serialize()))
    v = model2.find_value("HeatSource1")
    from cabxml import _first
    assert _first(v, "source").text.strip() == "0.5"

    pdata = _members()["_ex4_e_property.xml"]
    pm = PropertyModel(parse_property(pdata))
    assert pm.set_entry_value("air(incompressible/20C)", "density", "1.3")
    pm2 = PropertyModel(parse_property(pm.doc.serialize()))
    ent = pm2.find_entry("air(incompressible/20C)")
    from cabxml import _first
    assert _first(ent, "density").text.strip() == "1.3"


def test_cab_rebuild_with_edited_xml():
    arch = CabArchive.parse(open(CAB, "rb").read())
    members = {m.name: m for m in arch.fill_member_data()}
    model = StpreModel(parse_stpre(members["ex4_e.xml"].data))
    assert model.rename_part("battery", "battery_pack")
    edited = model.doc.serialize()
    members["ex4_e.xml"].data = edited

    rebuilt = arch.to_bytes(preserve_source_blocks=False)
    re_arch = CabArchive.parse(rebuilt)
    re_members = {m.name: m.data for m in re_arch.fill_member_data()}
    assert re_members["ex4_e.xml"] == edited
    assert re_members["_ex4_e_property.xml"] == members["_ex4_e_property.xml"].data
    assert re_members["_ex4_e_all.x_t"] == members["_ex4_e_all.x_t"].data
    m2 = StpreModel(parse_stpre(re_members["ex4_e.xml"]))
    assert m2.find_part("battery_pack") is not None
    assert m2.find_part("battery") is None

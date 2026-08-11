"""STpre standard material library (standard_property_ENG.xml)."""
from __future__ import annotations

from pathlib import Path

import cab_materials
from cabxml import PropertyModel, new_property_bytes, parse_property

ROOT = Path(__file__).resolve().parents[1]


def test_standard_property_path_resolves():
    path = cab_materials.standard_property_path()
    assert path is not None and path.is_file()
    assert path.name == "standard_property_ENG.xml"


def test_standard_library_has_stpre_solid_groups():
    model = cab_materials.standard_property_model()
    groups = {g for _, g, _ in model.group_catalog()}
    for name in ("pure_metal", "insulator", "semiconductor", "glass",
                 "rubber_plastic", "ceramics", "alloy", "concrete",
                 "brick_sand", "wood", "fiber_paper_ice",
                 "(Archi)cement_stone"):
        assert name in groups, name
    assert len(model.material_names()) >= 200


def test_new_property_bytes_is_full_standard():
    props = PropertyModel(parse_property(new_property_bytes()))
    assert len(props.material_names()) >= 200
    assert "iron(Fe)(300K)" in props.material_names()


def test_merge_standard_into_minimal():
    from cabxml import new_property_bytes as _
    # start from tiny in-memory library (bypass cab_materials)
    tiny = (
        b"\xef\xbb\xbf<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<property><group><type>fluid</type>"
        b"<name>gas(incompressible)</name>"
        b"<entry><name>air(incompressible/20C)</name>"
        b"<density>1.206</density></entry></group></property>"
    )
    props = PropertyModel(parse_property(tiny))
    assert len(props.material_names()) == 1
    n = cab_materials.merge_standard_into(props)
    assert n > 100
    assert "pure_metal" in {g for _, g, _ in props.group_catalog()}
    assert "iron(Fe)(300K)" in props.material_names()

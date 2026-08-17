"""ccel ATTR CBODY for cut-cell area parts (official exA23-1a)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import ccel
import cab_mesh
import s_export

ROOT = Path(__file__).resolve().parents[1]
EX4_CAB = ROOT / "tests" / "ex4_e.cab"


@pytest.fixture()
def ex4_models():
    from cab_container import CabArchive
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    arch = CabArchive.parse(EX4_CAB.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return (StpreModel(parse_stpre(members["ex4_e.xml"])),
            PropertyModel(parse_property(members["_ex4_e_property.xml"])))


def _register(model, attr: str):
    p = model.parts()[0]
    p.elem.find("attribute").text = f" {attr} "
    assert cab_mesh.set_part_cutcell(model, p.name, True)
    return p


def test_ccel_attr_cbody_for_cutcell_area(ex4_models):
    model, _props = ex4_models
    p = _register(model, "area")
    assert s_export._ccel_attr(model.parts()[0]) == "CBODY"
    parts, _a, _f = ccel.read_ccel_doc(s_export.build_ccel(model))
    assert parts[0].attr == "CBODY"
    cab_mesh.set_part_cutcell(model, p.name, False)


def test_ccel_attr_body_for_cutcell_solid(ex4_models):
    model, _props = ex4_models
    p = _register(model, "solid")
    assert s_export._ccel_attr(model.parts()[0]) == "BODY"
    parts, _a, _f = ccel.read_ccel_doc(s_export.build_ccel(model))
    assert parts[0].attr == "BODY"
    cab_mesh.set_part_cutcell(model, p.name, False)


def test_ccel_attr_panel_wins_over_cbody(ex4_models):
    model, _props = ex4_models
    p = _register(model, "panel")
    assert s_export._ccel_attr(model.parts()[0]) == "PANEL"
    cab_mesh.set_part_cutcell(model, p.name, False)


def test_ccel_attr_fluid_without_cutcell(ex4_models):
    model, _props = ex4_models
    p = model.parts()[0]
    p.elem.find("attribute").text = " fluid "
    assert s_export._ccel_attr(model.parts()[0]) == "FLUID"

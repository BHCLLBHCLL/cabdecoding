"""W1: List of Part priority rank (fan/porous first, then document order)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

ROOT = Path(__file__).resolve().parents[1]
EX4_CAB = ROOT / "tests" / "ex4_e.cab"


@pytest.fixture()
def ex4_model():
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    arch = CabArchive.parse(EX4_CAB.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return StpreModel(parse_stpre(members["ex4_e.xml"]))


def test_priority_rank_doc_order(ex4_model):
    import cab_mesh
    model = ex4_model
    names = [p.name for p in model.parts()]
    rank = cab_mesh.part_priority_rank(model)
    assert rank[names[0]] == 1
    assert rank[names[1]] == 2
    assert set(rank) == set(names)


def test_priority_rank_fan_beats_doc_order(ex4_model):
    import cab_mesh
    model = ex4_model
    body, fan = model.parts()[0], model.parts()[1]
    fan.elem.attrib["type"] = "fan"
    rank = cab_mesh.part_priority_rank(model)
    assert rank[fan.name] == 1
    assert rank[body.name] == 2

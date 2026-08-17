"""W1: mesh_fine_divide actually subdivides overlapping grid intervals."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import cab_grid
from cabxml import StpreModel, new_stpre_bytes, parse_stpre

ROOT = Path(__file__).resolve().parents[1]


class _Part:
    def __init__(self, name, fine, base="", size=""):
        self.name = name
        self.mesh_fine_divide = fine
        self.base = base
        self.size = size
        self.transform = ""


def test_fan_2_0_0_splits_x_once():
    # exA02-2b: fan 2,0,0 — one cell across the part becomes two.
    axes = {"x": [0.0, 10.0, 20.0, 30.0],
            "y": [0.0, 10.0],
            "z": [0.0, 10.0]}
    part = _Part("Fan1", "2,0,0", "10,0,0", "10,10,10")
    out = cab_grid.refine_axes_by_fine_divide(axes, [part])
    assert out["y"] == axes["y"] and out["z"] == axes["z"]
    assert len(out["x"]) == 5
    assert out["x"][1] == pytest.approx(10.0)
    assert out["x"][2] == pytest.approx(15.0)
    assert out["x"][3] == pytest.approx(20.0)
    # idempotent: second apply does not split again
    again = cab_grid.refine_axes_by_fine_divide(out, [part])
    assert again["x"] == out["x"]


def test_fan_0_5_0_ensures_five_y_cells():
    # exA05-2: fan 0,5,0 — span [10,20] on y becomes 5 cells.
    axes = {"x": [0.0, 10.0],
            "y": [0.0, 10.0, 20.0, 30.0],
            "z": [0.0, 10.0]}
    part = _Part("Fan1", "0,5,0", "0,10,0", "10,10,10")
    out = cab_grid.refine_axes_by_fine_divide(axes, [part])
    assert out["x"] == axes["x"] and out["z"] == axes["z"]
    ys = [v for v in out["y"] if 10.0 - 1e-9 <= v <= 20.0 + 1e-9]
    assert len(ys) == 6  # 5 cells → 6 points
    assert ys[0] == pytest.approx(10.0)
    assert ys[-1] == pytest.approx(20.0)


def test_apply_fine_divide_writes_mesh_block():
    model = StpreModel(parse_stpre(new_stpre_bytes("fine")))
    model.set_mesh(
        {"x": [0.0, 10.0, 20.0], "y": [0.0, 10.0], "z": [0.0, 10.0]},
        domain_min=(0, 0, 0), domain_max=(20, 10, 10))
    model.add_part(name="Fan1", kind="fan", attribute="Fan")
    assert model.set_part_mesh_fine_divide("Fan1", "2,0,0")
    from xml.etree import ElementTree as ET
    el = model.find_part("Fan1")
    ET.SubElement(el, "base").text = " 0,0,0 "
    ET.SubElement(el, "size").text = " 10,10,10 "
    refined = cab_grid.apply_fine_divide_to_model(model)
    assert len(refined["x"]) == 4
    assert len(model.mesh_axes()["x"]) == 4
    # remesh path is idempotent
    cab_grid.apply_fine_divide_to_model(model)
    assert len(model.mesh_axes()["x"]) == 4

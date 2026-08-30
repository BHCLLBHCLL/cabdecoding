"""§24 MB batch: lower-level rough-grid option, multiblock limitation
rules (Pre_eng "Limitations for multiblock"), child-block wireframes."""
from __future__ import annotations

import numpy as np
import pytest

import cab_grid


@pytest.fixture(scope="module")
def qapp():
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys as _sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([_sys.argv[0]])
    yield app


def _model_with_child(part_lo=(60.0, 60.0, 60.0),
                      part_hi=(70.0, 70.0, 70.0)):
    """Domain 100³, child 10..20³, one cube part (default 60..70)."""
    from cab_parts import cube_tess
    from cabxml import StpreModel, parse_stpre, new_stpre_bytes
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(base=(0.0, 0.0, 0.0), size=(100.0, 100.0, 100.0))
    m.set_mesh({ax: [0.0, 100.0] for ax in "xyz"},
               domain_min=(0.0, 0.0, 0.0), domain_max=(100.0, 100.0, 100.0))
    assert m.add_child_block(
        "Child1", "RootBlock", (10.0, 10.0, 10.0), (20.0, 20.0, 20.0),
        length=(0.5, 0.5, 0.5))
    m.add_part(name="P1", kind="cube", attribute="solid")
    size = tuple(h - l for h, l in zip(part_hi, part_lo))
    tess = cube_tess(part_lo, size)
    tess.name = "P1"
    return m, [tess]


def _spec():
    return cab_grid.GridSpec(
        unit="mm", domain_min=(0.0, 0.0, 0.0), domain_max=(100.0, 100.0, 100.0),
        vertex_detection="minmax", method="rough_and_detail",
        standard_length=(1.0, 1.0, 1.0), threshold_length=(0.1, 0.1, 0.1),
        geometric_ratio=(1.0, 1.0, 1.0),
        geometric_ratio_external=(1.2, 1.2, 1.2))


# --------------------------------------- MB-1: lower-level rough grid

def test_lower_level_merges_parent_rough_lines():
    m, meshes = _model_with_child()
    pts = {t.name: np.asarray(t.points) * 1000.0 for t in meshes}
    blocks = m.mesh_blocks()
    kw = dict(part_vertices=None, part_bounds=(
        np.full(3, 60.0), np.full(3, 70.0)))
    _r, _d, plain = cab_grid.build_axes_multiblock(
        pts, _spec(), blocks, child_only=False, **kw)
    _r2, _d2, child_only = cab_grid.build_axes_multiblock(
        pts, _spec(), blocks, child_only=True, **kw)
    _r3, _d3, with_low = cab_grid.build_axes_multiblock(
        pts, _spec(), blocks, child_only=True, lower_level=True, **kw)
    pv = [v for v, _m in plain["x"]]
    cv = [v for v, _m in child_only["x"]]
    lv = [v for v, _m in with_low["x"]]
    # without the option, child-only discards parent rough lines 60/70
    assert 60.0 in pv and 60.0 not in cv
    # "Consider rough grid of lower level block": 60/70 come back as N
    assert 60.0 in lv and 70.0 in lv
    marks = {round(v, 9): mk for v, mk in with_low["x"]}
    assert marks[60.0] == "N"
    # child boundaries keep their priority marks
    assert marks[10.0] == "CS" and marks[20.0] == "C"


def test_gridding_dialog_lower_level_checkbox(qapp):
    import cab_dialogs
    m, meshes = _model_with_child()
    dlg = cab_dialogs.GriddingDialog(m, meshes, parent=None)
    try:
        dlg.detection_radios["minmax"].setChecked(True)
        dlg.method_radios["rough_and_detail"].setChecked(True)
        dlg.chk_child_only.setChecked(True)
        dlg.chk_lower_level.setChecked(False)
        dlg._gridding()
        off = [v for v, _mk in m.mesh_axis_entries("x")]
        dlg.chk_lower_level.setChecked(True)
        dlg._gridding()
        on = [v for v, _mk in m.mesh_axis_entries("x")]
        assert 60.0 not in off and 60.0 in on
        assert dlg.last_block_validation == []
    finally:
        dlg.close()


# ------------------------------------ MB-3: multiblock limitations

def _blocks(child_lo, child_hi, sibling_lo=None, sibling_hi=None):
    root = {"name": "RootBlock", "min": (0.0, 0.0, 0.0),
            "max": (100.0, 100.0, 100.0), "children": [
                {"name": "C1", "min": child_lo, "max": child_hi,
                 "children": []}]}
    if sibling_lo is not None:
        root["children"].append(
            {"name": "C2", "min": sibling_lo, "max": sibling_hi,
             "children": []})
    return [root]


def test_validate_child_inside_parent():
    issues = cab_grid.validate_multiblock(
        _blocks((10.0, 10.0, 110.0), (20.0, 20.0, 120.0)))
    assert any("outside" in i for i in issues)


def test_validate_sibling_interference():
    issues = cab_grid.validate_multiblock(
        _blocks((10.0, 10.0, 10.0), (30.0, 30.0, 30.0),
                (20.0, 20.0, 20.0), (40.0, 40.0, 40.0)))
    assert any("interfere" in i for i in issues)


def test_validate_ok_tree_has_no_issues():
    issues = cab_grid.validate_multiblock(
        _blocks((10.0, 10.0, 10.0), (20.0, 20.0, 20.0)))
    assert issues == []


def test_validate_mesh_distance_warnings():
    # sibling gap 5 mm < 2 meshes (2 x 4 mm); child hugs parent boundary
    issues = cab_grid.validate_multiblock(
        _blocks((0.0, 10.0, 10.0), (10.0, 20.0, 20.0),
                (15.0, 10.0, 10.0), (25.0, 20.0, 20.0)),
        spacing=4.0)
    assert any("two meshes" in i for i in issues)
    # same tree without spacing: errors only, no distance warnings
    assert not cab_grid.validate_multiblock(
        _blocks((0.0, 10.0, 10.0), (10.0, 20.0, 20.0),
                (15.0, 10.0, 10.0), (25.0, 20.0, 20.0)))


def test_validate_child_hugging_parent_boundary_warns():
    # child flush with the parent boundary (gap 0 < one mesh)
    issues = cab_grid.validate_multiblock(
        _blocks((0.0, 10.0, 10.0), (10.0, 20.0, 20.0)), spacing=4.0)
    assert any("one mesh" in i for i in issues)


# -------------------------------------- MB-2: child-block wireframes

def test_child_block_actors():
    vtk = pytest.importorskip("vtk")
    from cab_vtk import child_block_actors
    m, _meshes = _model_with_child()
    m.add_child_block("Child2", "RootBlock", (50.0, 10.0, 10.0),
                      (60.0, 20.0, 20.0), length=(0.5, 0.5, 0.5))
    actors = child_block_actors(m)
    assert len(actors) == 2
    for a in actors:
        assert isinstance(a, vtk.vtkActor)


def test_child_block_actors_empty_without_children():
    pytest.importorskip("vtk")
    from cab_vtk import child_block_actors
    from cabxml import StpreModel, parse_stpre, new_stpre_bytes
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    assert child_block_actors(m) == []

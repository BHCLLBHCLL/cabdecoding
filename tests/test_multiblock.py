"""L7.6: multiblock native gridding (STpre nested block layout)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

import cab_grid
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def _model_with_child():
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(base=(0.0, 0.0, 0.0), size=(100.0, 100.0, 100.0))
    m.set_mesh({ax: [0.0, 100.0] for ax in "xyz"},
               domain_min=(0.0, 0.0, 0.0),
               domain_max=(100.0, 100.0, 100.0))
    assert m.add_child_block(
        "Child1", "RootBlock", (10.0, 10.0, 10.0), (20.0, 20.0, 20.0),
        length=(0.5, 0.5, 0.5))
    return m


def _spec() -> cab_grid.GridSpec:
    return cab_grid.GridSpec(
        unit="mm", domain_min=(0.0, 0.0, 0.0),
        domain_max=(100.0, 100.0, 100.0),
        vertex_detection="minmax", method="rough_and_detail",
        standard_length=(1.0, 1.0, 1.0),
        threshold_length=(0.1, 0.1, 0.1),
        geometric_ratio=(1.0, 1.0, 1.0),
        geometric_ratio_external=(1.2, 1.2, 1.2))


def test_child_block_roundtrip():
    m = _model_with_child()
    blocks = m.mesh_blocks()
    assert blocks[0]["name"] == "RootBlock"
    child = blocks[0]["children"][0]
    assert child["name"] == "Child1"
    assert child["min"] == (10.0, 10.0, 10.0)
    assert child["max"] == (20.0, 20.0, 20.0)
    assert child["divide"] == "0.5,0.5,0.5"
    m2 = StpreModel(parse_stpre(m.doc.serialize()))
    c2 = m2.mesh_blocks()[0]["children"][0]
    assert c2["name"] == "Child1"
    assert c2["max"] == (20.0, 20.0, 20.0)
    assert m2.update_child_block_grid("Child1", (21, 21, 21))
    assert m2.block_param("Child1", "grid") == "21,21,21"
    assert m2.set_block_param(
        "Child1", "limit", "0.2,0.2,0.2", unit="mm")
    assert m2.block_param("Child1", "limit") == "0.2,0.2,0.2"


def test_build_axes_multiblock_merge():
    m = _model_with_child()
    spec = _spec()
    pts = {"box": np.array([[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]])}
    rough, detailed, entries = cab_grid.build_axes_multiblock(
        pts, spec, m.mesh_blocks())
    x = entries["x"]
    marks = {round(v, 9): mk for v, mk in x}
    assert marks[0.0] == "B"
    assert marks[100.0] == "B"
    assert marks[10.0] == "CS"
    assert marks[20.0] == "C"
    inside = sorted(v for v, mk in x if 10.0 < v < 20.0)
    assert len(inside) == 19
    np.testing.assert_allclose(
        np.diff([10.0] + inside + [20.0]), 0.5)
    assert len(x) > 30
    assert detailed["x"] == [v for v, _m in x]
    # child_only: only the child range plus domain bounds
    _, d2, e2 = cab_grid.build_axes_multiblock(
        pts, spec, m.mesh_blocks(), child_only=True)
    assert len(e2["x"]) == 23


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_gridding_dialog_multiblock(qapp):
    import cab_dialogs
    m = _model_with_child()
    dlg = cab_dialogs.GriddingDialog(m, [], parent=None)
    assert dlg.chk_child_only.isEnabled() is True
    assert dlg.chk_lower_level.isEnabled() is True
    # child appears in the parameter tree
    texts = []

    def walk(item):
        texts.append(item.text(0))
        for i in range(item.childCount()):
            walk(item.child(i))

    for i in range(dlg.block_tree.topLevelItemCount()):
        walk(dlg.block_tree.topLevelItem(i))
    assert "Child1" in texts
    dlg.detection_radios["minmax"].setChecked(True)
    dlg.method_radios["rough_and_detail"].setChecked(True)
    dlg.std["x"].setValue(1.0)
    dlg.ratio["x"].setValue(1.0)
    dlg.ratio_ext["x"].setValue(1.2)
    dlg._gridding()
    entries = m.mesh_axis_entries("x")
    marks = {round(v, 9): mk for v, mk in entries}
    assert marks[10.0] == "CS"
    assert marks[20.0] == "C"
    assert m.block_param("Child1", "grid") == "21,21,21"
    dlg.close()

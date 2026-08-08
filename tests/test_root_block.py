"""STpre RootBlock blue wireframe (Layout of Parts)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _box_model() -> StpreModel:
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml = next(
        m.data for m in archive.members
        if m.name.endswith(".xml") and "property" not in m.name
        and not m.name.startswith("_")
    )
    return StpreModel(parse_stpre(xml))


def test_root_block_bounds_box():
    model = _box_model()
    bb = model.root_block_bounds()
    assert bb == (0.0, 0.0, 0.0, 100.0, 100.0, 100.0)
    assert model.root_block_visible() is True
    model.set_root_block_visible(False)
    assert model.root_block_visible() is False
    model.set_root_block_visible(True)
    assert model.root_block_visible() is True


def test_root_block_falls_back_to_domain():
    raw = (b"\xef\xbb\xbf<?xml version=\"1.0\"?>\n"
           b"<stpre>\n</stpre>\n")
    model = StpreModel(parse_stpre(raw))
    model.ensure_domain(base=(0, 0, 0), size=(50, 60, 70))
    bb = model.root_block_bounds()
    assert bb == (0.0, 0.0, 0.0, 50.0, 60.0, 70.0)


def test_root_block_actor():
    pytest.importorskip("cab_vtk")
    import cab_vtk
    model = _box_model()
    frame = cab_vtk.root_block_frame(model)
    assert frame is not None
    assert frame.name == "RootBlock"
    # metres
    assert frame.bounds[3] == pytest.approx(0.1)
    actor = cab_vtk.root_block_actor(model)
    assert actor is not None
    assert actor.GetProperty().GetRepresentation() == 1  # wireframe


def test_set_root_block_range():
    model = _box_model()
    model.set_root_block_range((10, 20, 30), (40, 50, 60), name="RootBlock")
    assert model.root_block_bounds() == (10.0, 20.0, 30.0, 40.0, 50.0, 60.0)


def test_mesh_block_dialog(qapp):
    from cab_dialogs import MeshBlockDialog
    model = _box_model()
    dlg = MeshBlockDialog(model)
    assert dlg.windowTitle() == "Mesh:block"
    assert dlg.name_edit.text() == "RootBlock"
    assert dlg.min_spins["x"].value() == pytest.approx(0.0)
    assert dlg.max_spins["x"].value() == pytest.approx(100.0)
    dlg.max_spins["x"].setValue(120.0)
    assert dlg._apply() is True
    assert model.root_block_bounds()[3] == pytest.approx(120.0)
    dlg.close()


def test_new_project_has_rootblock_and_sketch(qapp):
    import cab_gui
    import cab_sketch
    from cabxml import _first
    win = cab_gui.CabViewer(None, enable_3d=False)
    try:
        assert win.model is not None
        assert win.model.analysis_region() is not None
        assert win.model.root_block_bounds() == (
            0.0, 0.0, 0.0, 100.0, 100.0, 100.0)
        assert win._root_block_visible is True
        assert _first(win.model.root, "sketch_control") is not None
        plane = cab_sketch.plane_from_xml(win.model)
        # STpre defaults: Min=-25, Max=125, Δ=Snap=5 (mm)
        assert plane.u_range == pytest.approx((-0.025, 0.125))
        assert plane.v_range == pytest.approx((-0.025, 0.125))
        assert plane.delta[0] == pytest.approx(0.005)
        assert plane.snap[0] == pytest.approx(0.005)
        assert win.control.layer_on("sketch_plane")
        assert win.control.layer_on("axis_sketch")
        assert win.control.sk_grid["(U)"]["Minimum"].value() == pytest.approx(
            -25.0)
        assert win.control.sk_grid["(U)"]["Maximum"].value() == pytest.approx(
            125.0)
    finally:
        win.close()

"""M8: sketch plane and sketch part tests."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _model():
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    return StpreModel(parse_stpre(members[xml_name]))


def test_sketch_plane_xml_roundtrip():
    import cab_sketch
    model = _model()
    plane = cab_sketch.SketchPlane(
        origin=(1.0, 2.0, 3.0),
        u=(1, 0, 0), v=(0, 1, 0), w=(0, 0, 1),
        u_range=(0.0, 0.25), v_range=(-0.1, 0.5),
        delta=(0.025, 0.05, 0.0), snap=(0.025, 0.05, 0.0),
        gridsnap=False, minus=True, color=(1, 2, 3, 255))
    cab_sketch.apply_plane(model, plane)
    from cabxml import StpreModel, parse_stpre
    model2 = StpreModel(parse_stpre(model.doc.serialize()))
    p2 = cab_sketch.plane_from_xml(model2)
    assert p2.origin == (1.0, 2.0, 3.0)
    np.testing.assert_allclose(p2.u_range, (0.0, 0.25))
    assert p2.gridsnap is False and p2.minus is True
    assert p2.color == (1, 2, 3, 255)


def test_reset_and_fit_plane():
    import cab_sketch
    model = _model()
    p = cab_sketch.reset_plane_to_domain(model)
    base = model.domain_base()
    assert p.origin[2] == pytest.approx(base[2])
    np.testing.assert_allclose(p.u, (1, 0, 0))
    np.testing.assert_allclose(p.w, (0, 0, 1))
    fit = cab_sketch.fit_plane_to_domain(model, p)
    base = model.domain_base()
    size = model.domain_size()
    assert fit.u_range[0] == pytest.approx(base[0] / 1000.0)
    assert fit.u_range[1] == pytest.approx((base[0] + size[0]) / 1000.0)
    assert fit.v_range[1] == pytest.approx((base[1] + size[1]) / 1000.0)


def test_sketch_plane_actors():
    pytest.importorskip("cab_vtk")
    import cab_vtk
    import cab_sketch
    import numpy as np
    plane = cab_sketch.SketchPlane(
        u_range=(0.0, 0.125), v_range=(0.0, 0.125),
        delta=(0.005, 0.005, 0.0))
    pd = cab_vtk.sketch_plane_grid(plane)
    assert pd.GetNumberOfLines() > 0
    minor, major, labels = cab_vtk.sketch_plane_grid_layers(plane)
    assert minor.GetNumberOfLines() > 0
    assert major.GetNumberOfLines() > 0
    assert major.GetNumberOfLines() < minor.GetNumberOfLines() + major.GetNumberOfLines()
    assert any(t == "0" or t == "0.0" or t.endswith("25") for _, t in labels)
    assert cab_vtk.sketch_plane_major_stride(plane) == 5
    actors = cab_vtk.sketch_axes_actors(plane)
    assert len(actors) >= 4  # 3 arrows (+ labels) + origin ball
    grid_actors = cab_vtk.sketch_plane_actors(plane)
    assert len(grid_actors) >= 2  # minor + major (+ labels)
    assert cab_vtk.sketch_plane_actor(plane) is not None
    # Corner global XYZ marker builds with STpre tip proportions
    ax = cab_vtk.axes_actor()
    assert ax.GetXAxisLabelText().lower() == "x"
    assert cab_vtk.world_origin_marker_actors(0.1)

    # Max=25 mm, Δ=10 mm: must keep 副网格 at 10 and 20 (not drop 20)
    p25 = cab_sketch.SketchPlane(
        u_range=(0.0, 0.025), v_range=(0.0, 0.025),
        delta=(0.010, 0.010, 0.010))
    us = cab_vtk._sketch_axis_samples(0.0, 0.025, 0.010)
    np.testing.assert_allclose(us * 1000.0, [0.0, 10.0, 20.0, 25.0])
    mi, ma, _ = cab_vtk.sketch_plane_grid_layers(p25)
    assert mi.GetNumberOfLines() >= 4  # 10 & 20 on U and V
    assert ma.GetNumberOfLines() >= 4  # 0 & 25 borders

    # Max=25 mm, Δ=5 mm (STpre screenshot): 5×5 secondary grid
    p5 = cab_sketch.SketchPlane(
        u_range=(0.0, 0.025), v_range=(0.0, 0.025),
        delta=(0.005, 0.005, 0.005))
    us5 = cab_vtk._sketch_axis_samples(0.0, 0.025, 0.005)
    np.testing.assert_allclose(
        us5 * 1000.0, [0.0, 5.0, 10.0, 15.0, 20.0, 25.0])
    mi5, ma5, _ = cab_vtk.sketch_plane_grid_layers(p5)
    assert mi5.GetNumberOfLines() >= 8
    assert ma5.GetNumberOfLines() >= 4


def test_sketch_tess_counts():
    import cab_sketch
    plane = cab_sketch.SketchPlane()
    rect = cab_sketch.SketchProfile(geometry_type="rectangle")
    t = cab_sketch.sketch_tess(plane, rect, "extrusion", 10.0)
    assert len(t.points) == 8 and len(t.triangles) == 12
    tp = cab_sketch.sketch_tess(plane, rect, "panel", 0.0)
    assert len(tp.points) == 4 and len(tp.triangles) == 2
    circ = cab_sketch.SketchProfile(
        geometry_type="circle", radius=5.0, divisions=12)
    tc = cab_sketch.sketch_tess(plane, circ, "extrusion", 10.0)
    assert len(tc.points) == 24 and len(tc.triangles) == 44


def test_register_and_rebuild_sketch_part():
    import cab_sketch
    model = _model()
    plane = cab_sketch.SketchPlane(origin=(0.0, 0.0, 0.0))
    profile = cab_sketch.SketchProfile(
        geometry_type="rectangle", location=(0, 0), size=(10, 20))
    assert cab_sketch.register_sketch_part(
        model, name="sk1", plane=plane, profile=profile,
        model_type="extrusion", thickness_mm=5.0,
        material="air(incompressible/20C)", attribute="Solid") is True
    parts = cab_sketch.sketch_parts_from_model(model)
    assert len(parts) == 1 and parts[0].name == "sk1"
    from cabxml import StpreModel, parse_stpre
    model2 = StpreModel(parse_stpre(model.doc.serialize()))
    parts2 = cab_sketch.sketch_parts_from_model(model2)
    assert len(parts2) == 1 and len(parts2[0].points) == 8


def test_sketch_dialog_spec(qapp):
    import cab_sketch
    model = _model()
    dlg = cab_sketch.SketchPartDialog(model, None, parent=None)
    dlg.name_edit.setText("sk2")
    dlg.geometry_type.setCurrentText("Rectangle")
    dlg.rect_size["u"].setValue(12.0)
    dlg.rect_size["v"].setValue(8.0)
    dlg.height.setValue(3.0)
    spec = dlg.spec()
    assert spec["name"] == "sk2"
    assert spec["profile"].geometry_type == "rectangle"
    assert spec["profile"].size == (12.0, 8.0)
    assert spec["thickness"] == 3.0
    dlg.close()


def test_control_sketch_page_and_action(qapp, monkeypatch):
    import cab_sketch
    import cab_gui
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = StpreModel(parse_stpre(members[xml_name]))
    viewer.archive = archive
    viewer.control.load_sketch(viewer.model)
    plane = viewer.control.sketch_plane()
    assert plane.origin == (0.0, 0.0, 0.0)
    # reset action writes plane + XML
    viewer._on_sketch_action("reset")
    base = viewer.model.domain_base()
    assert viewer.model.doc.root.find(
        "sketch_control/system/c") is not None
    p = cab_sketch.plane_from_xml(viewer.model)
    assert p.origin[2] == pytest.approx(base[2])
    # update action reads widget values back
    viewer.control.sk_origin["x"].setValue(5.0)
    viewer._on_sketch_action("update")
    p = cab_sketch.plane_from_xml(viewer.model)
    assert p.origin[0] == pytest.approx(5.0)

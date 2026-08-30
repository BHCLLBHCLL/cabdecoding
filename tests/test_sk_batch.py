"""§24 SK batch: arc primitive, editing tools, dimension driving, and the
three missing Sketch Part model types (9/9 coverage)."""
from __future__ import annotations

import numpy as np
import pytest

import cab_sketch


@pytest.fixture(scope="module")
def qapp():
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys as _sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([_sys.argv[0]])
    yield app


def _poly(profile):
    return np.asarray(profile.polygon(), dtype=float)


# ------------------------------------------------- SK-1: arc primitive

def test_arc_polygon_pie_and_open():
    arc = cab_sketch.SketchProfile(
        geometry_type="arc", center=(10.0, 0.0), radius=5.0,
        divisions=16, start_angle=0.0, end_angle=180.0)
    pts = arc.polygon()
    # pie: arc samples + centre
    assert len(pts) == 17
    assert pts[-1] == (10.0, 0.0)
    first = pts[0]
    assert abs(first[0] - 15.0) < 1e-9 and abs(first[1]) < 1e-9
    # open arc: chain only (close=False -> no centre point)
    open_arc = cab_sketch.SketchProfile(
        geometry_type="arc", center=(10.0, 0.0), radius=5.0,
        divisions=16, start_angle=0.0, end_angle=180.0, close=False)
    assert len(open_arc.polygon()) == 16


def test_arc_tessellates_with_volume():
    plane = cab_sketch.SketchPlane()
    arc = cab_sketch.SketchProfile(
        geometry_type="arc", center=(0.0, 0.0), radius=10.0,
        divisions=32, start_angle=0.0, end_angle=360.0)
    part = cab_sketch.sketch_tess(plane, arc, "extrusion", 10.0)
    assert part.triangles.shape[0] > 0
    # half-disc pie (0..360 with close -> full circle here: span==360 keeps
    # the circle path) — just require a positive volume
    vol = 0.0
    p = np.asarray(part.points)
    t = np.asarray(part.triangles)
    for tri in t:
        a, b, c = p[tri]
        vol += float(np.dot(a, np.cross(b, c))) / 6.0
    assert abs(vol) > 1e-9


def test_sketch_arc_xml_roundtrip(tmp_path):
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    plane = cab_sketch.default_sketch_plane(m)
    cab_sketch.apply_plane(m, plane)
    arc = cab_sketch.SketchProfile(
        geometry_type="arc", center=(3.0, 4.0), radius=7.5,
        divisions=20, start_angle=30.0, end_angle=210.0)
    assert cab_sketch.register_sketch_part(
        m, name="ArcPart1", plane=plane, profile=arc,
        model_type="extrusion", thickness_mm=5.0)
    loaded = cab_sketch.read_sketch_part(m, "ArcPart1")
    assert loaded is not None
    profile, _meta = loaded
    assert profile.geometry_type == "arc"
    assert profile.center == (3.0, 4.0)
    assert profile.radius == 7.5
    assert profile.start_angle == 30.0 and profile.end_angle == 210.0


# ------------------------------------------------- SK-2: editing tools

def test_move_and_mirror_profile():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(10.0, 6.0))
    moved = cab_sketch.move_profile(rect, 5.0, -2.0)
    assert moved.location == (5.0, -2.0)
    assert np.allclose(_poly(moved).min(0), (5.0, -2.0))
    mir = cab_sketch.mirror_profile(moved, axis="u", pivot=0.0)
    assert np.allclose(_poly(mir)[:, 0].max(), -5.0)


def test_rotate_rectangle_to_point_sequence():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(10.0, 4.0))
    rot = cab_sketch.rotate_profile(rect, 90.0)
    assert rot.geometry_type == "point_sequence"
    # CCW 90° about bbox centre (5,2): corner (10,0) -> (7,7)
    assert any(abs(u - 7.0) < 1e-9 and abs(v - 7.0) < 1e-9
               for u, v in rot.points)


def test_offset_profile_grows():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(10.0, 10.0))
    grown = cab_sketch.offset_profile(rect, 2.0)
    pts = _poly(grown)
    assert np.allclose(pts.min(0), (-2.0, -2.0))
    assert np.allclose(pts.max(0), (12.0, 12.0))
    shrunk = cab_sketch.offset_profile(rect, -2.0)
    pts2 = _poly(shrunk)
    assert np.allclose(pts2.min(0), (2.0, 2.0))


def test_clip_profile_trims():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(10.0, 10.0))
    half = cab_sketch.clip_profile(rect, "u", 5.0, keep_positive=True)
    pts = _poly(half)
    assert pts[:, 0].min() == pytest.approx(5.0)
    assert pts[:, 0].max() == pytest.approx(10.0)
    # area halved
    assert cab_sketch._signed_area_uv(pts) == pytest.approx(50.0, rel=0.01)


def test_fillet_profile_vertex_rounds_corner():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(10.0, 10.0))
    fil = cab_sketch.fillet_profile_vertex(rect, 2, 2.0)
    # the corner vertex is replaced by 6 bezier samples (8-2 interior pts)
    assert len(fil.points) == 4 - 1 + 6
    # rounded corner no longer contains the original (10,10) corner
    assert not any(abs(u - 10.0) < 1e-9 and abs(v - 10.0) < 1e-9
                   for u, v in fil.points)


# --------------------------------------------- SK-3: dimension driving

def test_profile_dimensions_rect_and_circle():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(12.0, 8.0))
    dims = cab_sketch.profile_dimensions(rect)
    kinds = {d["kind"]: d["value"] for d in dims}
    assert kinds == {"width": 12.0, "height": 8.0}
    circ = cab_sketch.SketchProfile(geometry_type="circle", radius=3.5)
    kinds = {d["kind"]: d["value"] for d in
             cab_sketch.profile_dimensions(circ)}
    assert kinds == {"radius": 3.5}


def test_apply_dimension_one_way_drives():
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(10.0, 10.0))
    wide = cab_sketch.apply_dimension(rect, "width", 25.0)
    assert wide.size == (25.0, 10.0)
    assert {d["kind"]: d["value"] for d in
            cab_sketch.profile_dimensions(wide)}["width"] == 25.0
    circ = cab_sketch.SketchProfile(geometry_type="circle", radius=5.0)
    grown = cab_sketch.apply_dimension(circ, "radius", 9.0)
    assert grown.radius == 9.0
    # point-sequence edge drive scales the end vertex along the edge
    tri = cab_sketch.SketchProfile(
        geometry_type="point_sequence",
        points=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], close=True)
    long_ = cab_sketch.apply_dimension(tri, "length", 20.0, index=0)
    assert long_.points[1] == (20.0, 0.0)
    assert long_.points[2] == (10.0, 10.0)


# ------------------------------------------ SK-4: missing model types

def test_dialog_has_nine_model_types(qapp):
    try:
        from PyQt5.QtWidgets import QApplication
        import sys
    except Exception:
        pytest.skip("PyQt5 not available")
    QApplication.instance() or QApplication([sys.argv[0]])
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    cab_sketch.apply_plane(m, cab_sketch.default_sketch_plane(m))
    dlg = cab_sketch.SketchPartDialog(m, None)
    try:
        items = [dlg.model_type.itemText(i)
                 for i in range(dlg.model_type.count())]
        for mt in ("Extrusion to selected part", "Face Division",
                   "Slit Punching", "Extrusion", "Panel", "Cutout"):
            assert mt in items
        assert dlg.model_type.count() == 9
        # target selection enabled for all target-needing types
        for mt in ("Cutout", "Extrusion to selected part",
                   "Face Division", "Slit Punching"):
            dlg.model_type.setCurrentText(mt)
            assert dlg.cutout_target.isEnabled(), mt
        dlg.model_type.setCurrentText("Extrusion")
        assert not dlg.cutout_target.isEnabled()
    finally:
        dlg.close()
        dlg.deleteLater()


def test_new_model_types_register_and_tessellate():
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    plane = cab_sketch.default_sketch_plane(m)
    cab_sketch.apply_plane(m, plane)
    rect = cab_sketch.SketchProfile(geometry_type="rectangle",
                                    location=(0.0, 0.0), size=(8.0, 8.0))
    for mt in ("Extrusion to selected part", "Face Division",
               "Slit Punching"):
        name = mt.replace(" ", "") + "1"
        assert cab_sketch.register_sketch_part(
            m, name=name, plane=plane, profile=rect, model_type=mt,
            thickness_mm=5.0, cutout_target="P1")
        loaded = cab_sketch.read_sketch_part(m, name)
        assert loaded is not None
        _profile, meta = loaded
        assert meta["model_type"] == mt
        assert meta["cutout_target"] == "P1"
        part = cab_sketch.sketch_tess(plane, rect, mt, 5.0)
        assert part.triangles.shape[0] > 0

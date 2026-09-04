"""SK-3 (H4): spline sketch primitive — Catmull-Rom through control
points, XML round-trip, tessellation and dialog wiring."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from cab_sketch import SketchPlane, SketchProfile, profile_dimensions, \
    read_sketch_part, register_sketch_part, sketch_tess, \
    update_sketch_part
from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


@pytest.fixture(scope="module")
def qapp():
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([sys.argv[0]])
    yield app


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


CTRL = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def test_spline_polygon_samples_through_control_points():
    p = SketchProfile(geometry_type="spline", points=CTRL, divisions=8)
    poly = p.polygon()
    assert len(poly) == 4 * 8
    # Catmull-Rom interpolates the control points exactly
    for c in CTRL:
        assert min(abs(x - c[0]) + abs(y - c[1]) for x, y in poly) \
            < 1e-9
    # closed loop -> tessellatable (positive area)
    pts2 = np.asarray(poly, float)
    area = 0.5 * abs(np.sum(pts2[:, 0] * np.roll(pts2[:, 1], -1)
                            - np.roll(pts2[:, 0], -1) * pts2[:, 1]))
    assert area > 50.0  # inside the 10x10 control bbox


def test_spline_open_profile_closes_region():
    p = SketchProfile(geometry_type="spline", points=CTRL, divisions=6,
                      close=False)
    poly = p.polygon()
    assert poly[0] == CTRL[0]
    assert poly[-1] == CTRL[-1]
    assert len(poly) == 3 * 6 + 1


def test_spline_degenerate_fewer_than_three_points():
    p = SketchProfile(geometry_type="spline",
                      points=[(0.0, 0.0), (5.0, 5.0)])
    assert p.polygon() == [(0.0, 0.0), (5.0, 5.0)]


def test_spline_dimensions_report_control_bbox():
    p = SketchProfile(geometry_type="spline", points=CTRL)
    kinds = [(d["kind"], d["value"]) for d in profile_dimensions(p)]
    assert ("width", 10.0) in kinds and ("height", 10.0) in kinds


def test_spline_xml_roundtrip():
    """register -> read keeps geometry_type/points/divisions; update
    rewrites in place."""
    m = _model()
    plane = SketchPlane(origin=(0.0, 0.0, 0.0), u=(1.0, 0.0, 0.0),
                        v=(0.0, 1.0, 0.0), w=(0.0, 0.0, 1.0))
    profile = SketchProfile(geometry_type="spline", points=CTRL,
                            divisions=10)
    assert register_sketch_part(m, name="Spline1", plane=plane,
                                profile=profile,
                                model_type="extrusion",
                                thickness_mm=5.0)
    part = m.find_part("Spline1")
    assert part is not None
    read_profile, meta = read_sketch_part(m, "Spline1")
    assert read_profile.geometry_type == "spline"
    assert read_profile.divisions == 10
    assert len(read_profile.points) == 4
    for (x0, y0), (x1, y1) in zip(read_profile.points, CTRL):
        assert abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9
    assert meta["thickness"] == pytest.approx(5.0)
    profile2 = SketchProfile(geometry_type="spline",
                             points=[(0, 0), (20, 0), (10, 15)],
                             divisions=16)
    assert update_sketch_part(m, name="Spline1", plane=plane,
                              profile=profile2, model_type="extrusion",
                              thickness_mm=7.0)
    read2, _meta2 = read_sketch_part(m, "Spline1")
    assert read2.divisions == 16
    assert len(read2.points) == 3


def test_spline_tessellation_watertight():
    """spline profile tessellates into a closed prism."""
    m = _model()
    plane = SketchPlane(origin=(0.0, 0.0, 0.0), u=(1.0, 0.0, 0.0),
                        v=(0.0, 1.0, 0.0), w=(0.0, 0.0, 1.0))
    profile = SketchProfile(geometry_type="spline", points=CTRL,
                            divisions=8)
    tess = sketch_tess(plane, profile, "extrusion", 5.0)
    pts = np.asarray(tess.points)
    tris = np.asarray(tess.triangles)
    assert tris.shape[1] == 3 and len(pts) == 2 * len(profile.polygon())
    # every edge appears exactly twice (watertight)
    edges = {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (min(a, b), max(a, b))
            edges[key] = edges.get(key, 0) + 1
    assert set(edges.values()) == {2}


def test_sk_dialog_spline_option(qapp):
    """Geometry combo carries Spline; selecting it shows the point table
    and sampling spin; _profile() returns a spline profile."""
    from cab_sketch import SketchPartDialog
    from cabxml import new_property_bytes as _npb
    m = _model()
    props = PropertyModel(parse_property(_npb()))
    dlg = SketchPartDialog(m, props)
    idx = dlg.geometry_type.findText("Spline")
    assert idx >= 0
    dlg.geometry_type.setCurrentIndex(idx)
    dlg.show()
    assert dlg.points_table.isVisibleTo(dlg)
    assert dlg.spline_div.isVisibleTo(dlg)
    assert dlg.accepts_plane_picks()
    from PyQt5.QtWidgets import QTableWidgetItem
    dlg.points_table.setRowCount(3)
    for r, (u, v) in enumerate([(0, 0), (10, 0), (5, 8)]):
        dlg.points_table.setItem(r, 1, QTableWidgetItem(str(u)))
        dlg.points_table.setItem(r, 2, QTableWidgetItem(str(v)))
    prof = dlg._profile()
    assert prof.geometry_type == "spline"
    assert prof.divisions == dlg.spline_div.value()
    assert len(prof.points) == 3

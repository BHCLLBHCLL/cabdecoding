"""M3: gridding tests (cab_grid algorithms + XML write-back)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

import cab_grid
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
EX4E = ROOT / "tests" / "ex4_e" / "ex4_e.xml"


def _spec(**kw) -> cab_grid.GridSpec:
    base = dict(
        domain_min=(-100.0, -100.0, -100.0),
        domain_max=(150.0, 300.0, 315.0),
    )
    base.update(kw)
    return cab_grid.GridSpec(**base)


def _box_points():
    return {"box": np.array([
        [0.0, 0.0, 0.0], [0.0, 0.0, 10.0], [0.0, 10.0, 0.0],
        [0.0, 10.0, 10.0], [10.0, 0.0, 0.0], [10.0, 0.0, 10.0],
        [10.0, 10.0, 0.0], [10.0, 10.0, 10.0]], dtype=float)}


def test_rough_minmax_and_all():
    pts = {"p": np.array([[0., 0., 0.], [5., 5., 5.], [10., 10., 10.]])}
    spec = _spec(vertex_detection="minmax")
    r = cab_grid.rough_grids(pts, spec)
    np.testing.assert_allclose(r["x"], [-100.0, 0.0, 10.0, 150.0])
    spec2 = _spec(vertex_detection="all")
    r2 = cab_grid.rough_grids(pts, spec2)
    np.testing.assert_allclose(r2["x"], [-100.0, 0.0, 5.0, 10.0, 150.0])


def test_rough_uniform_and_not_considered():
    pts = _box_points()
    spec = _spec(vertex_detection="uniform")
    r = cab_grid.rough_grids(pts, spec)
    assert r["x"] == [-100.0, 150.0]
    # STpre probe (tr03 vd4 == vd3): not_considered keeps part min/max
    # planes, only vertex detection is skipped.
    spec2 = _spec(vertex_detection="not_considered")
    r2 = cab_grid.rough_grids(pts, spec2)
    assert r2["x"] == [-100.0, 0.0, 10.0, 150.0]
    spec3 = _spec(vertex_detection="minmax")
    r3 = cab_grid.rough_grids(pts, spec3)
    assert r3["x"] == r2["x"]


def test_rough_threshold_unifies_close_lines():
    pts = {"p": np.array([[0., 0., 0.], [1.0, 0., 0.],
                          [1.05, 0., 0.], [10., 0., 0.]])}
    spec = _spec(vertex_detection="all", threshold_length=0.5)
    r = cab_grid.rough_grids(pts, spec)
    # 1.0 and 1.05 are within the 0.5 threshold -> unified
    assert 1.05 not in r["x"]
    assert r["x"] == [-100.0, 0.0, 1.0, 10.0, 150.0]


def test_refine_geometric_ratio():
    rough = {"x": [-100.0, 0.0, 50.0, 150.0],
             "y": [-100.0, 300.0], "z": [-100.0, 315.0]}
    spec = _spec(method="rough_and_detail",
                 standard_length=10.0, threshold_length=0.1,
                 geometric_ratio=1.0, geometric_ratio_external=1.2)
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([50.0, 200.0, 200.0])
    axes = cab_grid.refine_grids(rough, spec, part_bounds=(lo, hi))
    x = np.asarray(axes["x"])
    # external region [-100, 0]: geometric series dense at the part side
    ext = x[(x >= -100.0) & (x <= 0.0)]
    gaps = np.diff(ext)
    assert gaps[-1] == pytest.approx(10.0, abs=1e-6)  # adjacent to part = std
    assert gaps[0] > gaps[-1]
    # constant actual ratio (solved so the series exactly fills the interval)
    assert gaps[-2] / gaps[-1] == pytest.approx(
        gaps[-3] / gaps[-2], rel=1e-6)
    # internal region [0, 50]: equal split by standard length 10
    internal = x[(x >= 0.0) & (x <= 50.0)]
    ig = np.diff(internal)
    assert np.allclose(ig, 10.0)


def test_refine_num_elements():
    rough = {"x": [-100.0, 150.0], "y": [-100.0, 300.0],
             "z": [-100.0, 315.0]}
    spec = _spec(method="num_elements", target_elements=1000)
    axes = cab_grid.refine_grids(rough, spec)
    total = np.prod([len(v) - 1 for v in axes.values()])
    assert abs(total - 1000) / 1000 < 0.35
    for vals in axes.values():
        assert vals == sorted(vals)


def test_set_mesh_roundtrip():
    model = StpreModel(parse_stpre(EX4E.read_bytes()))
    axes = {
        "x": [-100.0, 0.0, 10.0, 150.0],
        "y": [-100.0, 50.0, 300.0],
        "z": [-100.0, 315.0],
    }
    model.set_mesh(
        axes, domain_min=(-100.0, -100.0, -100.0),
        domain_max=(150.0, 300.0, 315.0),
        threshold=(0.1, 0.1, 0.1), ratio=(1.2, 1.2, 1.2),
        detection=3, method=1,
        part_min=(0.0, 0.0, 0.0), part_max=(50.0, 200.0, 15.0))
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    got = reparsed.mesh_axes()
    assert len(got["x"]) == 4
    assert len(got["y"]) == 3
    assert len(got["z"]) == 2
    np.testing.assert_allclose(got["x"], [-100.0, 0.0, 10.0, 150.0])
    mc = reparsed.doc.root.find("mesh_control")
    grid = mc.find("block/grid")
    assert grid is not None and grid.text.strip() == "4,3,2"


def test_gridding_dialog_smoke(qapp):
    import cab_import
    pytest.importorskip("cab_gui")
    import cab_gui
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    from cab_container import CabArchive
    archive = CabArchive.parse(
        (ROOT / "tests" / "box.cab").read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    bodies = cab_import.import_xt_file(ROOT / "tests" / "box" / "box_all.x_t")
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = [b.tess for b in bodies]
    dlg = cab_gui._GriddingDialog(model, viewer._cad_meshes, viewer)
    dlg.detection_radios["minmax"].setChecked(True)
    dlg._apply()
    axes = model.mesh_axes()
    assert len(axes["x"]) >= 2
    dlg.close()


def test_refine_matches_stpre_golden_external():
    """ex4_e golden: domain -100..150, part x in [0,50], std=1, ratio=1.2.
    The external interval -100..0 gets 17 geometric gaps (first = 1.0)."""
    rough = {"x": [-100.0, 0.0, 50.0, 150.0],
             "y": [-100.0, 0.0, 200.0, 300.0],
             "z": [-100.0, 0.0, 200.0, 315.0]}
    spec = _spec(method="rough_and_detail",
                 standard_length=1.0, threshold_length=0.1,
                 geometric_ratio=1.2)
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([50.0, 200.0, 200.0])
    axes = cab_grid.refine_grids(rough, spec, part_bounds=(lo, hi))
    x = np.asarray(axes["x"])
    ext = x[(x >= -100.0) & (x <= 0.0)]
    assert len(ext) == 18  # 17 gaps + boundary
    assert ext[0] == pytest.approx(-100.0)
    assert ext[-1] == pytest.approx(0.0)
    assert np.diff(ext)[-1] == pytest.approx(1.0)


def test_refine_num_elements_stpre_noncube_counts():
    """SetElementNum disassembly: 100x50x25 domain, N=8000 -> 40x20x10."""
    rough = {"x": [0.0, 100.0], "y": [0.0, 50.0], "z": [0.0, 25.0]}
    spec = _spec(
        domain_min=(0.0, 0.0, 0.0), domain_max=(100.0, 50.0, 25.0),
        method="num_elements", target_elements=8000)
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([10.0, 10.0, 10.0])
    axes = cab_grid.refine_grids(rough, spec, part_bounds=(lo, hi))
    assert [len(v) - 1 for v in axes.values()] == [40, 20, 10]


def test_refine_num_elements_stpre_base_layout():
    """M17 closed form: domain -25..25, part 0..10, n=20 -> P=6/L=8/R=6."""
    rough = {"x": [-25.0, 25.0], "y": [-25.0, 25.0],
             "z": [-25.0, 25.0]}
    spec = _spec(
        domain_min=(-25.0, -25.0, -25.0),
        domain_max=(25.0, 25.0, 25.0),
        method="num_elements", target_elements=8000,
        geometric_ratio_external=(1.2, 1.2, 1.2))
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([10.0, 10.0, 10.0])
    axes = cab_grid.refine_grids(rough, spec, part_bounds=(lo, hi))
    x = np.asarray(axes["x"])
    assert len(x) == 21
    inner = x[(x >= 0.0) & (x <= 10.0)]
    assert len(inner) == 7                     # 6 inner cells
    np.testing.assert_allclose(np.diff(inner), 10.0 / 6.0)
    left = x[x <= 0.0]
    assert len(left) == 9                      # 8 outer cells + boundary


def test_inner_symmetric_ratio_matches_probe():
    rough = {"x": [-25.0, 0.0, 10.0, 25.0],
             "y": [-25.0, 25.0], "z": [-25.0, 25.0]}
    spec = _spec(
        domain_min=(-25.0, -25.0, -25.0),
        domain_max=(25.0, 25.0, 25.0),
        standard_length=1.0, geometric_ratio=1.2,
        geometric_ratio_external=(1.2, 1.2, 1.2))
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([10.0, 10.0, 10.0])
    axes = cab_grid.refine_grids(rough, spec, part_bounds=(lo, hi))
    x = np.asarray(axes["x"])
    inner = x[(x >= 0.0) & (x <= 10.0)]
    g = np.diff(inner)
    # probe: 1, 1.285, 1.653, 2.124, 1.653, 1.285, 1 (symmetric)
    assert len(g) == 7
    np.testing.assert_allclose(g[0], 1.0, atol=1e-6)
    np.testing.assert_allclose(g, g[::-1], atol=1e-9)
    assert g[1] > g[0] and g[2] > g[1]


def test_uniform_mode_ignores_part_bounds():
    """STpre \"uniform\" divides the whole domain by std and ignores the part.

    part_bounds must NOT turn the single interval into an external geometric
    region (which used to collapse the axis to ~18 points instead of 91).
    """
    spec = _spec(
        domain_min=(-20.0, -20.0, -20.0), domain_max=(70.0, 120.0, 120.0),
        vertex_detection="uniform", method="rough_and_detail",
        standard_length=1.0, threshold_length=0.1,
        geometric_ratio=1.0, geometric_ratio_external=1.2)
    pts = {"p": np.array([[0., 0., 0.], [22.5, 47.5, 47.5]])}
    lo = np.array([-22.5, -47.5, -47.5])
    hi = np.array([22.5, 47.5, 47.5])
    _, d = cab_grid.build_axes(pts, spec, part_bounds=(lo, hi))
    assert len(d["x"]) == 91        # 90 cells
    assert len(d["y"]) == 141       # 140 cells
    assert len(d["z"]) == 141
    np.testing.assert_allclose(np.diff(d["x"]), 1.0)


def test_clip_dedupe_snaps_transform_noise():
    """A metres->mm part transform leaves ~1e-13 FP noise; the snap keeps a
    nominal 2.5 mm segment from flipping _trunc_round(2.5) 3 -> 2."""
    vals = [-20.0, 20.000000000000004, 22.49999999999999, 70.0]
    out = cab_grid._clip_dedupe(vals, -20.0, 70.0, tol=0.1)
    assert 20.0 in out and 22.5 in out
    # the snapped segment length is exactly 2.5 -> 3 intervals
    import stpre_rules
    assert stpre_rules._trunc_round(22.5 - 20.0) == 3


def test_cylindrical_axes_layout():
    """P2: cylindrical domain stores x=R / y=theta / z=Z tables."""
    rough = {"x": [0.0, 50.0], "y": [0.0, 360.0], "z": [0.0, 100.0]}
    spec = _spec(
        domain_min=(0.0, 0.0, 0.0), domain_max=(50.0, 360.0, 100.0),
        domain_coordinate="cylindrical",
        standard_length=5.0, threshold_length=0.1,
        geometric_ratio=1.0, geometric_ratio_external=1.0)
    lo = np.array([5.0, 0.0, 0.0])
    hi = np.array([15.0, 360.0, 80.0])
    _, d = cab_grid.build_axes(
        {"p": np.array([[5, 0, 0], [15, 0, 80]])}, spec,
        part_bounds=(lo, hi))
    y = np.asarray(d["y"])
    assert y[0] == 0.0 and y[-1] == 360.0
    np.testing.assert_allclose(np.diff(y), 360.0 / (len(y) - 1))
    assert d["x"][0] == 0.0 and d["x"][-1] == 50.0
    assert d["z"][0] == 0.0 and d["z"][-1] == 100.0


def test_cylindrical_axes_radial_internal_external_split():
    """P0-②: a part centred on the axis grids r=[0,r_out] internal and
    r=[r_out,r_max] external (geometric), NOT the cartesian x bounds."""
    spec = _spec(
        domain_min=(0.0, 0.0, 0.0), domain_max=(50.0, 360.0, 100.0),
        domain_coordinate="cylindrical",
        standard_length=5.0, threshold_length=0.1,
        geometric_ratio=1.0, geometric_ratio_external=1.2)
    # a ring of points at r=10 (centred on the axis: x^2+y^2=100)
    th = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
    pts = np.stack([10.0 * np.cos(th), 10.0 * np.sin(th),
                    np.full_like(th, 5.0)], axis=1)
    _, d = cab_grid.build_axes({"p": pts}, spec)
    x = np.asarray(d["x"])
    assert x[0] == 0.0 and x[-1] == 50.0
    # internal region [0, 10]: equal split by std=5 -> 3 points
    inner = x[x <= 10.0 + 1e-9]
    assert len(inner) == 3
    np.testing.assert_allclose(inner, [0.0, 5.0, 10.0])
    # external region [10, 50]: geometric, dense at the part side
    outer = x[x >= 10.0 - 1e-9]
    gaps = np.diff(outer)
    assert gaps[0] == pytest.approx(5.0, abs=1e-6)   # adjacent = std
    assert gaps[-1] > gaps[0]
    # theta is uniform over 0..360
    y = np.asarray(d["y"])
    assert y[0] == 0.0 and y[-1] == 360.0
    np.testing.assert_allclose(np.diff(y), 360.0 / (len(y) - 1))


def test_rough_grids_representative_uses_real_vertices():
    pts = {"p": np.array([[0., 0., 0.], [10., 10., 10.]])}
    verts = {"p": np.array([[-5., 2., 3.], [7., 8., 9.]])}
    spec = _spec(vertex_detection="representative")
    rough = cab_grid.rough_grids(pts, spec, part_vertices=verts)
    # B-rep topology vertices must appear even though the tessellation points
    # do not contain the -5 / 7 coordinates.
    assert -5.0 in rough["x"]
    assert 7.0 in rough["x"]
    assert 2.0 in rough["y"] and 8.0 in rough["y"]


def test_rough_grids_all_uses_tess_not_vertices():
    # STpre "All vertices" = every triangle-patch vertex (the display mesh),
    # NOT the B-rep topology vertices.  The B-rep vertex at -5 must be
    # ignored by "all" while the tess point at 5 is kept.
    pts = {"p": np.array([[0., 0., 0.], [5., 5., 5.], [10., 10., 10.]])}
    verts = {"p": np.array([[-5., 2., 3.], [7., 8., 9.]])}
    spec = _spec(vertex_detection="all")
    rough = cab_grid.rough_grids(pts, spec, part_vertices=verts)
    assert 5.0 in rough["x"]
    assert -5.0 not in rough["x"]
    assert 7.0 not in rough["x"]


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app

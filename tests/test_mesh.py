"""M4: meshing tests (cab_mesh occupancy + element write-back)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

import cab_mesh
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"


def _box_tess():
    import cab_import
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    return cab_import.import_xt_file(BOX_XT)[0].tess


def test_cylindrical_domain_radial_axes_and_full_theta_occupancy():
    """P0-②: cylindrical domain grids R with internal/external split and
    classifies a centred cylinder across the FULL theta span."""
    import cab_grid
    from cab_parts import PrimitivePart
    spec = cab_grid.GridSpec(
        unit="mm", domain_min=(0.0, 0.0, 0.0),
        domain_max=(50.0, 360.0, 100.0),
        domain_coordinate="cylindrical", vertex_detection="minmax",
        method="rough_and_detail", standard_length=5.0,
        threshold_length=0.1, geometric_ratio=1.0,
        geometric_ratio_external=1.2)
    nlon = 32
    th = np.linspace(0, 2 * np.pi, nlon, endpoint=False)
    pts = []
    for z in (20.0, 80.0):
        for t in th:
            pts.append([10 * np.cos(t), 10 * np.sin(t), z])
    tris = []
    for i in range(nlon):
        j = (i + 1) % nlon
        tris.append([i, j, nlon + i])
        tris.append([j, nlon + j, nlon + i])
    tess = PrimitivePart("cyl", np.array(pts, float) / 1000.0,
                         np.array(tris, int))
    _, axes = cab_grid.build_axes({"cyl": np.array(pts, float)}, spec)
    # R: internal [0,10] = 3 points, external [10,50] geometric
    x = np.asarray(axes["x"])
    assert x[0] == 0.0 and x[-1] == 50.0
    np.testing.assert_allclose(x[x <= 10.0 + 1e-9], [0.0, 5.0, 10.0])
    gaps = np.diff(x[x >= 10.0 - 1e-9])
    assert gaps[0] == pytest.approx(5.0, abs=1e-6)
    assert gaps[-1] > gaps[0]
    # Z: internal [20,80] equal split
    z = np.asarray(axes["z"])
    np.testing.assert_allclose(z[(z >= 20.0 - 1e-9) & (z <= 80.0 + 1e-9)],
                               np.arange(20.0, 80.0 + 1e-9, 5.0))
    # occupancy spans the FULL theta (j) range
    _analysis, boxes = cab_mesh.classify_cells(
        axes, [tess], coordinate="cylindrical")
    assert "cyl" in boxes and len(boxes["cyl"]) == 1
    b = boxes["cyl"][0]
    assert b[2] == 1 and b[3] == len(axes["y"]) - 1   # all theta cells


def test_classify_box_full_domain():
    tess = _box_tess()
    axes = {ax: [i * 1.0 for i in range(11)] for ax in "xyz"}  # 0..10 mm
    analysis, boxes = cab_mesh.classify_cells(axes, [tess])
    assert analysis == (1, 10, 1, 10, 1, 10)
    assert "box" in boxes
    # the cube fills the whole domain: one merged box expected
    assert boxes["box"] == [(1, 10, 1, 10, 1, 10)]
    # multi-sample corners majority must agree with the center result
    _a2, boxes2 = cab_mesh.classify_cells(axes, [tess], samples="corners")
    c = boxes["box"][0]
    b = boxes2["box"][0]
    # conservative subset: no cell outside the center-classified box
    assert b[0] >= c[0] and b[1] <= c[1]
    assert b[2] >= c[2] and b[3] <= c[3]
    assert b[4] >= c[4] and b[5] <= c[5]


def test_classify_box_center_subset():
    tess = _box_tess()
    axes = {ax: [i * 1.0 for i in range(21)] for ax in "xyz"}  # 0..20 mm
    analysis, boxes = cab_mesh.classify_cells(axes, [tess])
    assert analysis == (1, 20, 1, 20, 1, 20)
    # box occupies cells 1..10 (centres 0.5..9.5 mm)
    assert boxes["box"] == [(1, 10, 1, 10, 1, 10)]


def test_apply_elements_roundtrip():
    from cab_container import CabArchive
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    tess = _box_tess()
    axes = {ax: [i * 1.0 for i in range(11)] for ax in "xyz"}
    analysis, boxes = cab_mesh.classify_cells(axes, [tess])
    cab_mesh.apply_elements(model, "Domain(cuboid)", analysis, boxes)
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    assert reparsed.analysis_boxes() == [[1, 10, 1, 10, 1, 10]]
    assert reparsed.part_boxes("box") == [[1, 10, 1, 10, 1, 10]]


def test_merge_boxes():
    mask = np.zeros((6, 6, 6), dtype=bool)
    mask[1:4, 2:4, 3:5] = True
    boxes = cab_mesh._merge_boxes(mask)
    assert boxes == [(2, 4, 3, 4, 4, 5)]


def test_meshing_dialog_smoke(qapp):
    import cab_import
    pytest.importorskip("cab_gui")
    import cab_gui
    import cab_grid
    from cab_container import CabArchive
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    bodies = cab_import.import_xt_file(BOX_XT)
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = [b.tess for b in bodies]
    spec = cab_grid.GridSpec(
        unit="mm", domain_min=(0, 0, 0), domain_max=(10, 10, 10),
        vertex_detection="uniform", method="rough_and_detail",
        standard_length=1.0, threshold_length=0.1, geometric_ratio=1.0)
    _r, axes = cab_grid.build_axes({}, spec)
    model.set_mesh(axes, domain_min=(0, 0, 0), domain_max=(10, 10, 10))
    viewer._meshing_dialog()
    assert model.analysis_boxes() == [[1, 10, 1, 10, 1, 10]]


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app

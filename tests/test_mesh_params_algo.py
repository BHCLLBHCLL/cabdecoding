"""L3: Others-tab meshing parameters affect native classification."""
from __future__ import annotations

import cab_mesh
from cab_parts import cube_tess, panel_tess


def _axes(mm_step: float = 1.0, n: int = 11):
    return {ax: [i * mm_step for i in range(n)] for ax in "xyz"}


def test_edge_eps_expands_solid_occupancy():
    """Thin slab 5.2..5.4 mm is empty without tolerance, occupied with it."""
    tess = cube_tess((5.2, 0.0, 0.0), (0.2, 10.0, 10.0))
    tess.name = "slab"
    _, boxes0 = cab_mesh.classify_cells(_axes(), [tess], edge_eps=0.0)
    _, boxes1 = cab_mesh.classify_cells(
        _axes(), [tess], edge_eps=0.00015)  # 0.15 mm
    assert not boxes0.get("slab")
    assert boxes1.get("slab")


def test_element_threshold_moves_reference_point():
    """Slab 4.0..4.8 mm: threshold 0.9 shifts the sample out of the part."""
    tess = cube_tess((4.0, 0.0, 0.0), (0.8, 10.0, 10.0))
    tess.name = "slab"
    _, boxes_mid = cab_mesh.classify_cells(
        _axes(), [tess], element_threshold=0.5)
    _, boxes_low = cab_mesh.classify_cells(
        _axes(), [tess], element_threshold=0.1)
    _, boxes_high = cab_mesh.classify_cells(
        _axes(), [tess], element_threshold=0.9)
    assert boxes_mid.get("slab")
    assert boxes_low.get("slab")
    assert not boxes_high.get("slab")


def test_face_search_scales_panel_band():
    """Panel at z=5 mm: tiny search range leaves no cells; 1.0 fills a band."""
    tess = panel_tess((0.0, 0.0, 5.0), (10.0, 10.0, 0.0), "+Z")
    tess.name = "P"
    _, boxes0 = cab_mesh.classify_cells(
        _axes(), [tess], part_kinds={"P": "panel"},
        part_attrs={"P": "panel"}, face_search=0.05)
    _, boxes1 = cab_mesh.classify_cells(
        _axes(), [tess], part_kinds={"P": "panel"},
        part_attrs={"P": "panel"}, face_search=1.0)
    assert not boxes0.get("P")
    assert boxes1.get("P")


def test_workers_parallel_same_result():
    """L7: threaded per-part classification must match serial output."""
    from cab_parts import cube_tess
    ta = cube_tess((0.0, 0.0, 0.0), (5.0, 5.0, 5.0))
    ta.name = "A"
    tb = cube_tess((5.0, 5.0, 5.0), (5.0, 5.0, 5.0))
    tb.name = "B"
    axes = {ax: [i * 1.0 for i in range(11)] for ax in "xyz"}
    _, b1 = cab_mesh.classify_cells(axes, [ta, tb], workers=1)
    _, b2 = cab_mesh.classify_cells(axes, [ta, tb], workers=2)
    assert set(b1) == set(b2) == {"A", "B"}
    for key in b1:
        assert b1[key] == b2[key]

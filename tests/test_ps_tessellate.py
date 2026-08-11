"""Tests for Parasolid .x_t tessellation (skip if no Cradle kernel)."""
from __future__ import annotations

from pathlib import Path

import pytest

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
CAB = ROOT / "tests" / "ex4_e.cab"
TR03 = ROOT / "tests" / "tr03.cab"
BOX = ROOT / "tests" / "box.cab"

ps_tessellate = pytest.importorskip("ps_tessellate")


@pytest.mark.skipif(not ps_tessellate.available(),
                    reason="Cradle pskernel.dll not installed")
def test_tessellate_ex4_e_bodies():
    raw = CAB.read_bytes()
    archive = CabArchive.parse(raw)
    archive.fill_member_data()
    xt = next(m.data for m in archive.members if m.name.endswith(".x_t"))
    parts = ps_tessellate.tessellate_xt(xt)
    assert len(parts) >= 20
    names = {p.name for p in parts}
    assert "lower_cover_01" in names
    assert "battery" in names
    cover = next(p for p in parts if p.name == "lower_cover_01")
    assert cover.triangles.shape[0] >= 100
    assert cover.points.shape[1] == 3
    # phone-scale extents (meters)
    mn, mx = cover.points.min(0), cover.points.max(0)
    assert mx[0] - mn[0] > 0.01
    assert mx[1] - mn[1] > 0.01


@pytest.mark.skipif(not ps_tessellate.available(),
                    reason="Cradle pskernel.dll not installed")
def test_attach_cad_to_part_boxes():
    import cab_vtk

    raw = CAB.read_bytes()
    archive = CabArchive.parse(raw)
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    model = StpreModel(parse_stpre(members["ex4_e.xml"]))
    xt = next(v for k, v in members.items() if k.endswith(".x_t"))
    tess = ps_tessellate.tessellate_xt(xt)
    boxes = cab_vtk.part_boxes(model, tess)
    with_cad = [b for b in boxes if b.cad_polydata is not None]
    assert len(with_cad) >= 20
    pd = cab_vtk.part_polydata(with_cad[0], for_part=True)
    assert pd.GetNumberOfPolys() > 0
    assert pd.GetPointData().GetNormals() is not None
    # Element path still returns box mesh
    pd_e = cab_vtk.part_polydata(with_cad[0], for_part=False)
    assert pd_e.GetNumberOfCells() > 0
    # CAD bodies are local in the .x_t; XML transform must place them on the
    # structured-mesh occupancy boxes (otherwise every part sits at origin).
    cover = next(b for b in boxes if b.name == "lower_cover_01")
    cell_bounds = cab_vtk._merge_bounds(
        cab_vtk._cells_from_element(model, cover.name))
    assert cell_bounds is not None
    for lo_cad, lo_cell, hi_cad, hi_cell in (
            (cover.bounds[0], cell_bounds[0], cover.bounds[3], cell_bounds[3]),
            (cover.bounds[1], cell_bounds[1], cover.bounds[4], cell_bounds[4]),
            (cover.bounds[2], cell_bounds[2], cover.bounds[5], cell_bounds[5])):
        assert abs(lo_cad - lo_cell) < 1e-5
        assert abs(hi_cad - hi_cell) < 1e-5


@pytest.mark.skipif(not ps_tessellate.available(),
                    reason="Cradle pskernel.dll not installed")
def test_tessellate_cad_only_no_element_mesh():
    """tr03 has no generated ``element`` occupancy yet; the x_t surface
    alone must still produce visible Part shading geometry."""
    import cab_vtk

    raw = TR03.read_bytes()
    archive = CabArchive.parse(raw)
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    model = StpreModel(parse_stpre(members["tr03.xml"]))
    assert {p.name for p in model.parts()} == {"Case", "Impeller", "Rotate"}
    tess = ps_tessellate.tessellate_xt(members["_tr03_all.x_t"])
    boxes = cab_vtk.part_boxes(model, tess)
    assert {b.name for b in boxes} == {"Case", "Impeller", "Rotate"}
    for box in boxes:
        assert not box.cells          # no element section
        assert box.cad_polydata is not None
        assert box.cad_polydata.GetPointData().GetNormals() is not None
        assert box.cad_polydata.GetNumberOfPolys() > 0


@pytest.mark.skipif(not ps_tessellate.available(),
                    reason="Cradle pskernel.dll not installed")
def test_tessellate_root_level_parts_no_group():
    """box.cab stores <parts> directly under <stpre> (no <group>) and its
    x_t body name must survive the SDL attribute scan."""
    import cab_vtk

    raw = BOX.read_bytes()
    archive = CabArchive.parse(raw)
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    model = StpreModel(parse_stpre(members["box.xml"]))
    assert [p.name for p in model.parts()] == ["box"]
    tess = ps_tessellate.tessellate_xt(members["_box_all.x_t"])
    assert [p.name for p in tess] == ["box"]
    boxes = cab_vtk.part_boxes(model, tess)
    assert [b.name for b in boxes] == ["box"]
    assert boxes[0].cad_polydata is not None
    assert boxes[0].cad_polydata.GetPointData().GetNormals() is not None

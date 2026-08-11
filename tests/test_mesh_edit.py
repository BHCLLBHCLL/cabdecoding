"""M6: cell editing / interferences / cross-section model helpers."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

import cab_grid
import cab_mesh
import cab_vtk
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


def _box_model() -> StpreModel:
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    return StpreModel(parse_stpre(xml_member.data))


def _meshed_model(n: int = 12) -> StpreModel:
    model = _box_model()
    axes = cab_grid.build_axes(
        {}, cab_grid.GridSpec(domain_min=(-50, -50, -50),
                              domain_max=(50, 50, 50),
                              method="rough_and_detail"))[1]
    model.set_mesh(axes, domain_min=(-50, -50, -50),
                   domain_max=(50, 50, 50), unit="mm")
    return model


def test_cell_mask_roundtrip():
    model = _meshed_model()
    ni = len(model.mesh_axes()["x"]) - 1
    mask = cab_mesh.cell_mask_from_boxes(
        ni, ni, ni, [(1, 3, 1, 3, 1, 3)])
    assert mask.shape == (ni, ni, ni)
    assert int(mask.sum()) == 27
    assert mask[0, 0, 0] and not mask[3, 3, 3]
    boxes = cab_mesh._boxes_from_mask(mask)
    assert boxes == [(1, 3, 1, 3, 1, 3)]


def test_toggle_cells_effective():
    model = _meshed_model()
    ni = len(model.mesh_axes()["x"]) - 1
    full = cab_mesh._boxes_from_mask(np.ones((ni, ni, ni), dtype=bool))
    cab_mesh.apply_elements(model, "Domain(cuboid)", (1, ni, 1, ni, 1, ni),
                            {"box": full})
    # remove a single corner cell (1,1,1)
    n = cab_mesh.toggle_cells_effective(model, "box", [(1, 1, 1)], False)
    boxes = model.part_boxes("box")
    cells = cab_mesh.cell_mask_from_boxes(ni, ni, ni, boxes)
    assert not cells[0, 0, 0]
    assert int(cells.sum()) == ni ** 3 - 1
    # add it back -> full occupancy
    n2 = cab_mesh.toggle_cells_effective(model, "box", [(1, 1, 1)], True)
    assert [list(b) for b in model.part_boxes("box")] == \
        [list(b) for b in full]
    # removing a corner cell splits the box into 3 residuals; re-adding
    # merges back into 1
    assert n == 3 and n2 == 1


def test_classify_interferences_states():
    model = _meshed_model()
    ni = len(model.mesh_axes()["x"]) - 1
    analysis_box = (1, ni, 1, ni, 1, ni)
    overlap = {"a": [(1, 5, 1, 5, 1, 5)], "b": [(4, 9, 4, 9, 4, 9)]}
    cab_mesh.apply_elements(model, "Domain(cuboid)", analysis_box, overlap)
    assert cab_mesh.classify_interferences(model) == \
        [("a", "b", "Interference")]

    contact = {"a": [(1, 5, 1, 5, 1, 5)], "b": [(5, 9, 1, 9, 1, 9)]}
    cab_mesh.apply_elements(model, "Domain(cuboid)", analysis_box, contact)
    assert cab_mesh.classify_interferences(model) == [("a", "b", "Contact")]

    sep = {"a": [(1, 3, 1, 3, 1, 3)], "b": [(6, 8, 6, 8, 6, 8)]}
    cab_mesh.apply_elements(model, "Domain(cuboid)", analysis_box, sep)
    assert cab_mesh.classify_interferences(model) == \
        [("a", "b", "Separation")]


def test_element_section_data_fluid_and_part():
    model = _meshed_model()
    ni = len(model.mesh_axes()["x"]) - 1
    cab_mesh.apply_elements(
        model, "Domain(cuboid)", (1, ni, 1, ni, 1, ni),
        {"box": [(2, 5, 2, 5, 2, 5)]})
    cells, colors = cab_vtk.element_section_data(model, "x", 1, "show")
    # slice at i=1 is the first x layer: all fluid (box starts at i=2)
    assert len(cells) == ni ** 2
    assert all(pid == 0 for _q, pid in cells)
    # slice at i=3 passes through the box
    cells2, colors2 = cab_vtk.element_section_data(model, "x", 3, "show")
    ids = {pid for _q, pid in cells2}
    assert 0 in ids and 1 in ids
    assert colors2 and colors2[0][0] == "box"
    r, g, b = colors2[0][1]
    # box.cab part color is "25,117,255,255"
    assert r == pytest.approx(25 / 255) and g == pytest.approx(117 / 255) \
        and b == pytest.approx(1.0)
    # fluid-only slice excludes part cells
    cells_f, _c = cab_vtk.element_section_data(model, "x", 3, "fluid_only")
    assert all(pid == 0 for _q, pid in cells_f)
    assert len(cells_f) < len(cells2)


def test_element_section_bad_args():
    model = _meshed_model()
    cells, colors = cab_vtk.element_section_data(model, "x", 0, "show")
    assert cells == [] and colors == []


def test_parse_s_parts():
    import s_export
    model = _meshed_model()
    from cabxml import PropertyModel, parse_property
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    prop_member = next((m for m in archive.members
                        if m.name.endswith("_property.xml")), None)
    props = PropertyModel(parse_property(prop_member.data)) \
        if prop_member else None
    text = s_export.build_sdat(model, props)
    names = s_export.parse_s_parts(text)
    assert names and names[0] == "Domain(cuboid)"
    assert "box" in names

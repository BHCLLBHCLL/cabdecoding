"""M5: end-to-end workflow: import -> domain -> gridding -> meshing -> export."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cab_domain
import cab_grid
import cab_mesh
from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"
TR03 = ROOT / "tests" / "tr03.cab"


def _project(path: Path):
    archive = CabArchive.parse(path.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    prop_name = next(n for n in members if n.endswith("_property.xml"))
    xt_name = next(n for n in members if n.endswith(".x_t"))
    model = StpreModel(parse_stpre(members[xml_name]))
    props = PropertyModel(parse_property(members[prop_name]))
    return archive, model, props, members[xt_name]


def _mesh_project(xt_bytes, model, target=8000):
    import cab_import
    bodies = cab_import.import_xt_bytes(xt_bytes)
    assert bodies
    lo, hi = cab_domain.part_bounds(model, [b.tess for b in bodies])
    dmin = tuple(float(v) * 1000.0 for v in lo)
    dmax = tuple(float(v) * 1000.0 for v in hi)
    model.ensure_domain(
        base=dmin,
        size=tuple(b - a for a, b in zip(dmin, dmax)),
        material=model.domain_material() or "air(incompressible/20C)")
    spec = cab_grid.GridSpec(
        unit="mm", domain_min=dmin, domain_max=dmax,
        vertex_detection="minmax", method="num_elements",
        target_elements=target)
    part_points = {
        b.name: np.asarray(b.tess.points) * 1000.0 for b in bodies}
    _rough, axes = cab_grid.build_axes(part_points, spec)
    model.set_mesh(
        axes, unit="mm", domain_min=dmin, domain_max=dmax,
        threshold=(0.1, 0.1, 0.1), ratio=(1.2, 1.2, 1.2),
        detection=cab_grid.detection_index(spec),
        method=cab_grid.method_index(spec),
        part_min=dmin, part_max=dmax)
    analysis, boxes = cab_mesh.classify_cells(
        axes, [b.tess for b in bodies])
    cab_mesh.apply_elements(model, "Domain(cuboid)", analysis, boxes)
    return model, bodies, axes


def test_box_workflow_export():
    pytest.importorskip("cab_import")
    import cab_import
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    from s_export import build_sdat
    from xemt_export import build_emt
    archive, model, props, xt = _project(BOX)
    model, bodies, axes = _mesh_project(xt, model, target=1000)
    s = build_sdat(model, props)
    assert s.startswith("SDAT")
    assert "CXYZ" in s and "PARTS" in s
    emt = build_emt(model, props)
    assert "<EMT>" in emt
    # cab round-trip keeps element + mesh
    xml_member = next(m for m in archive.members
                      if m.name.endswith(".xml")
                      and not m.name.startswith("_"))
    xml_member.data = model.doc.serialize()
    again = CabArchive.parse(
        archive.to_bytes(preserve_source_blocks=False))
    again.fill_member_data()
    members2 = {m.name: m.data for m in again.members}
    xml2 = next(n for n in members2 if n.endswith(".xml")
                and not n.startswith("_"))
    model2 = StpreModel(parse_stpre(members2[xml2]))
    assert model2.analysis_boxes() == [[1, len(axes["x"]) - 1,
                                        1, len(axes["y"]) - 1,
                                        1, len(axes["z"]) - 1]]


def test_tr03_full_flow():
    pytest.importorskip("cab_import")
    import cab_import
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    from s_export import build_sdat
    archive, model, props, xt = _project(TR03)
    model, bodies, axes = _mesh_project(xt, model, target=4000)
    assert model.mesh_axes()
    assert model.analysis_boxes()
    assert any(model.part_boxes(b.name) for b in bodies)
    s = build_sdat(model, props)
    assert "CXYZ" in s and "PARTS" in s
    parts_section = s.split("PARTS", 1)[1] if "PARTS" in s else ""
    assert any(line.strip() for line in parts_section.splitlines())
    assert "Case" in parts_section

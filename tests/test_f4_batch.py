"""§25 F4 batch: gridding negative-conclusion cleanup — polygon parts
registered in body_files for the STpre relay, and multiblock x
cylindrical engine coverage."""
from __future__ import annotations

import numpy as np
import pytest

import cab_grid
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def test_polygon_parts_registered_in_body_files():
    """AM-3: a polygon part with an .stl member gains a body_files entry
    (STpre's own STL cab layout), idempotent."""
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="poly1", kind="polygon", attribute="solid",
               file_ref="poly1.stl")
    assert m.ensure_polygon_body_files() == 1
    assert m.ensure_polygon_body_files() == 0  # idempotent
    bf = m.doc.root.find("body_files")
    assert bf is not None
    entries = [(c.attrib.get("type"), (c.text or "").strip())
               for c in bf.findall("file")]
    assert ("stl", "poly1.stl") in entries


def test_polygon_registration_skips_non_stl():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="cube1", kind="cube", attribute="solid")
    assert m.ensure_polygon_body_files() == 0


def test_relay_cab_carries_polygon_body_files(tmp_path):
    """build_relay_cab runs ensure_polygon_body_files before copying."""
    from cab_container import CabArchive
    import cab_stpre_api
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="poly1", kind="polygon", attribute="solid",
               file_ref="poly1.stl")
    m.ensure_domain(base=(0.0, 0.0, 0.0), size=(50.0, 50.0, 50.0))
    from pathlib import Path
    arch = CabArchive.parse(
        (Path(__file__).resolve().parents[1] / "tests" / "ex4_e.cab")
        .read_bytes())
    arch.fill_member_data()
    src = tmp_path / "relay.cab"
    assert cab_stpre_api.build_relay_cab(m, arch, src)
    out = CabArchive.parse(src.read_bytes())
    out.fill_member_data()
    xml = next(mm.data for mm in out.members
               if mm.name.endswith(".xml"))
    assert b"poly1.stl" in xml


def test_multiblock_with_cylindrical_spec():
    """AM-3: build_axes_multiblock works with a cylindrical GridSpec —
    the nested-child combination the grid rules previously left
    unverified (engine-level coverage; STpre blackbox verification
    stays probe-dependent)."""
    from tests.test_mb_batch import _model_with_child, _spec
    m, meshes = _model_with_child()
    spec = _spec()
    spec.domain_coordinate = "cylindrical"
    pts = {t.name: np.asarray(t.points) * 1000.0 for t in meshes}
    blocks = m.mesh_blocks()
    rough, detailed, entries = cab_grid.build_axes_multiblock(
        pts, spec, blocks, part_bounds=(np.full(3, 60.0),
                                        np.full(3, 70.0)))
    # cylindrical axes carry the theta/r/z structure with child marks
    for ax in entries:
        assert entries[ax], ax
    assert any(abs(v - 10.0) < 1e-9 for v, _m in entries["x"])

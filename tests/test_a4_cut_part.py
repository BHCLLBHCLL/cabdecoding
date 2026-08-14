"""A4: all-operator x_t output — PK cut wiring + STL persistence fallback."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"

cab_edit_ops = pytest.importorskip("cab_edit_ops")
cab_ps_ops = pytest.importorskip("cab_ps_ops")
ps_facet2 = pytest.importorskip("ps_facet2_nodes")


def _box_archive() -> CabArchive:
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    return archive


def _xml_model(archive):
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    return StpreModel(parse_stpre(xml_member.data))


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_cut_part_by_plane_pk_registers_two_parts():
    archive = _box_archive()
    model = _xml_model(archive)
    tag, _ = cab_edit_ops._find_body_tags(model, archive, "box", "")
    assert tag is not None, "no body tag for box"
    sess = ps_facet2._get_session()
    tess = (sess.facet_body_adaptive(tag)
            or sess.facet2(tag) or sess.facet_go(tag))
    v0 = cab_ps_ops.mesh_volume_m3(tess.points, tess.triangles)
    pts = np.asarray(tess.points)
    lo, hi = pts.min(0), pts.max(0)
    mid_x = 0.5 * (lo[0] + hi[0])
    cad = []
    names = cab_edit_ops.cut_part_by_plane_pk(
        model, archive, cad, "box", (mid_x, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert names is not None and len(names) == 2, f"names={names}"
    assert model.find_part("box") is None, "original part not removed"
    vols = []
    for t in cad:
        vols.append(cab_ps_ops.mesh_volume_m3(t.points, t.triangles))
    assert len(vols) == 2 and all(v > 0 for v in vols)
    assert abs(sum(vols) - v0) / v0 < 0.05, f"v0={v0} vols={vols}"

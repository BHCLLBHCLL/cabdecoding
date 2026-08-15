"""Wrap -> x_t: wrap_part_pk produces a real convex-hull solid body."""
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


def _box_archive():
    a = CabArchive.parse(BOX.read_bytes())
    a.fill_member_data()
    return a


def _model(archive):
    xml = next(m for m in archive.members
               if m.name.endswith(".xml") and not m.name.startswith("_"))
    return StpreModel(parse_stpre(xml.data))


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_wrap_part_pk_box():
    archive = _box_archive()
    model = _model(archive)
    # build a cad_meshes list with the box tessellation (10 mm cube at origin)
    tag, _ = cab_edit_ops._find_body_tags(model, archive, "box", "")
    sess = ps_facet2._get_session()
    tess = sess.facet_body(tag) or sess.facet2(tag) or sess.facet_go(tag)
    tess.name = "box"
    cad = [tess]
    new = cab_edit_ops.wrap_part_pk(model, archive, cad, "box")
    assert new and new.startswith("box_wrap")
    assert model.find_part(new) is not None
    assert any(m.name == f"{new}.x_t" for m in archive.members)
    xt = next(m.data for m in archive.members if m.name == f"{new}.x_t")
    tags = sess.expand_to_bodies(sess.receive_xt(xt))
    assert tags
    pts = np.asarray((sess.facet_body(tags[0]) or sess.facet2(tags[0])
                      or sess.facet_go(tags[0])).points)
    # convex hull of a 10 mm cube -> same AABB [0, 0.01]^3
    assert pts.min(0)[0] == pytest.approx(0.0, abs=1e-5)
    assert pts.max(0)[0] == pytest.approx(0.01, abs=1e-5)
    assert pts.max(0)[2] == pytest.approx(0.01, abs=1e-5)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_wrap_part_pk_accuracy_clusters():
    archive = _box_archive()
    model = _model(archive)
    tag, _ = cab_edit_ops._find_body_tags(model, archive, "box", "")
    sess = ps_facet2._get_session()
    tess = sess.facet_body(tag) or sess.facet2(tag) or sess.facet_go(tag)
    tess.name = "box"
    cad = [tess]
    new = cab_edit_ops.wrap_part_pk(model, archive, cad, "box", accuracy=0.5)
    assert new and new.startswith("box_wrap")
    assert model.find_part(new) is not None
    assert any(m.name == f"{new}.x_t" for m in archive.members)

"""Transform GUI core: transform_part_pk applies PK transform and writes x_t."""
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
def test_transform_part_pk_translate():
    archive = _box_archive()
    model = _model(archive)
    tag, _ = cab_edit_ops._find_body_tags(model, archive, "box", "")
    assert tag is not None
    sess = ps_facet2._get_session()
    tess0 = (sess.facet_body(tag, facet_tol=1e-4, facet_angle_deg=12.0)
             or sess.facet2(tag) or sess.facet_go(tag))
    lo0 = np.asarray(tess0.points).min(0)
    ok = cab_edit_ops.transform_part_pk(
        model, archive, "box",
        lambda t: cab_ps_ops.body_transform_translate(t, 0.02, 0.0, 0.0))
    assert ok
    # the archive now has a box.x_t member and the part references it
    assert any(m.name == "box.x_t" for m in archive.members)
    assert "box.x_t" in model.body_files()
    # re-receive the new x_t and verify the translation
    xt = next(m.data for m in archive.members if m.name == "box.x_t")
    tags2 = sess.expand_to_bodies(sess.receive_xt(xt))
    assert tags2
    tess1 = (sess.facet_body(tags2[0], facet_tol=1e-4, facet_angle_deg=12.0)
             or sess.facet2(tags2[0]) or sess.facet_go(tags2[0]))
    lo1 = np.asarray(tess1.points).min(0)
    assert np.allclose(lo1 - lo0, [0.02, 0.0, 0.0], atol=1e-6), (lo0, lo1)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_mirror_copy_parts_pk():
    archive = _box_archive()
    model = _model(archive)
    cad = []
    created = cab_edit_ops.mirror_copy_parts_pk(
        model, archive, cad, ["box"], "X", 0.0)
    assert created, "mirror_copy_parts_pk returned no names"
    new_name = created[0]
    assert new_name.startswith("box_m")
    assert any(m.name == f"{new_name}.x_t" for m in archive.members)
    assert model.find_part(new_name) is not None
    xt = next(m.data for m in archive.members if m.name == f"{new_name}.x_t")
    sess = ps_facet2._get_session()
    tags = sess.expand_to_bodies(sess.receive_xt(xt))
    assert tags
    tess = (sess.facet_body(tags[0], facet_tol=1e-4, facet_angle_deg=12.0)
            or sess.facet2(tags[0]) or sess.facet_go(tags[0]))
    pts = np.asarray(tess.points)
    assert pts[:, 0].min() == pytest.approx(-0.01, abs=1e-5)
    assert pts[:, 0].max() == pytest.approx(0.0, abs=1e-5)
    assert pts[:, 1].min() == pytest.approx(0.0, abs=1e-5)
    assert pts[:, 2].max() == pytest.approx(0.01, abs=1e-5)

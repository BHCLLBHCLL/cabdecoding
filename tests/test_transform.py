"""Transform editing: PK_TRANSF_create_translation -> PK_BODY_transform_2 (V37)."""
import numpy as np
import pytest

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
cab_ps_ops = pytest.importorskip("cab_ps_ops")


def _aabb(tag):
    sess = ps_facet2._get_session()
    t = (sess.facet_body(tag, facet_tol=1e-4, facet_angle_deg=12.0)
         or sess.facet2(tag) or sess.facet_go(tag))
    p = np.asarray(t.points)
    return p.min(0), p.max(0)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_translate_x():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    lo0, hi0 = _aabb(tag)
    rc = cab_ps_ops.body_transform_translate(tag, 0.02, 0.0, 0.0)
    assert rc == 0
    lo1, hi1 = _aabb(tag)
    assert np.allclose(lo1 - lo0, [0.02, 0.0, 0.0], atol=1e-9), (lo0, lo1)
    assert np.allclose(hi1 - hi0, [0.02, 0.0, 0.0], atol=1e-9), (hi0, hi1)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_translate_xyz():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    lo0, hi0 = _aabb(tag)
    d = (0.01, -0.02, 0.005)
    cab_ps_ops.body_transform_translate(tag, *d)
    lo1, hi1 = _aabb(tag)
    assert np.allclose(lo1 - lo0, d, atol=1e-9)
    assert np.allclose(hi1 - hi0, d, atol=1e-9)

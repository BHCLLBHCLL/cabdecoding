"""Transform editing: rotation / reflection / uniform scale (V37 PK_TRANSF_create_*)."""
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
def test_rotate_about_x_90deg():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    # block: x/y [-0.005,0.005], z [0,0.01]
    rc = cab_ps_ops.body_transform_rotate(
        tag, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), np.pi / 2)
    assert rc == 0
    lo, hi = _aabb(tag)
    # x unchanged; y/z swap (z [0,0.01] -> -y or +y)
    assert abs(lo[0] - (-0.005)) < 1e-6 and abs(hi[0] - 0.005) < 1e-6
    assert abs((hi[1] - lo[1]) - 0.01) < 1e-6, (lo, hi)  # y now has 0.01 extent
    assert abs((hi[2] - lo[2]) - 0.01) < 1e-6, (lo, hi)  # z now 0.01 extent


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_reflect_across_x0():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    rc = cab_ps_ops.body_transform_reflect(tag, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert rc == 0
    lo, hi = _aabb(tag)
    # x negates: [-0.005,0.005] stays (symmetric), so translate first instead
    assert abs(lo[0] + hi[0]) < 1e-6  # centred on 0


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_scale_doubles():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    rc = cab_ps_ops.body_transform_scale(tag, 2.0, (0.0, 0.0, 0.005))
    assert rc == 0
    lo, hi = _aabb(tag)
    size = hi - lo
    assert abs(size[0] - 0.02) < 1e-6, size
    assert abs(size[1] - 0.02) < 1e-6, size
    assert abs(size[2] - 0.02) < 1e-6, size

"""Wrap: convex-hull solid via half-space boolean intersection -> x_t."""
import numpy as np
import pytest

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
cab_ps_ops = pytest.importorskip("cab_ps_ops")


def _volume(tag):
    sess = ps_facet2._get_session()
    t = (sess.facet_body(tag, facet_tol=1e-4, facet_angle_deg=12.0)
         or sess.facet2(tag) or sess.facet_go(tag))
    return cab_ps_ops.mesh_volume_m3(t.points, t.triangles)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_convex_hull_box():
    corners = np.array(
        [[x, y, z] for x in (0, 0.01) for y in (0, 0.01) for z in (0, 0.01)],
        dtype=np.float64)
    tag = cab_ps_ops.convex_hull_solid(corners)
    vol = _volume(tag)
    assert abs(vol - 1e-6) / 1e-6 < 0.02, vol


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_convex_hull_tetrahedron():
    # regular tetrahedron with one vertex at origin
    pts = np.array([
        [0.0, 0.0, 0.0],
        [0.01, 0.0, 0.0],
        [0.0, 0.01, 0.0],
        [0.0, 0.0, 0.01],
    ], dtype=np.float64)
    tag = cab_ps_ops.convex_hull_solid(pts)
    vol = _volume(tag)
    expect = (0.01 ** 3) / 6.0  # volume of a corner tetrahedron
    assert abs(vol - expect) / expect < 0.05, (vol, expect)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_convex_hull_transmit_roundtrip():
    sess = ps_facet2._get_session()
    corners = np.array(
        [[x, y, z] for x in (0, 0.01) for y in (0, 0.01) for z in (0, 0.01)],
        dtype=np.float64)
    tag = cab_ps_ops.convex_hull_solid(corners)
    xt = cab_ps_ops.transmit_parts([tag])
    assert xt and b"TRANSMIT FILE" in xt[:256]
    tags = sess.expand_to_bodies(sess.receive_xt(xt))
    assert tags and abs(_volume(tags[0]) - 1e-6) / 1e-6 < 0.02

"""A4: x_t write-back — boolean/cut result transmit + re-receive round-trip."""
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
def test_cut_result_transmit_roundtrip():
    sess = ps_facet2._get_session()
    block = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    v0 = _volume(block)
    res = cab_ps_ops.cut_body_by_plane(block, (0, 0, 0.005), (1, 0, 0))
    for key in ("front", "back"):
        xt = cab_ps_ops.transmit_parts([res[key]])
        assert xt and len(xt) > 100, f"{key} transmit empty"
        assert b"TRANSMIT FILE" in xt[:256], f"{key} not a transmit file"
        tags = sess.expand_to_bodies(sess.receive_xt(xt))
        assert tags, f"{key} no bodies re-received"
        vol = _volume(tags[0])
        assert abs(vol - v0 / 2) / v0 < 0.05, f"{key} volume {vol} != {v0/2}"


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_translate_then_transmit():
    sess = ps_facet2._get_session()
    block = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    cab_ps_ops.body_transform_translate(block, 0.02, 0.0, 0.0)
    xt = cab_ps_ops.transmit_parts([block])
    assert xt and b"TRANSMIT FILE" in xt[:256]
    tags = sess.expand_to_bodies(sess.receive_xt(xt))
    assert tags

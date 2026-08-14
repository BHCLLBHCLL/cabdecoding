"""A3: PK-level plane cut (cut_body_by_plane) via PK_BODY_boolean_2."""
import numpy as np
import pytest

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
cab_ps_ops = pytest.importorskip("cab_ps_ops")


def _body_volume_m3(tag):
    sess = ps_facet2._get_session()
    tess = (sess.facet_body_adaptive(tag)
            or sess.facet2(tag) or sess.facet_go(tag))
    return cab_ps_ops.mesh_volume_m3(tess.points, tess.triangles)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_cut_box_by_x_plane_conserves_volume():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    v0 = _body_volume_m3(tag)
    res = cab_ps_ops.cut_body_by_plane(tag, (0.0, 0.0, 0.005), (1.0, 0.0, 0.0))
    vf = _body_volume_m3(res["front"])
    vb = _body_volume_m3(res["back"])
    assert vf > 0 and vb > 0, f"vf={vf} vb={vb}"
    assert abs(vf + vb - v0) / v0 < 0.05, f"v0={v0} vf={vf} vb={vb}"


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_cut_box_by_z_plane():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    v0 = _body_volume_m3(tag)
    res = cab_ps_ops.cut_body_by_plane(tag, (0.0, 0.0, 0.005), (0.0, 0.0, 1.0))
    vf = _body_volume_m3(res["front"])
    vb = _body_volume_m3(res["back"])
    assert vf > 0 and vb > 0
    assert abs(vf + vb - v0) / v0 < 0.05, f"v0={v0} vf={vf} vb={vb}"

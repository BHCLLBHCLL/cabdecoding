"""A2: PK_FACE_delete_2 wiring — face-plane matching + delete."""
import numpy as np
import pytest

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
cab_ps_ops = pytest.importorskip("cab_ps_ops")


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_match_plus_z_face():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    # block spans x/y [-0.005,0.005], z [0,0.01]; +Z face centroid at z=0.01
    ft = cab_ps_ops.match_face_by_plane(
        tag, (0.0, 0.0, 1.0), (0.0, 0.0, 0.01))
    assert ft is not None, "no +Z face matched"
    normal, origin = sess.face_plane(ft)
    assert abs(float(normal[2])) > 0.98, f"normal={normal}"
    assert abs(float(origin[2]) - 0.01) < 1e-6, f"origin={origin}"


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_match_minus_z_face():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    ft = cab_ps_ops.match_face_by_plane(
        tag, (0.0, 0.0, -1.0), (0.0, 0.0, 0.0))
    assert ft is not None, "no -Z face matched"
    normal, origin = sess.face_plane(ft)
    assert abs(float(normal[2])) > 0.98, f"normal={normal}"
    assert abs(float(origin[2])) < 1e-6, f"origin={origin}"


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_face_delete_cap_keeps_solid():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    ft = cab_ps_ops.match_face_by_plane(
        tag, (0.0, 0.0, 1.0), (0.0, 0.0, 0.01))
    assert ft is not None
    cab_ps_ops.face_delete([ft], heal="cap")  # must not raise
    # cap heals the hole; body remains a valid solid body (class 5006)
    assert sess.entity_class(tag) == ps_facet2.PK_CLASS_body

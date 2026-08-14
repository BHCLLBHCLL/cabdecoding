"""A1: B-rep topology query (faces / edges / vertices / face plane)."""
import numpy as np
import pytest

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
cab_ps_ops = pytest.importorskip("cab_ps_ops")


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_box_topology_counts():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    faces = sess.body_faces(tag)
    edges = sess.body_edges(tag)
    verts = sess.body_vertices(tag)
    assert faces is not None and len(faces) == 6, f"faces={faces}"
    assert edges is not None and len(edges) == 12, f"edges={edges}"
    assert verts is not None and len(verts) == 8, f"verts={verts}"


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_box_face_planes():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    faces = sess.body_faces(tag)
    assert faces is not None and len(faces) == 6
    planes = []
    for f in faces:
        pl = sess.face_plane(f)
        assert pl is not None, f"face {f} returned no plane"
        planes.append(pl)
    # Each face normal is axis-aligned; all six directions are covered.
    axes = set()
    for normal, origin in planes:
        normal = np.asarray(normal, dtype=np.float64)
        assert abs(float(np.linalg.norm(normal)) - 1.0) < 1e-6
        idx = int(np.argmax(np.abs(normal)))
        assert abs(abs(float(normal[idx])) - 1.0) < 1e-6, f"non-axis normal {normal}"
        assert float(np.abs(normal).sum()) < 1.0 + 1e-6
        axes.add((idx, "+" if normal[idx] > 0 else "-"))
    assert axes == {(0, "+"), (0, "-"), (1, "+"), (1, "-"), (2, "+"), (2, "-")}

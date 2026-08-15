"""B5: body_vertices via PK_VERTEX_ask_point -> PK_POINT_ask (correct coords)."""
from pathlib import Path

import numpy as np
import pytest

ps_facet2 = pytest.importorskip("ps_facet2_nodes")
cab_ps_ops = pytest.importorskip("cab_ps_ops")

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_box_vertex_coords():
    sess = ps_facet2._get_session()
    tag = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    v = sess.body_vertices(tag)
    assert v is not None and len(v) == 8
    # block spans x/y [-0.005, 0.005], z [0, 0.01]
    assert abs(v[:, 0].min() - (-0.005)) < 1e-9
    assert abs(v[:, 0].max() - 0.005) < 1e-9
    assert abs(v[:, 2].min()) < 1e-9
    assert abs(v[:, 2].max() - 0.01) < 1e-9
    # no denormal garbage
    assert np.all(np.abs(v) < 1.0)


@pytest.mark.skipif(not ps_facet2.available(), reason="pskernel not available")
def test_tr03_impeller_vertices_are_real():
    xt = ROOT / "tests" / "tr03" / "_tr03_all.x_t"
    if not xt.exists():
        pytest.skip("tr03 x_t fixture missing")
    sess = ps_facet2._get_session()
    tags = sess.expand_to_bodies(sess.receive_xt(xt.read_bytes()))
    assert tags
    imp = None
    for t in tags:
        if sess.body_name(t) == "Impeller":
            imp = t
            break
    if imp is None:
        imp = tags[0]
    v = sess.body_vertices(imp)
    assert v is not None and len(v) >= 8
    # finite, within a plausible domain (m), and NOT denormal garbage (~1e-322)
    assert np.all(np.isfinite(v))
    assert not np.any((np.abs(v) > 0) & (np.abs(v) < 1e-300)), \
        "vertex coords contain denormal garbage"
    assert np.all(np.abs(v) < 10.0)

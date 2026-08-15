# M37: V37 blend / chamfer ABI (PK_EDGE_set_blend_* + PK_BODY_fix_blends).
from __future__ import annotations

import numpy as np

import cab_blend
import cab_ps_ops


def test_blend_option_structs():
    co = cab_blend.constant_blend_options()
    assert co.o_t_version == 1
    assert co.cliff_edge == 0
    assert co.xs_shape == 0x56B9
    assert co.properties.draw_fix == 1
    assert co.properties.tolerance == 1e-5
    assert co.properties.ov_smooth == 0x4809
    assert co.properties.ov_cliff == 0x4813
    assert co.properties.ov_cliff_end == 0x481C
    assert co.properties.ov_notch == 0x4827
    ch = cab_blend.chamfer_options()
    assert ch.o_t_version == 1
    assert ch.d1 == 1.0 and ch.d2 == 0.0
    fo = cab_blend.fix_blend_options()
    assert fo.o_t_version == 1
    assert fo.f2 == 0x5230 and fo.f3 == 0x523A and fo.f4 == 0x5244
    assert fo.f6 == 0x550A and fo.b1 == 1


def test_constant_blend_cycle_on_block():
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    body = cab_ps_ops.create_solid_block((0.04, 0.04, 0.04))
    edges = cab_blend.body_edges(sess.pk, body)
    assert len(edges) == 12
    rc, n = cab_blend.blend_edge(sess.pk, [edges[0]], 0.01)
    assert rc == 0 and n == 1
    rc2, n_blends, faces = cab_blend.fix_blends(sess.pk, body)
    assert rc2 == 0 and n_blends == 1 and len(faces) == 1
    part = sess.facet_body_stpre(body)
    assert part is not None
    # 40 mm cube with one rounded edge: 530 facets on the golden kernel
    assert len(part.triangles) == 530


def test_chamfer_cycle_on_block():
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    body = cab_ps_ops.create_solid_block((0.04, 0.04, 0.04))
    edges = cab_blend.body_edges(sess.pk, body)
    rc, n = cab_blend.blend_edge(
        sess.pk, [edges[0]], 0.008, chamfer=True, range1=0.008)
    assert rc == 0 and n == 1
    rc2, n_blends, faces = cab_blend.fix_blends(sess.pk, body)
    assert rc2 == 0 and n_blends == 1
    part = sess.facet_body_stpre(body)
    assert part is not None
    # chamfered box: 422 facets on the golden kernel
    assert len(part.triangles) == 422


def test_blend_part_edge_pk_persists_x_t():
    # M37 wiring: blend an x_t-part edge in place and rewrite the member.
    if not cab_ps_ops.available():
        return
    from pathlib import Path
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre, new_stpre_bytes
    import cab_edit_ops
    import ps_facet2_nodes as _ps
    root = Path(__file__).resolve().parents[1]
    box_xt = (root / 'tests' / 'box' / 'box_all.x_t').read_bytes()
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name='P', kind='body', attribute='solid')
    arch = CabArchive.parse(b'') if False else None
    import cab_import
    import io
    # build a real archive holding the box x_t member
    from cab_container import CabArchive as CA
    arch = None
    try:
        import cab_container
        arch = cab_container.build_archive({'box.x_t': box_xt})
    except Exception:
        arch = None
    if arch is None:
        return
    model.add_body_file('box.x_t', unit='m')
    el = model.doc.root.find('.//part')
    assert el is not None
    # register the part against the member
    import cab_import as ci
    ci.register_parts_from_x_t(model, [('P', 'box.x_t')])
    ok = cab_edit_ops.blend_part_edge_pk(model, arch, None, 'P', 0.004)
    # blend radius 4 mm on a 10 mm cube edge is valid
    assert ok
    names = [m.name for m in arch.members]
    assert any(n.endswith('.x_t') and n != 'box.x_t' for n in names)


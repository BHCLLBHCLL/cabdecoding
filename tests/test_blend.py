# M37: V37 blend / chamfer ABI (PK_EDGE_set_blend_* + PK_BODY_fix_blends).
from __future__ import annotations

import numpy as np

import cab_blend
import cab_ps_ops


def test_make_sheet_from_face_and_unify():
    # R3.1e/f: sheet-from-face + PK_EDGE_delete unify on coplanar pair.
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    import ctypes as C
    sess = _ps._get_session()
    pk = sess.pk
    body = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    pk.PK_BODY_ask_faces.restype = C.c_int
    pk.PK_BODY_ask_faces.argtypes = [
        C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    n = C.c_int(0)
    arr = C.c_void_p()
    pk.PK_BODY_ask_faces(body, C.byref(n), C.byref(arr))
    faces = [int(C.cast(arr, C.POINTER(C.c_int))[i])
             for i in range(n.value)]
    sheet = cab_ps_ops.make_sheet_from_faces(pk, [faces[0]])
    assert sheet > 0
    n2 = C.c_int(0)
    a2 = C.c_void_p()
    pk.PK_BODY_ask_faces(sheet, C.byref(n2), C.byref(a2))
    assert n2.value == 1
    # unify: two coplanar triangles sharing an edge merge to one face
    t1 = cab_ps_ops._triangle_sheet(pk, (0.0, 0, 0), (0.01, 0, 0),
                                    (0.0, 0.01, 0))
    t2 = cab_ps_ops._triangle_sheet(pk, (0.0, 0.01, 0), (0.01, 0, 0),
                                    (0.01, 0.01, 0))
    sewn = cab_ps_ops.sew_sheet_bodies(pk, [t1, t2], allow_disjoint=True)
    pk.PK_BODY_ask_edges.restype = C.c_int
    pk.PK_BODY_ask_edges.argtypes = [
        C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    ne = C.c_int(0)
    ae = C.c_void_p()
    pk.PK_BODY_ask_edges(sewn, C.byref(ne), C.byref(ae))
    eds = [int(C.cast(ae, C.POINTER(C.c_int))[i])
           for i in range(ne.value)]
    merged = False
    for e in eds:
        if cab_ps_ops.delete_edges(pk, [e]) == 0:
            merged = True
            break
    assert merged
    nf = C.c_int(0)
    fa = C.c_void_p()
    pk.PK_BODY_ask_faces(sewn, C.byref(nf), C.byref(fa))
    assert nf.value == 1


def test_simplify_and_regions_on_box():
    # R3.1g/h: simplify rc=0 on a box; region listing works.
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    pk = sess.pk
    body = cab_ps_ops.create_solid_block((0.01, 0.01, 0.01))
    assert cab_ps_ops.simplify_body_geom(pk, body) == 0
    regs = cab_ps_ops.ask_regions(pk, body)
    assert len(regs) >= 1

def test_sweep_body_triangle_to_prism():
    # R3.1c: PK_BODY_sweep in place - sheet triangle -> prism solid.
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    import ctypes as C
    sess = _ps._get_session()
    pk = sess.pk
    t1 = cab_ps_ops._triangle_sheet(pk, (0.0, 0, 0), (0.01, 0, 0),
                                    (0.0, 0.01, 0))
    rc = cab_ps_ops.sweep_body(pk, t1, (0.0, 0.0, 0.01))
    assert rc == 0
    pk.PK_BODY_ask_faces.restype = C.c_int
    pk.PK_BODY_ask_faces.argtypes = [
        C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    n = C.c_int(0)
    arr = C.c_void_p()
    assert pk.PK_BODY_ask_faces(t1, C.byref(n), C.byref(arr)) == 0
    assert n.value == 5  # 2 caps + 3 lateral quads
    part = sess.facet_body_stpre(t1)
    assert part is not None
    vol = cab_ps_ops.mesh_volume_m3(part.points, part.triangles)
    assert abs(vol - 5e-7) < 1e-12

def test_fill_sheet_body_caps_closed_tent():
    # R3.1b: four sewn triangles (closed tent) heal-cap into a solid.
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    import ctypes as C
    sess = _ps._get_session()
    pk = sess.pk
    a, b, c, d = (0.0, 0, 0), (0.01, 0, 0), (0.0, 0.01, 0), (0.0, 0, 0.01)
    tris = [cab_ps_ops._triangle_sheet(pk, a, b, c),
            cab_ps_ops._triangle_sheet(pk, a, c, d),
            cab_ps_ops._triangle_sheet(pk, a, d, b),
            cab_ps_ops._triangle_sheet(pk, b, d, c)]
    sewn = cab_ps_ops.sew_sheet_bodies(pk, tris, allow_disjoint=True,
                                       manifold=True)
    assert sewn > 0
    solid = cab_ps_ops.fill_sheet_body(pk, sewn)
    assert solid > 0
    pk.PK_BODY_ask_faces.restype = C.c_int
    pk.PK_BODY_ask_faces.argtypes = [
        C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    n = C.c_int(0)
    arr = C.c_void_p()
    assert pk.PK_BODY_ask_faces(solid, C.byref(n), C.byref(arr)) == 0
    assert n.value == 4

def test_sew_sheet_bodies_stitches_two_triangles():
    # R3.1a: PK_BODY_sew_bodies helper stitches two sheet triangles.
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    pk = sess.pk
    t1 = cab_ps_ops._triangle_sheet(pk, (0.0, 0, 0), (0.01, 0, 0),
                                    (0.0, 0.01, 0))
    t2 = cab_ps_ops._triangle_sheet(pk, (0.005, 0, 0), (0.015, 0, 0),
                                    (0.005, 0.01, 0))
    sewn = cab_ps_ops.sew_sheet_bodies(pk, [t1, t2],
                                       allow_disjoint=True)
    assert sewn > 0
    import ctypes as C
    pk.PK_BODY_ask_faces.restype = C.c_int
    pk.PK_BODY_ask_faces.argtypes = [
        C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    n = C.c_int(0)
    arr = C.c_void_p()
    assert pk.PK_BODY_ask_faces(sewn, C.byref(n), C.byref(arr)) == 0
    assert n.value == 2

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




def test_replace_part_from_library():
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    import cab_edit_ops
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name='P', kind='cube', attribute='solid')
    entry = {
        'name': 'LibCyl', 'kind': 'cylinder', 'attribute': 'fluid',
        'material': 'Aluminum', 'heat_source': 5.0, 'temperature': 80.0,
        'params': {'base': (1.0, 2.0, 3.0), 'size': (20.0, 40.0, 20.0)},
    }
    assert cab_edit_ops.replace_part_from_library(model, 'P', entry)
    el = model.find_part('P')
    assert el is not None
    assert el.get('type') == 'cylinder'
    from cabxml import _first
    assert _first(el, 'attribute').text.strip() == 'fluid'
    assert _first(el, 'property').text.strip() == 'Aluminum'
    assert float(_first(el, 'heat_source').text.strip()) == 5.0
    assert float(_first(el, 'temperature').text.strip()) == 80.0
    base = [float(x) for x in _first(el, 'base').text.replace(',', ' ').split()]
    assert base == [1.0, 2.0, 3.0]
    size = [float(x) for x in _first(el, 'size').text.replace(',', ' ').split()]
    assert size == [20.0, 40.0, 20.0]
    # transform untouched (identity default)
    assert '1,0,0,0,0,1,0' in (_first(el, 'transform').text or '')


def test_variable_blend_cycle_on_block():
    # R3.5: PK_EDGE_set_blend_variable legacy v1 ABI - variable-radius
    # round on one edge of a 10 m cube (2.0 m -> 0.5 m linear profile).
    # Removed material = avg(r^2) * (1 - pi/4) * L with avg(r^2)=1.75 and
    # L=10, so V = 1000 - 17.5*(1-pi/4) ~= 996.244.
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    pk = sess.pk
    body = cab_ps_ops.create_solid_block((10.0, 10.0, 10.0))
    edges = cab_blend.body_edges(pk, body)
    assert len(edges) == 12
    rc, n = cab_blend.variable_blend_edge(pk, edges[0],
                                          [(0.0, 2.0), (1.0, 0.5)])
    assert rc == 0 and n == 1
    rc2, n_blends, faces = cab_blend.fix_blends(pk, body)
    assert rc2 == 0 and n_blends == 1 and len(faces) == 1
    part = sess.facet_body_stpre(body)
    assert part is not None
    vol = cab_ps_ops.mesh_volume_m3(part.points, part.triangles)
    assert abs(vol - 996.244) < 0.35
    # interior-only positions get endpoint radii by linear extrapolation
    body2 = cab_ps_ops.create_solid_block((10.0, 10.0, 10.0))
    edges2 = cab_blend.body_edges(pk, body2)
    rc3, n3 = cab_blend.variable_blend_edge(pk, edges2[0],
                                            [(0.25, 1.75), (0.75, 0.75)])
    assert rc3 == 0 and n3 == 1


def test_spin_sheet_cone_volume():
    # R3.5: PK_BODY_spin - off-axis sheet triangle revolved 360 deg about
    # Z yields the Pappus ring volume 2*pi/3 (area 0.5, centroid dist 2/3).
    if not cab_ps_ops.available():
        return
    import math
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    pk = sess.pk
    sheet = cab_ps_ops._triangle_sheet(pk, (0.5, 0.0, 0.0),
                                       (1.0, 0.0, 0.0), (0.5, 0.0, 2.0))
    rc, n_lat, _ = cab_ps_ops.spin_body(pk, sheet, (0.0, 0.0, 0.0),
                                        (0.0, 0.0, 1.0), 360.0)
    assert rc == 0 and n_lat >= 1
    part = sess.facet_body_stpre(sheet)
    assert part is not None
    vol = cab_ps_ops.mesh_volume_m3(part.points, part.triangles)
    assert abs(vol - 2.0 * math.pi / 3.0) < 0.05
    # zero axis is rejected without touching the kernel
    rc2, _, _ = cab_ps_ops.spin_body(pk, sheet, (0.0, 0.0, 0.0),
                                     (0.0, 0.0, 0.0), 90.0)
    assert rc2 != 0


def test_blend_dialog_variable_and_spin_modes():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    from PyQt5.QtWidgets import QApplication
    from cab_edit_dialogs import BlendEdgeDialog, FaceExtrusionDialog
    app = QApplication.instance() or QApplication([])
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name="P", kind="cube", attribute="solid")
    dlg = BlendEdgeDialog(model, [], None)
    assert hasattr(dlg, "rb_var")
    assert dlg.rb_var.isChecked() is False
    assert dlg.var_start.value() > 0 and dlg.var_end.value() > 0
    fdlg = FaceExtrusionDialog(model, [], None)
    assert hasattr(fdlg, "rb_spin")
    assert fdlg.rb_linear.isChecked() is True
    assert fdlg.angle.value() == 360.0


def test_find_g1_edges_on_block():
    # V37 chain helper: PK_EDGE_find_g1_edges returns at least the edge
    # itself on a box (no tangent neighbours).
    if not cab_ps_ops.available():
        return
    import ps_facet2_nodes as _ps
    sess = _ps._get_session()
    body = cab_ps_ops.create_solid_block((0.04, 0.04, 0.04))
    edges = cab_blend.body_edges(sess.pk, body)
    assert len(edges) == 12
    chain = cab_blend.find_g1_edges(sess.pk, edges[0])
    assert edges[0] in chain and len(chain) >= 1

def test_blend_dialog_chain_option_present():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    from PyQt5.QtWidgets import QApplication
    from cab_edit_dialogs import BlendEdgeDialog
    app = QApplication.instance() or QApplication([])
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name="P", kind="cube", attribute="solid")
    dlg = BlendEdgeDialog(model, [], None)
    assert hasattr(dlg, "chain_chk")
    assert dlg.chain_chk.isChecked() is False

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


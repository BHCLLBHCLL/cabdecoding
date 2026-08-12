"""M33: PK_BODY_boolean_2 + face-plane panelize/sweep + face delete."""
from __future__ import annotations

from pathlib import Path

import cab_edit_ops
import cab_ps_ops
from cab_parts import cube_tess
from cabxml import StpreModel, new_stpre_bytes, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"


def _two_cubes():
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name="A", kind="cube", attribute="solid")
    model.add_part(name="B", kind="cube", attribute="solid")
    ta = cube_tess((0, 0, 0), (10, 10, 10))
    ta.name = "A"
    tb = cube_tess((5, 5, 5), (10, 10, 10))
    tb.name = "B"
    return model, [ta, tb]


def test_pk_body_boolean_available_ops():
    if not cab_ps_ops.available():
        return
    a = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    b = cab_ps_ops.create_solid_block((0.5, 0.5, 0.5), (0.25, 0.25, 0.25))
    a = cab_ps_ops.entity_copy(a)
    b = cab_ps_ops.entity_copy(b)
    out = cab_ps_ops.body_boolean(a, [b], "subtract")
    assert out and out[0] > 0


def test_boolean_on_received_xt_body():
    """M39-P1: PK_BODY_boolean_2 on a real x_t body tag (not AABB block)."""
    if not cab_ps_ops.available():
        return
    sess = cab_ps_ops._ps._get_session()
    tag_a = sess.receive_xt(BOX_XT.read_bytes())[0]
    tag_b = cab_ps_ops.create_solid_block(
        (0.005, 0.005, 0.005), (0.0025, 0.0025, 0.0025))
    out = cab_ps_ops.body_boolean(tag_a, [tag_b], "subtract")
    part = (sess.facet_body_adaptive(out[0])
            or sess.facet2(out[0]) or sess.facet_go(out[0]))
    assert part is not None
    vol = cab_ps_ops.mesh_volume_m3(part.points, part.triangles)
    # 10 mm cube minus 5 mm inner cube = 1e-6 - 1.25e-7 m^3
    assert abs(vol - 8.75e-7) < 1e-10


def test_boolean_xt_bodies_intersect():
    """M39-P1: boolean_xt_bodies on two real x_t streams."""
    if not cab_ps_ops.available():
        return
    raw = BOX_XT.read_bytes()
    res = cab_ps_ops.boolean_xt_bodies(raw, raw, "intersect")
    assert abs(res["volume_m3"] - 1e-6) < 1e-10


def test_boolean_mesh_parts_real_xt_bodies():
    """M39-P1 wiring: boolean via real x_t body tags + XT member persist."""
    if not cab_ps_ops.available():
        return
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    import cab_import
    # ex4_e: two overlapping solid bodies from one real x_t stream.
    arch = CabArchive.parse((ROOT / "tests" / "ex4_e.cab").read_bytes())
    arch.fill_member_data()
    mm = {m.name: m.data for m in arch.members}
    model = StpreModel(parse_stpre(mm["ex4_e.xml"]))
    tess = {b.name: b.tess for b in cab_import.import_xt_bytes(
        mm["_ex4_e_all.x_t"], adaptive=False)}
    tess_a, tess_b = tess["button"], tess["battery"]
    out = cab_edit_ops.boolean_mesh_parts(
        model, [tess_a, tess_b], "button", "battery", "subtract",
        "bool_real",
        archive=arch)
    assert out is not None and out[1] == "pk"
    assert any(p.name == out[0] for p in model.parts())
    # pskernel here cannot PK_PART_transmit -> faceted result persists as STL
    assert any(m.name == f"{out[0]}.stl" for m in arch.members)


def test_boolean_mesh_parts_prefers_pk():
    model, meshes = _two_cubes()
    out = cab_edit_ops.boolean_mesh_parts(
        model, meshes, "A", "B", "subtract", "bool_1",
        keep_a=True, keep_b=True)
    assert out is not None
    name, backend = out
    assert name.startswith("bool_1")
    if cab_ps_ops.available():
        assert backend == "pk"
    assert any(p.name == name for p in model.parts())


def test_face_plane_and_panelize():
    model, meshes = _two_cubes()
    plane = cab_edit_ops.face_plane_from_cell(meshes[0], 0, "")
    assert plane is not None
    assert "direction" in plane
    pname = cab_edit_ops.panelize_part_face(
        model, meshes, "A", cell_id=0)
    assert pname and ("panel" in pname)


def test_extrude_and_delete_faces():
    model, meshes = _two_cubes()
    ename = cab_edit_ops.extrude_part_face(
        model, meshes, "A", 5.0, cell_id=0, result_name="ex1")
    assert ename
    n_before = len(meshes[0].triangles)
    removed = cab_edit_ops.delete_selected_faces_tess(meshes, "A", 0)
    assert removed > 0
    assert len(meshes[0].triangles) < n_before

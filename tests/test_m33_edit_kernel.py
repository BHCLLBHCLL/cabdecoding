"""M33: PK_BODY_boolean_2 + face-plane panelize/sweep + face delete."""
from __future__ import annotations

import cab_edit_ops
import cab_ps_ops
from cab_parts import cube_tess
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


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

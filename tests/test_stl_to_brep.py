"""M39: STL/facet triangles -> solid B-rep (classic PK pipeline)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cab_edit_ops
import cab_ps_ops
from cab_parts import cube_tess
from cabxml import StpreModel, new_stpre_bytes, parse_stpre

ROOT = Path(__file__).resolve().parents[1]


def _kernel():
    return cab_ps_ops.available()


def test_triangles_to_brep_cube_solid():
    """12-triangle cube -> one solid -> valid x_t -> 12-face body."""
    if not _kernel():
        return
    t = cube_tess((0, 0, 0), (10, 10, 10))
    solids = cab_ps_ops.triangles_to_brep(t.points, t.triangles)
    assert len(solids) == 1
    xt = cab_ps_ops.transmit_parts(solids)
    assert len(xt) > 1000
    sess = cab_ps_ops._ps._get_session()
    bodies = sess.expand_to_bodies(sess.receive_xt(xt))
    assert len(bodies) == 1
    pk = sess.pk
    import ctypes as C
    pk.PK_BODY_ask_faces.restype = C.c_int
    pk.PK_BODY_ask_faces.argtypes = [C.c_int, C.POINTER(C.c_int),
                                    C.POINTER(C.c_void_p)]
    nf = C.c_int(0)
    fp = C.c_void_p()
    rc = pk.PK_BODY_ask_faces(bodies[0], C.byref(nf), C.byref(fp))
    assert rc == 0 and nf.value == 12


def test_triangles_to_brep_open_sheet_rejected():
    """An open mesh cannot form a solid; the capped degenerate is dropped."""
    if not _kernel():
        return
    pts = np.array([[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0]], dtype=np.float64)
    tris = np.array([[0, 1, 2]], dtype=np.int64)
    solids = cab_ps_ops.triangles_to_brep(pts, tris)
    assert solids == []


def test_facets_to_solid_part_registers_x_t():
    """GUI-model wiring: faceted part -> solid body part + .x_t member."""
    if not _kernel():
        return
    from cab_container import CabArchive
    arch = CabArchive.parse((ROOT / "tests" / "box.cab").read_bytes())
    arch.fill_member_data()
    model = StpreModel(parse_stpre(new_stpre_bytes("demo")))
    t = cube_tess((0, 0, 0), (10, 10, 10))
    t.name = "stl_part"
    model.add_part(name="stl_part", kind="polygon", attribute="surface")
    meshes = [t]
    new_name = cab_edit_ops.facets_to_solid_part(
        model, arch, meshes, "stl_part")
    assert new_name is not None
    assert any(p.name == new_name and p.kind == "body" for p in model.parts())
    assert any(m.name == f"{new_name}.x_t" and m.data for m in arch.members)

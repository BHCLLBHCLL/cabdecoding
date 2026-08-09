"""Smoke tests for M24–M31 MVP deliverables."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

import cab_edit_ops
import cab_import
import cab_ps_ops
from cab_parts import PRIMITIVE_KINDS, tess_for_spec
from cab_wizards import _CW_PAGES


def test_obj_import():
    p = Path(tempfile.mkdtemp()) / "t.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    bodies, _raw, fmt = cab_import.import_file_with_payload(p)
    assert fmt == "stl"
    assert bodies and bodies[0].tess.triangles.shape[0] == 1


def test_mesh_boolean_subtract_intersect():
    pts = np.array([[0.0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2]])
    tris = np.array([[0, 1, 2], [0, 2, 3], [0, 3, 1], [1, 3, 2]], np.int64)
    lo = np.array([0.5, 0.5, -1.0])
    hi = np.array([3.0, 3.0, 0.2])
    _p, nt = cab_ps_ops.mesh_boolean(pts, tris, lo, hi, "subtract")
    assert len(nt) == 3
    _p, ni = cab_ps_ops.mesh_boolean(pts, tris, lo, hi, "intersect")
    assert len(ni) == 1


def test_flip_selected_triangle():
    class T:
        name = "a"
        triangles = np.array([[0, 1, 2]], np.int64)
        points = np.zeros((3, 3))

    meshes = [T()]
    assert cab_edit_ops.flip_selected_triangles(meshes, "a", [0])
    assert list(meshes[0].triangles[0]) == [0, 2, 1]


def test_m30_specialty_kinds():
    for k in ("enclosure", "plate_fin", "pin_fin", "peltier", "two_resistor"):
        assert k in PRIMITIVE_KINDS
        t = tess_for_spec(
            k,
            {
                "base": (0, 0, 0),
                "size": (10, 10, 5),
                "fin_count": 3,
                "pin_nx": 2,
                "pin_ny": 2,
            },
        )
        assert t.triangles.size > 0


def test_m28_cw_pages_registered():
    keys = {k for k, _, __ in _CW_PAGES}
    assert {"humidity", "porous", "bc_radiation"} <= keys


def test_m29_options_tabs_exist():
    from cab_options import OptionsDialog

    assert hasattr(OptionsDialog, "_folder_tab")
    assert hasattr(OptionsDialog, "_color_tab")
    assert hasattr(OptionsDialog, "_unit_tab")

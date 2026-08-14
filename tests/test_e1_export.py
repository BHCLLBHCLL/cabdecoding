"""E1: MDL/DXF/OBJ export helpers round-trip."""
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest

import cab_import


def _temp_dir():
    d = Path(tempfile.gettempdir()) / f"e1_{uuid.uuid4().hex}"
    os.makedirs(d, exist_ok=False)
    return d


def _cube():
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    tris = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return pts, tris


def test_obj_roundtrip():
    pts, tris = _cube()
    data = cab_import._tris_to_obj_bytes(pts, tris, "cube")
    d = _temp_dir()
    f = d / "cube.obj"
    f.write_bytes(data)
    v, t = cab_import.parse_obj_file(f)
    assert v.shape == (8, 3), v.shape
    assert t.shape == (12, 3), t.shape


def test_dxf_roundtrip():
    pts, tris = _cube()
    data = cab_import._tris_to_dxf_bytes(pts, tris, "cube")
    d = _temp_dir()
    f = d / "cube.dxf"
    f.write_bytes(data)
    p, t = cab_import.parse_dxf_meshish(f)
    assert len(p) >= 8 and len(t) == 12, (len(p), len(t))


def test_mdl_is_obj_compatible():
    pts, tris = _cube()
    assert cab_import._tris_to_mdl_bytes(pts, tris, "c") == \
        cab_import._tris_to_obj_bytes(pts, tris, "c")

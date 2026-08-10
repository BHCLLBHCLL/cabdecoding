"""M38: import/export format matrix smoke (OBJ/STL; XT if pskernel)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cab_import

ROOT = Path(__file__).resolve().parents[1]
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"


def _unit_cube_mm():
    """Axis-aligned unit cube in mm (8 verts / 12 tris)."""
    pts = np.array([
        [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
        [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10],
    ], dtype=np.float64) / 1000.0  # metres for tess
    tris = np.array([
        [0, 1, 2], [0, 2, 3],
        [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1],
        [1, 5, 6], [1, 6, 2],
        [2, 6, 7], [2, 7, 3],
        [3, 7, 4], [3, 4, 0],
    ], dtype=np.int64)
    return pts, tris


def test_obj_roundtrip_smoke():
    pts, tris = _unit_cube_mm()
    out_dir = ROOT / "tests" / "_m38_tmp"
    out_dir.mkdir(exist_ok=True)
    obj = out_dir / "cube.obj"
    lines = [f"v {p[0]} {p[1]} {p[2]}" for p in pts]
    for t in tris:
        lines.append(f"f {t[0] + 1} {t[1] + 1} {t[2] + 1}")
    obj.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        pts2, tris2 = cab_import.parse_obj_file(obj)
        assert len(pts2) == 8
        assert len(tris2) == 12
        # Export-style: OBJ → STL bytes → parse back
        stl = cab_import._tris_to_stl_bytes(pts2, tris2, "cube")
        assert len(stl) > 84
        pts3, tris3 = cab_import.parse_stl_bytes(stl)
        assert len(pts3) >= 3
        assert len(tris3) == 12
    finally:
        try:
            obj.unlink()
        except OSError:
            pass


def test_stl_roundtrip_smoke():
    pts, tris = _unit_cube_mm()
    raw = cab_import._tris_to_stl_bytes(pts, tris, "cube")
    out_dir = ROOT / "tests" / "_m38_tmp"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "cube.stl"
    out.write_bytes(raw)
    try:
        again = out.read_bytes()
        pts2, tris2 = cab_import.parse_stl_bytes(again)
        assert len(tris2) == 12
        # bbox roughly preserved (metres)
        lo, hi = pts2.min(0), pts2.max(0)
        np.testing.assert_allclose(lo, [0, 0, 0], atol=1e-5)
        np.testing.assert_allclose(hi, [0.01, 0.01, 0.01], atol=1e-5)
    finally:
        try:
            out.unlink()
        except OSError:
            pass


@pytest.mark.skipif(not cab_import.available(),
                    reason="pskernel not installed")
def test_xt_import_smoke_if_available():
    assert BOX_XT.is_file()
    bodies = cab_import.import_xt_file(BOX_XT)
    assert bodies
    assert bodies[0].tess is not None
    assert len(bodies[0].tess.triangles) > 0


def test_unsupported_iges_idf_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        cab_import.import_file("dummy.iges")
    with pytest.raises(ValueError, match="unsupported"):
        cab_import.import_file("dummy.idf")

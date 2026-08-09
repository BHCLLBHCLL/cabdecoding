"""M24+: Parasolid session helpers (transmit / facet reconstruct / mesh CSG).

True ``PK_BODY_boolean_2`` option layouts are kernel-version sensitive; until
those are reverse-engineered, boolean here uses tessellation CSG (triangle
keep/discard against the tool AABB) and still produces polygon parts that
participate in meshing.  ``PK_PART_transmit`` is used for XT export.
"""

from __future__ import annotations

import tempfile
from ctypes import (
    POINTER, Structure, byref, c_char_p, c_double, c_int, c_void_p, cast,
    create_string_buffer, memmove, sizeof,
)
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import ps_facet2_nodes as _ps
except Exception:  # pragma: no cover
    _ps = None


class _Transmit(Structure):
    _fields_ = [
        ("o_t_version", c_int),
        ("transmit_format", c_int),   # 0 = text
        ("transmit_user_fields", c_int),
        ("transmit_nw_version", c_int),
        ("transmit_xmt_file", c_int),
        ("transmit_attr", c_int),
    ]


def available() -> bool:
    return _ps is not None and _ps.available()


def transmit_parts(tags: list[int]) -> bytes:
    """``PK_PART_transmit`` selected body tags → text ``.x_t`` bytes."""
    if not tags:
        raise ValueError("no body tags to transmit")
    sess = _ps._get_session()
    pk = sess.pk
    tmpdir = Path(tempfile.mkdtemp(prefix="cab_tx_"))
    key = str(tmpdir / "out").encode()
    opts = _Transmit()
    opts.o_t_version = 1
    opts.transmit_format = 0
    pk.PK_PART_transmit.restype = c_int
    pk.PK_PART_transmit.argtypes = [
        c_int, POINTER(c_int), c_char_p, POINTER(_Transmit)]
    arr = (c_int * len(tags))(*tags)
    rc = pk.PK_PART_transmit(len(tags), arr, key, byref(opts))
    if rc != 0:
        raise RuntimeError(f"PK_PART_transmit failed: {rc}")
    xtp = tmpdir / "out.x_t"
    if not xtp.is_file():
        # some kernels write without extension
        cand = list(tmpdir.glob("out*"))
        if not cand:
            raise RuntimeError("PK_PART_transmit produced no file")
        xtp = cand[0]
    return xtp.read_bytes()


def reconstruct_facet(xt_bytes: bytes, *, names: Optional[set[str]] = None,
                      facet_tol: float = 1e-4,
                      facet_angle_deg: float = 12.0,
                      adaptive: bool = True) -> list:
    """Re-receive + ``PK_TOPOL_facet_2``; optionally filter by body name."""
    if not available():
        raise RuntimeError("pskernel not available")
    sess = _ps._get_session()
    tags = sess.receive_xt(xt_bytes)
    out = []
    for tag in tags:
        name = sess.body_name(tag)
        if names is not None and name not in names:
            continue
        if adaptive:
            part = sess.facet_body_adaptive(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        else:
            part = sess.facet_body(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        if part is not None and part.triangles.size:
            out.append(part)
    return out


def _point_in_aabb(p: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> bool:
    return bool(np.all(p >= lo - 1e-12) and np.all(p <= hi + 1e-12))


def mesh_boolean(points_a: np.ndarray, tris_a: np.ndarray,
                 lo_b: np.ndarray, hi_b: np.ndarray, op: str
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Triangle keep/discard CSG against tool AABB (metres).

    ``op``: unite | subtract | intersect
    """
    pts = np.asarray(points_a, dtype=np.float64)
    tris = np.asarray(tris_a, dtype=np.int64)
    if tris.size == 0:
        return pts, tris
    keep = []
    for t in tris:
        c = pts[t].mean(axis=0)
        inside = _point_in_aabb(c, lo_b, hi_b)
        if op == "unite":
            keep.append(True)  # caller merges B separately
        elif op == "subtract":
            keep.append(not inside)
        elif op == "intersect":
            keep.append(inside)
        else:
            keep.append(True)
    mask = np.asarray(keep, dtype=bool)
    kept = tris[mask]
    if kept.size == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    used = np.unique(kept.ravel())
    remap = {old: i for i, old in enumerate(used)}
    new_pts = pts[used]
    new_tris = np.asarray([[remap[i] for i in t] for t in kept], dtype=np.int64)
    return new_pts, new_tris


def tess_world_aabb(tess, transform: str = "") -> Optional[tuple[np.ndarray, np.ndarray]]:
    """World AABB of a TessPart in metres."""
    import cab_vtk
    pts = np.asarray(tess.points, dtype=np.float64)
    if pts.size == 0:
        return None
    pts = cab_vtk._apply_transform(pts, transform)
    return pts.min(0), pts.max(0)

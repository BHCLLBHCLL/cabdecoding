"""M24+/M33: Parasolid helpers — transmit, facet reconstruct, B-rep boolean.

``PK_BODY_boolean_2`` is bound with verified ``o_t_version=2`` options and the
6-argument signature (target, tools, options, tracking, results). Tessellation
AABB CSG remains as fallback when pskernel/XT is unavailable.
"""

from __future__ import annotations

import tempfile
from ctypes import (
    POINTER, Structure, byref, c_char_p, c_double, c_int, c_void_p, memset,
    sizeof,
)
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import ps_facet2_nodes as _ps
except Exception:  # pragma: no cover
    _ps = None

# --- Parasolid tokens (V35-style numeric codes) ---------------------------
PK_boolean_intersect_c = 15901
PK_boolean_subtract_c = 15902
PK_boolean_unite_c = 15903
PK_boolean_fence_none_c = 18212
PK_boolean_check_fa_yes_c = 21801
PK_FACE_heal_cap_c = 18081
PK_FACE_heal_shrink_c = 18084
PK_local_ops_update_default_c = 24330
PK_repair_fa_fa_no_c = 24360
PK_delete_track_no_c = 26340

_OP_TO_FUNC = {
    "unite": PK_boolean_unite_c,
    "subtract": PK_boolean_subtract_c,
    "intersect": PK_boolean_intersect_c,
}


class _Transmit(Structure):
    _fields_ = [
        ("o_t_version", c_int),
        ("transmit_format", c_int),   # 0 = text
        ("transmit_user_fields", c_int),
        ("transmit_nw_version", c_int),
        ("transmit_xmt_file", c_int),
        ("transmit_attr", c_int),
    ]


class _AXIS2(Structure):
    _fields_ = [
        ("location", c_double * 3),
        ("axis", c_double * 3),
        ("ref_direction", c_double * 3),
    ]


class _BooleanOpts(Structure):
    """PK_BODY_boolean_o_t (verified o_t_version=2 on Cradle 2025 pskernel)."""
    _fields_ = [
        ("o_t_version", c_int),
        ("function", c_int),
        ("configuration", c_void_p),
        ("matched_region", c_void_p),
        ("merge_imprinted", c_int),
        ("prune_in_solid", c_int),
        ("prune_in_void", c_int),
        ("fence", c_int),
        ("allow_disjoint", c_int),
        ("selective_merge", c_int),
        ("check_fa", c_int),
        ("default_tol", c_double),
        ("max_tol", c_double),
        ("tracking", c_int),
        ("merge_attributes", c_int),
        ("keep_target_edges", c_int),
    ]


class _TrackR(Structure):
    _fields_ = [
        ("n_track_records", c_int),
        ("track_records", c_void_p),
        ("internal_origs", c_void_p),
        ("internal_classes", c_void_p),
        ("internal_prods", c_void_p),
    ]


class _BooleanR(Structure):
    _fields_ = [
        ("result", c_int),
        ("n_bodies", c_int),
        ("bodies", POINTER(c_int)),
        ("n_reports", c_int),
        ("reports", c_void_p),
    ]


class _FaceDeleteOpts(Structure):
    """PK_FACE_delete_o_t (verified o_t_version=1, heal_cap)."""
    _fields_ = [
        ("o_t_version", c_int),
        ("update", c_int),
        ("heal_action", c_int),
        ("heal_loops", c_int),
        ("local_check", c_int),
        ("allow_disjoint", c_int),
        ("repair_fa_fa", c_int),
        ("track", c_int),
    ]


def available() -> bool:
    return _ps is not None and _ps.available()


def transmit_parts(tags: list[int]) -> bytes:
    """``PK_PART_transmit`` body/part tags → text ``.x_t`` bytes."""
    if not tags:
        raise ValueError("no body tags to transmit")
    sess = _ps._get_session()
    pk = sess.pk
    # PK_PART_transmit expects PART tags; map body tags to their owner part.
    pk.PK_BODY_ask_parent.restype = c_int
    pk.PK_BODY_ask_parent.argtypes = [c_int, POINTER(c_int)]
    parts = []
    for tag in tags:
        parent = c_int(0)
        rc = -1
        try:
            rc = pk.PK_BODY_ask_parent(int(tag), byref(parent))
        except Exception:
            pass
        parts.append(int(parent.value) if rc == 0 and parent.value
                     else int(tag))
    tmpdir = Path(tempfile.mkdtemp(prefix="cab_tx_"))
    key = str(tmpdir / "out").encode()
    opts = _Transmit()
    opts.o_t_version = 1
    opts.transmit_format = 0
    pk.PK_PART_transmit.restype = c_int
    pk.PK_PART_transmit.argtypes = [
        c_int, POINTER(c_int), c_char_p, POINTER(_Transmit)]
    arr = (c_int * len(parts))(*parts)
    rc = pk.PK_PART_transmit(len(parts), arr, key, byref(opts))
    if rc != 0:
        raise RuntimeError(f"PK_PART_transmit failed: {rc}")
    xtp = tmpdir / "out.x_t"
    if not xtp.is_file():
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
    tags = sess.expand_to_bodies(sess.receive_xt(xt_bytes))
    out = []
    for tag in tags:
        try:
            name = sess.body_name(tag)
        except Exception:
            name = f"body_{tag}"
        if names is not None and name not in names:
            continue
        try:
            if adaptive:
                part = sess.facet_body_adaptive(
                    tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
            else:
                part = sess.facet_body(
                    tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        except OSError:
            part = None
        if part is not None and part.triangles.size:
            out.append(part)
    return out


def create_solid_block(size_m: tuple[float, float, float],
                       origin_m: tuple[float, float, float] = (0, 0, 0)
                       ) -> int:
    """``PK_BODY_create_solid_block`` → body tag (metres)."""
    if not available():
        raise RuntimeError("pskernel not available")
    pk = _ps._get_session().pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    body = c_int(0)
    ox, oy, oz = (float(v) for v in origin_m)
    if abs(ox) + abs(oy) + abs(oz) < 1e-15:
        pk.PK_BODY_create_solid_block.restype = c_int
        pk.PK_BODY_create_solid_block.argtypes = [
            c_double, c_double, c_double, c_void_p, POINTER(c_int)]
        rc = pk.PK_BODY_create_solid_block(
            float(size_m[0]), float(size_m[1]), float(size_m[2]),
            None, byref(body))
    else:
        ax = _AXIS2()
        ax.location[:] = (ox, oy, oz)
        ax.axis[:] = (0.0, 0.0, 1.0)
        ax.ref_direction[:] = (1.0, 0.0, 0.0)
        pk.PK_BODY_create_solid_block.restype = c_int
        pk.PK_BODY_create_solid_block.argtypes = [
            c_double, c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
        rc = pk.PK_BODY_create_solid_block(
            float(size_m[0]), float(size_m[1]), float(size_m[2]),
            byref(ax), byref(body))
    if rc != 0 or not body.value:
        raise RuntimeError(f"PK_BODY_create_solid_block failed: {rc}")
    return int(body.value)


def body_boolean(target: int, tools: list[int], op: str
                 ) -> list[int]:
    """``PK_BODY_boolean_2``; returns resulting body tags.

    Tools are consumed by the kernel. ``op``: unite|subtract|intersect.
    """
    if not available():
        raise RuntimeError("pskernel not available")
    func = _OP_TO_FUNC.get(op)
    if func is None:
        raise ValueError(f"unsupported boolean op: {op}")
    if not tools:
        raise ValueError("no tool bodies")
    pk = _ps._get_session().pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)

    opts = _BooleanOpts()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 2
    opts.function = func
    opts.fence = PK_boolean_fence_none_c
    opts.check_fa = PK_boolean_check_fa_yes_c
    opts.default_tol = 1.0e-5
    opts.max_tol = 0.0

    track = _TrackR()
    memset(byref(track), 0, sizeof(track))
    res = _BooleanR()
    memset(byref(res), 0, sizeof(res))
    arr = (c_int * len(tools))(*[int(t) for t in tools])

    pk.PK_BODY_boolean_2.restype = c_int
    pk.PK_BODY_boolean_2.argtypes = [
        c_int, c_int, POINTER(c_int), POINTER(_BooleanOpts),
        POINTER(_TrackR), POINTER(_BooleanR)]
    rc = pk.PK_BODY_boolean_2(
        int(target), len(tools), arr, byref(opts), byref(track), byref(res))
    if rc != 0:
        raise RuntimeError(f"PK_BODY_boolean_2 failed: {rc}")
    if res.n_bodies <= 0 or not res.bodies:
        raise RuntimeError(
            f"PK_BODY_boolean_2 produced no bodies (result={res.result})")
    return [int(res.bodies[i]) for i in range(res.n_bodies)]


def face_delete(face_tags: list[int], *,
                heal: str = "cap") -> None:
    """``PK_FACE_delete_2`` with cap/shrink healing (same body)."""
    if not available():
        raise RuntimeError("pskernel not available")
    if not face_tags:
        return
    pk = _ps._get_session().pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)

    opts = _FaceDeleteOpts()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 1
    opts.update = PK_local_ops_update_default_c
    opts.heal_action = (
        PK_FACE_heal_shrink_c if heal == "shrink" else PK_FACE_heal_cap_c)
    opts.heal_loops = 0
    opts.local_check = 1
    opts.repair_fa_fa = PK_repair_fa_fa_no_c
    opts.track = PK_delete_track_no_c

    track = _TrackR()
    memset(byref(track), 0, sizeof(track))
    arr = (c_int * len(face_tags))(*[int(t) for t in face_tags])
    pk.PK_FACE_delete_2.restype = c_int
    pk.PK_FACE_delete_2.argtypes = [
        c_int, POINTER(c_int), POINTER(_FaceDeleteOpts), POINTER(_TrackR)]
    rc = pk.PK_FACE_delete_2(len(face_tags), arr, byref(opts), byref(track))
    if rc != 0:
        raise RuntimeError(f"PK_FACE_delete_2 failed: {rc}")


def entity_copy(tag: int) -> int:
    """``PK_ENTITY_copy`` → new tag."""
    if not available():
        raise RuntimeError("pskernel not available")
    pk = _ps._get_session().pk
    out = c_int(0)
    pk.PK_ENTITY_copy.restype = c_int
    pk.PK_ENTITY_copy.argtypes = [c_int, POINTER(c_int)]
    rc = pk.PK_ENTITY_copy(int(tag), byref(out))
    if rc != 0 or not out.value:
        raise RuntimeError(f"PK_ENTITY_copy failed: {rc}")
    return int(out.value)


def mesh_volume_m3(points, triangles) -> float:
    """Closed-mesh volume via signed tetrahedra (origin-based)."""
    pts = np.asarray(points, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int64)
    a = pts[tris[:, 0]]
    b = pts[tris[:, 1]]
    c = pts[tris[:, 2]]
    return float(abs(float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum())
                     / 6.0))


def boolean_xt_bodies(xt_a: bytes, xt_b: bytes, op: str) -> dict:
    """M39-P1 core: ``PK_BODY_boolean_2`` on real x_t body tags.

    Receives both streams into one session, booleans the first body with
    the second as tool, facets the result and returns
    ``{body_tag, tess, volume_m3}``.

    Note: ``PK_BODY_export`` is not exported by this pskernel build, so the
    result geometry is only available in-session (persistence via XT export
    is a remaining P1 item).
    """
    if not available():
        raise RuntimeError("pskernel not available")
    sess = _ps._get_session()
    ta = sess.receive_xt(xt_a)
    tb = sess.receive_xt(xt_b)
    if not ta or not tb:
        raise RuntimeError("PK_PART_receive produced no bodies")
    out = body_boolean(ta[0], [tb[0]], op)
    tag = int(out[0])
    part = (sess.facet_body_adaptive(tag)
            or sess.facet2(tag)
            or sess.facet_go(tag))
    if part is None or part.triangles.size == 0:
        raise RuntimeError("failed to facet boolean result")
    return {
        "body_tag": tag,
        "tess": part,
        "volume_m3": mesh_volume_m3(part.points, part.triangles),
    }


def find_body_tag_by_name(xt_bytes: bytes, name: str) -> Optional[int]:
    """Receive XT and return the body tag matching ``name``."""
    if not available() or not name:
        return None
    sess = _ps._get_session()
    try:
        tags = sess.expand_to_bodies(sess.receive_xt(xt_bytes))
    except Exception:
        return None
    for tag in tags:
        try:
            if sess.body_name(tag) == name:
                return int(tag)
        except Exception:
            continue
    return None


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


def tess_world_aabb(tess, transform: str = ""
                    ) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """World AABB of a TessPart in metres."""
    import cab_vtk
    pts = np.asarray(tess.points, dtype=np.float64)
    if pts.size == 0:
        return None
    pts = cab_vtk._apply_transform(pts, transform)
    return pts.min(0), pts.max(0)

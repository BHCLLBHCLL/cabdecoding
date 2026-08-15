"""M24+/M33: Parasolid helpers — transmit, facet reconstruct, B-rep boolean.

``PK_BODY_boolean_2`` is bound with verified ``o_t_version=2`` options and the
6-argument signature (target, tools, options, tracking, results). Tessellation
AABB CSG remains as fallback when pskernel/XT is unavailable.
"""

from __future__ import annotations

import tempfile
from ctypes import (
    POINTER, Structure, byref, c_byte, c_char_p, c_double, c_int, c_void_p,
    memset, sizeof,
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
    """``PK_PART_transmit_o_t``（对齐 pphdecoding / Cradle V37，6 字段）。"""
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
    """``PK_PART_transmit`` body/part tags → text ``.x_t`` bytes.

    A4 note (q-solid Parasolid V35 headers): ``PK_PART_transmit`` takes PART
    tags.  Standalone bodies from ``PK_BODY_boolean_2`` have no owning part,
    and this kernel exports no ``PK_PART_new`` / ``PK_PART_add_bodies`` —
    ``PK_PART_add_geoms`` only adds *construction* geometry (points/curves/
    surfaces/lattices), not bodies; ``PK_PART_receive`` returns body tags
    rather than part tags here; ``PK_SESSION_transmit``/``PK_PARTITION_transmit``
    also reject a body-only session (973 / 5048).  Callers therefore fall back
    to the STL + polygon-part persistence path
    (see ``cab_edit_ops.register_tess_part``).
    """
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
    tmpdir = _ps._temp_dir("cab_tx_")
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


def create_rotated_block(size_m: tuple[float, float, float],
                        center_m, axis, ref_dir) -> int:
    """``PK_BODY_create_solid_block`` in a rotated frame (axis = local Z)."""
    if not available():
        raise RuntimeError("pskernel not available")
    pk = _ps._get_session().pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    ax = _AXIS2()
    ax.location[:] = (float(center_m[0]), float(center_m[1]),
                      float(center_m[2]))
    ax.axis[:] = (float(axis[0]), float(axis[1]), float(axis[2]))
    ax.ref_direction[:] = (float(ref_dir[0]), float(ref_dir[1]),
                           float(ref_dir[2]))
    body = c_int(0)
    pk.PK_BODY_create_solid_block.restype = c_int
    pk.PK_BODY_create_solid_block.argtypes = [
        c_double, c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
    rc = pk.PK_BODY_create_solid_block(
        float(size_m[0]), float(size_m[1]), float(size_m[2]),
        byref(ax), byref(body))
    if rc != 0 or not body.value:
        raise RuntimeError(f"PK_BODY_create_solid_block failed: {rc}")
    return int(body.value)


def _half_space_block(o, n, lo, hi, margin) -> int:
    """A3: a solid block covering ``{p : (p-o).n in [0, hi+margin]}``.

    Oriented so its local Z is ``n`` and its cross-section spans the body
    AABB projection onto the plane's two tangent axes.
    """
    n = np.asarray(n, dtype=np.float64)
    n = n / float(np.linalg.norm(n))
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(n @ ref)) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u = u / float(np.linalg.norm(u))
    v = np.cross(n, u)
    corners = np.array([
        [lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]],
        [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
        [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]],
        [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]],
    ], dtype=np.float64)
    uu = corners @ u
    vv = corners @ v
    ww = (corners - o) @ n
    u_lo, u_hi = float(uu.min()), float(uu.max())
    v_lo, v_hi = float(vv.min()), float(vv.max())
    w_span = max(0.0, float(ww.max())) + margin
    # PK_BODY_create_solid_block places basis_set.location at the centre of
    # the face at -axis (the block extends +dz along axis, centred on location
    # in the ref/cross directions).  The plane is w=0, so location sits on it.
    center = (o + u * ((u_lo + u_hi) / 2.0)
              + v * ((v_lo + v_hi) / 2.0))
    return create_rotated_block(
        ((u_hi - u_lo) + 2.0 * margin,
         (v_hi - v_lo) + 2.0 * margin,
         w_span),
        center, n, u)


def cut_body_by_plane(body_tag: int, origin_m, normal) -> dict:
    """A3: PK-level plane cut of a body into front(+n)/back(-n) solids.

    Uses ``PK_BODY_boolean_2`` intersect against two half-space blocks so the
    results are real B-rep bodies (not tessellation shells).  Returns
    ``{"front": body_tag, "back": body_tag}``.
    """
    if not available():
        raise RuntimeError("pskernel not available")
    sess = _ps._get_session()
    n = np.asarray(normal, dtype=np.float64)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        raise ValueError("cut plane normal must be non-zero")
    n = n / nn
    o = np.asarray(origin_m, dtype=np.float64)
    tess = (sess.facet_body_adaptive(body_tag)
            or sess.facet2(body_tag) or sess.facet_go(body_tag))
    if tess is None or len(tess.points) == 0:
        raise RuntimeError("failed to facet body for cut")
    pts = np.asarray(tess.points, dtype=np.float64)
    lo, hi = pts.min(0), pts.max(0)
    margin = max(float((hi - lo).max()) * 0.5, 1e-3)
    front_block = _half_space_block(o, n, lo, hi, margin)
    back_block = _half_space_block(o, -n, lo, hi, margin)
    fa = entity_copy(int(body_tag))
    fb = entity_copy(int(body_tag))
    fr = body_boolean(fa, [front_block], "intersect")
    bk = body_boolean(fb, [back_block], "intersect")
    return {"front": int(fr[0]), "back": int(bk[0])}


class _TransformOpts(Structure):
    """``PK_BODY_transform_o_t``（对齐 pphdecoding / Cradle V37，4 int）。"""
    _fields_ = [
        ("o_t_version", c_int),
        ("merge_face", c_int),
        ("check_fa_fa", c_int),
        ("update", c_int),
    ]


def body_transform_translate(body_tag: int, dx: float, dy: float, dz: float,
                             tolerance: float = 1e-6) -> int:
    """A-trans：平移 body（Parasolid V37 路径）。

    Cradle pskernel 是 Parasolid V37，``PK_TRANSF_t`` 是 32 位 tag（非 V35 的
    4x4 矩阵）：先 ``PK_TRANSF_create_translation`` 生成变换 tag，再
    ``PK_BODY_transform_2(body, tag, tolerance, opts, track, res)`` 按值接收。
    返回内核 rc。
    """
    if not available():
        raise RuntimeError("pskernel not available")
    pk = _ps._get_session().pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    disp = (c_double * 3)(float(dx), float(dy), float(dz))
    tag = c_int(0)
    pk.PK_TRANSF_create_translation.restype = c_int
    pk.PK_TRANSF_create_translation.argtypes = [
        POINTER(c_double * 3), POINTER(c_int)]
    rc = pk.PK_TRANSF_create_translation(disp, byref(tag))
    if rc != 0 or not tag.value:
        raise RuntimeError(f"PK_TRANSF_create_translation failed: {rc}")
    opts = _TransformOpts(1, 1, 1, 0)
    track = (c_byte * 256)()
    res = (c_byte * 256)()
    pk.PK_BODY_transform_2.restype = c_int
    pk.PK_BODY_transform_2.argtypes = [
        c_int, c_int, c_double, POINTER(_TransformOpts), c_void_p, c_void_p]
    rc = int(pk.PK_BODY_transform_2(
        int(body_tag), int(tag.value), c_double(float(tolerance)),
        byref(opts), track, res))
    if rc != 0:
        raise RuntimeError(f"PK_BODY_transform_2 failed: {rc}")
    return rc


def match_face_by_plane(body_tag: int, normal, origin, *,
                        normal_tol: float = 0.98,
                        dist_tol: float = 1e-4) -> Optional[int]:
    """A2: match a body's PK_FACE to a plane ``(normal, origin)``.

    ``normal``/``origin`` must be in the body's local coordinates.  Returns
    the best-matching face tag or ``None`` when no face lies on the plane.
    """
    if not available():
        return None
    sess = _ps._get_session()
    faces = sess.body_faces(int(body_tag))
    if not faces:
        return None
    n = np.asarray(normal, dtype=np.float64)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        return None
    n = n / nn
    o = np.asarray(origin, dtype=np.float64)
    best: Optional[int] = None
    best_score = -1.0
    for ft in faces:
        pl = sess.face_plane(ft)
        if pl is None:
            continue
        fn, fo = pl
        dot = abs(float(np.dot(fn, n)))
        if dot < normal_tol:
            continue
        dist = abs(float(np.dot(fo - o, n)))
        if dist > dist_tol:
            continue
        score = dot - dist * 1e3
        if score > best_score:
            best_score = score
            best = int(ft)
    return best


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

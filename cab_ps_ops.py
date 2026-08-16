"""M24+/M33: Parasolid helpers — transmit, facet reconstruct, B-rep boolean.

``PK_BODY_boolean_2`` is bound with verified ``o_t_version=2`` options and the
6-argument signature (target, tools, options, tracking, results). Tessellation
AABB CSG remains as fallback when pskernel/XT is unavailable.
"""

from __future__ import annotations

import tempfile
from ctypes import (
    POINTER, Structure, byref, cast, c_byte, c_char_p, c_double, c_int,
    c_ubyte, c_void_p, memset, sizeof,
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
PK_FACE_heal_none_c = 18080
PK_FACE_heal_cap_c = 18081
# NOTE (diag 2026-08-16): this kernel's PK_FACE_delete_2 accepts ONLY
# heal tokens 18080 (none) / 18081 (cap).  The old ``shrink`` token 18084
# returns rc 525 on every body (created or received) and leaves the
# session unstable enough that the next call can crash; 18082 gives rc
# 5000.  Scan range 18060-18110, only 18080/18081 return rc 0.
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
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    opts = _Transmit()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 1
    opts.transmit_format = 0
    pk.PK_PART_transmit.restype = c_int
    pk.PK_PART_transmit.argtypes = [
        c_int, POINTER(c_int), c_char_p, POINTER(_Transmit)]
    arr = (c_int * len(tags))(*[int(t) for t in tags])
    key = b"out"
    rc = pk.PK_PART_transmit(len(tags), arr, key, byref(opts))
    if rc != 0:
        raise RuntimeError(f"PK_PART_transmit failed: {rc}")
    return sess._transmit_output.get("out", b"")


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
    """``PK_FACE_delete_2`` with cap/none healing (same body).

    ``heal="cap"`` closes the removed region with a healing face (the
    STpre Part-Simplification semantic: delete hole/feature face, keep a
    valid solid); ``"none"`` leaves the gap open.
    """
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
        PK_FACE_heal_none_c if heal == "none" else PK_FACE_heal_cap_c)
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


def _create_rotation(position, axis, angle) -> int:
    pk = _ps._get_session().pk
    pos = (c_double * 3)(float(position[0]), float(position[1]),
                          float(position[2]))
    ax = (c_double * 3)(float(axis[0]), float(axis[1]), float(axis[2]))
    tag = c_int(0)
    pk.PK_TRANSF_create_rotation.restype = c_int
    pk.PK_TRANSF_create_rotation.argtypes = [
        POINTER(c_double * 3), POINTER(c_double * 3), c_double, POINTER(c_int)]
    rc = pk.PK_TRANSF_create_rotation(pos, ax, c_double(float(angle)),
                                      byref(tag))
    if rc != 0 or not tag.value:
        raise RuntimeError(f"PK_TRANSF_create_rotation failed: {rc}")
    return int(tag.value)


def _create_reflection(position, normal) -> int:
    pk = _ps._get_session().pk
    pos = (c_double * 3)(float(position[0]), float(position[1]),
                          float(position[2]))
    nrm = (c_double * 3)(float(normal[0]), float(normal[1]), float(normal[2]))
    tag = c_int(0)
    pk.PK_TRANSF_create_reflection.restype = c_int
    pk.PK_TRANSF_create_reflection.argtypes = [
        POINTER(c_double * 3), POINTER(c_double * 3), POINTER(c_int)]
    rc = pk.PK_TRANSF_create_reflection(pos, nrm, byref(tag))
    if rc != 0 or not tag.value:
        raise RuntimeError(f"PK_TRANSF_create_reflection failed: {rc}")
    return int(tag.value)


def _create_equal_scale(scale, centre) -> int:
    pk = _ps._get_session().pk
    cen = (c_double * 3)(float(centre[0]), float(centre[1]), float(centre[2]))
    tag = c_int(0)
    pk.PK_TRANSF_create_equal_scale.restype = c_int
    pk.PK_TRANSF_create_equal_scale.argtypes = [
        c_double, POINTER(c_double * 3), POINTER(c_int)]
    rc = pk.PK_TRANSF_create_equal_scale(c_double(float(scale)), cen,
                                         byref(tag))
    if rc != 0 or not tag.value:
        raise RuntimeError(f"PK_TRANSF_create_equal_scale failed: {rc}")
    return int(tag.value)


def _body_transform_by_tag(body_tag: int, transf_tag: int,
                           tolerance: float = 1e-6) -> int:
    pk = _ps._get_session().pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    opts = _TransformOpts(1, 1, 1, 0)
    track = (c_byte * 256)()
    res = (c_byte * 256)()
    pk.PK_BODY_transform_2.restype = c_int
    pk.PK_BODY_transform_2.argtypes = [
        c_int, c_int, c_double, POINTER(_TransformOpts), c_void_p, c_void_p]
    rc = int(pk.PK_BODY_transform_2(
        int(body_tag), int(transf_tag), c_double(float(tolerance)),
        byref(opts), track, res))
    if rc != 0:
        raise RuntimeError(f"PK_BODY_transform_2 failed: {rc}")
    return rc


def body_transform_rotate(body_tag: int, position, axis, angle,
                          tolerance: float = 1e-6) -> int:
    """Rotate a body about ``axis`` through ``position`` by ``angle`` (rad)."""
    return _body_transform_by_tag(
        body_tag, _create_rotation(position, axis, angle), tolerance)


def body_transform_reflect(body_tag: int, position, normal,
                           tolerance: float = 1e-6) -> int:
    """Reflect a body in the plane through ``position`` with ``normal``."""
    return _body_transform_by_tag(
        body_tag, _create_reflection(position, normal), tolerance)


def body_transform_scale(body_tag: int, scale: float, centre,
                         tolerance: float = 1e-6) -> int:
    """Uniformly scale a body by ``scale`` centred on ``centre``."""
    return _body_transform_by_tag(
        body_tag, _create_equal_scale(scale, centre), tolerance)


def convex_hull_solid(points_m) -> int:
    """Wrap：point cloud → convex-hull solid body (half-space intersection).

    Builds the convex hull (scipy), then intersects one inward half-space
    block per hull face against a seed block via ``PK_BODY_boolean_2``.
    Returns the resulting solid body tag.
    """
    from scipy.spatial import ConvexHull
    if not available():
        raise RuntimeError("pskernel not available")
    pts = np.asarray(points_m, dtype=np.float64)
    if len(pts) < 4:
        raise ValueError("need at least 4 points for a convex hull")
    try:
        hull = ConvexHull(pts)
    except Exception as e:
        raise ValueError(f"ConvexHull failed: {e}")
    lo, hi = pts.min(0), pts.max(0)
    margin = max(float((hi - lo).max()) * 0.5, 1e-3)
    size = (hi - lo) + 2.0 * margin
    # V37 create_solid_block: x/y centred at origin, z from origin.z upward
    origin = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2] - margin)
    block = create_solid_block(tuple(size), origin)
    for eq in hull.equations:
        n = np.asarray(eq[:3], dtype=np.float64)
        nn = float(np.linalg.norm(n))
        if nn < 1e-12:
            continue
        n = n / nn
        offset = float(eq[3])
        origin = -offset * n  # a point on the face plane
        half = _half_space_block(origin, -n, lo, hi, margin)
        block = body_boolean(block, [half], "intersect")[0]
    return int(block)


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

# ---------------------------------------------------------------------------
# M39: STL/facet triangles -> B-rep solid (classic PK, no facet geometry)
#
# Reverse-engineered chain (probe-verified on the V37 kernel):
#   PK_PLANE_create   sf = {point[3], normal[3], x_axis[3]}  (72 bytes)
#   PK_BCURVE_create  2D polyline (vertex_dim=2, degree=1, 2 vertices)
#   PK_SPCURVE_create sf = {surf, curve}
#   PK_SURF_make_sheet_trimmed(surf, trim_data, precision, opts, &body, &state)
#   PK_BODY_sew_bodies -> single stitched sheet body
#   PK_FACE_make_solid_bodies -> solid body
# ---------------------------------------------------------------------------
class _SheetPlaneSf(Structure):
    """PK_PLANE_sf_t on this kernel: 9 doubles (point, normal, x_axis)."""
    _fields_ = [("data", c_double * 9)]


class _SheetBcurveSf(Structure):
    """PK_BCURVE_sf_t (PK_LOGICAL_t = unsigned char)."""
    _fields_ = [
        ("degree", c_int),
        ("n_vertices", c_int),
        ("vertex_dim", c_int),
        ("is_rational", c_ubyte),
        ("vertex", POINTER(c_double)),
        ("form", c_int),
        ("n_knots", c_int),
        ("knot_mult", POINTER(c_int)),
        ("knot", POINTER(c_double)),
        ("knot_type", c_int),
        ("is_periodic", c_ubyte),
        ("is_closed", c_ubyte),
        ("self_intersecting", c_ubyte),
    ]


class _SheetSpcurveSf(Structure):
    _fields_ = [("surf", c_int), ("curve", c_int)]


class _SheetInterval(Structure):
    _fields_ = [("value", c_double * 2)]


class _SheetTrimData(Structure):
    """PK_SURF_trim_data_t."""
    _fields_ = [
        ("n_spcurves", c_int),
        ("spcurves", POINTER(c_int)),
        ("intervals", POINTER(_SheetInterval)),
        ("trim_loop", POINTER(c_int)),
        ("trim_set", POINTER(c_int)),
    ]


class _SheetTrimOpts(Structure):
    """PK_SURF_make_sheet_trimmed_o_t."""
    _fields_ = [
        ("o_t_version", c_int),
        ("check_wires", c_ubyte),
        ("check_self_int", c_ubyte),
        ("check_loops", c_ubyte),
        ("nominal_geom", c_ubyte),
    ]


class _SheetSewOpts(Structure):
    """PK_BODY_sew_bodies_o_t (generous trailing pad)."""
    _fields_ = [
        ("o_t_version", c_int),
        ("set_global_tolerance", c_ubyte),
        ("allow_disjoint_result", c_ubyte),
        ("treat_as_manifold", c_ubyte),
        ("prefered_body_type", c_int),
        ("duplicate_removal", c_int),
        ("number_of_iterations", c_int),
        ("iteration_bounds", POINTER(c_double)),
        ("_pad", c_int * 8),
    ]


def _sheet_declare(pk) -> None:
    """Declare the sheet-building prototypes once per kernel handle."""
    pk.PK_PLANE_create.restype = c_int
    pk.PK_PLANE_create.argtypes = [POINTER(_SheetPlaneSf), POINTER(c_int)]
    pk.PK_BCURVE_create.restype = c_int
    pk.PK_BCURVE_create.argtypes = [POINTER(_SheetBcurveSf), POINTER(c_int)]
    pk.PK_SPCURVE_create.restype = c_int
    pk.PK_SPCURVE_create.argtypes = [POINTER(_SheetSpcurveSf), POINTER(c_int)]
    pk.PK_SURF_make_sheet_trimmed.restype = c_int
    pk.PK_SURF_make_sheet_trimmed.argtypes = [
        c_int, POINTER(_SheetTrimData), c_double, POINTER(_SheetTrimOpts),
        POINTER(c_int), POINTER(c_int)]
    pk.PK_BODY_sew_bodies.restype = c_int
    pk.PK_BODY_sew_bodies.argtypes = [
        c_int, POINTER(c_int), c_double, POINTER(_SheetSewOpts),
        POINTER(c_int), POINTER(c_void_p), POINTER(c_int), POINTER(c_void_p),
        POINTER(c_int), POINTER(c_void_p)]
    pk.PK_BODY_ask_faces.restype = c_int
    pk.PK_BODY_ask_faces.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
    pk.PK_FACE_make_solid_bodies.restype = c_int
    pk.PK_FACE_make_solid_bodies.argtypes = [
        c_int, POINTER(c_int), c_int, c_ubyte, POINTER(c_int),
        POINTER(c_void_p), POINTER(c_void_p)]


def _triangle_sheet(pk, a, b, c, precision=1e-6) -> int:
    """One trimmed planar sheet body for triangle (a, b, c) in metres."""
    import numpy as _np
    a = _np.asarray(a, dtype=_np.float64)
    b = _np.asarray(b, dtype=_np.float64)
    c = _np.asarray(c, dtype=_np.float64)
    n = _np.cross(b - a, c - a)
    nn = _np.linalg.norm(n)
    if nn < 1e-12:
        raise ValueError("degenerate triangle")
    n = n / nn
    xax = (b - a) / _np.linalg.norm(b - a)
    yax = _np.cross(n, xax)
    sf = _SheetPlaneSf()
    sf.data[0:3] = a
    sf.data[3:6] = n
    sf.data[6:9] = xax
    plane = c_int(0)
    rc = pk.PK_PLANE_create(byref(sf), byref(plane))
    if rc != 0:
        raise RuntimeError(f"PK_PLANE_create failed: {rc}")
    corners = [a, b, c]
    uvs = [_np.array([(p - a) @ xax, (p - a) @ yax]) for p in corners]
    spcs = []
    for e in range(3):
        p0 = uvs[e]
        p1 = uvs[(e + 1) % 3]
        verts = (c_double * 4)(p0[0], p0[1], p1[0], p1[1])
        kmult = (c_int * 2)(2, 2)
        knots = (c_double * 2)(0.0, 1.0)
        bsf = _SheetBcurveSf()
        memset(byref(bsf), 0, sizeof(bsf))
        bsf.degree = 1
        bsf.n_vertices = 2
        bsf.vertex_dim = 2
        bsf.vertex = verts
        bsf.form = 1
        bsf.n_knots = 2
        bsf.knot_mult = kmult
        bsf.knot = knots
        crv = c_int(0)
        r2 = pk.PK_BCURVE_create(byref(bsf), byref(crv))
        if r2 != 0:
            raise RuntimeError(f"PK_BCURVE_create failed: {r2}")
        ssf = _SheetSpcurveSf(plane.value, crv.value)
        spc = c_int(0)
        r3 = pk.PK_SPCURVE_create(byref(ssf), byref(spc))
        if r3 != 0:
            raise RuntimeError(f"PK_SPCURVE_create failed: {r3}")
        spcs.append(spc.value)
    spc_arr = (c_int * 3)(*spcs)
    ivs = (_SheetInterval * 3)(_SheetInterval((0.0, 1.0)),
                               _SheetInterval((0.0, 1.0)),
                               _SheetInterval((0.0, 1.0)))
    loops = (c_int * 3)(0, 0, 0)
    sets = (c_int * 3)(0, 0, 0)
    td = _SheetTrimData(3, spc_arr, ivs, loops, sets)
    sopts = _SheetTrimOpts()
    memset(byref(sopts), 0, sizeof(sopts))
    sopts.o_t_version = 1
    body = c_int(0)
    state = c_int(0)
    r4 = pk.PK_SURF_make_sheet_trimmed(plane.value, byref(td), precision,
                                       byref(sopts), byref(body),
                                       byref(state))
    if r4 != 0:
        raise RuntimeError(f"PK_SURF_make_sheet_trimmed failed: {r4}")
    return body.value


def triangles_to_brep(points, triangles, gap=1e-4) -> list:
    """Convert a triangle mesh (metres) into solid body tags.

    Classic Parasolid route (no Convergent Modeling needed): one trimmed
    planar sheet per triangle, ``PK_BODY_sew_bodies`` to stitch, then
    ``PK_FACE_make_solid_bodies`` per stitched sheet.  Returns the final
    solid body tags; raises RuntimeError when the kernel rejects the input.
    """
    if not available():
        raise RuntimeError("pskernel not available")
    import numpy as _np
    pts = _np.asarray(points, dtype=_np.float64)
    tris = _np.asarray(triangles, dtype=_np.int64)
    if tris.size == 0:
        return []
    sess = _ps._get_session()
    pk = sess.pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    _sheet_declare(pk)
    sheet_bodies = []
    for tri in tris:
        try:
            tag = _triangle_sheet(pk, pts[tri[0]], pts[tri[1]], pts[tri[2]])
            sheet_bodies.append(int(tag))
        except RuntimeError:
            continue  # degenerate triangle etc.
    if not sheet_bodies:
        return []
    solids = []
    if len(sheet_bodies) == 1:
        sewn = sheet_bodies
    else:
        arr = (c_int * len(sheet_bodies))(*sheet_bodies)
        sewo = _SheetSewOpts()
        memset(byref(sewo), 0, sizeof(sewo))
        sewo.o_t_version = 1
        sewo.treat_as_manifold = 1
        n_sewn = c_int(0)
        sewn_p = c_void_p()
        n_un = c_int(0)
        un_p = c_void_p()
        n_prob = c_int(0)
        prob_p = c_void_p()
        r5 = pk.PK_BODY_sew_bodies(len(sheet_bodies), arr, gap,
                                   byref(sewo), byref(n_sewn), byref(sewn_p),
                                   byref(n_un), byref(un_p), byref(n_prob),
                                   byref(prob_p))
        if r5 != 0:
            raise RuntimeError(f"PK_BODY_sew_bodies failed: {r5}")
        if n_sewn.value == 0:
            return []
        sewn = [int(t) for t in
                cast(sewn_p, POINTER(c_int * n_sewn.value)).contents]
    for body_tag in sewn:
        nf = c_int(0)
        faces_p = c_void_p()
        rc = pk.PK_BODY_ask_faces(int(body_tag), byref(nf), byref(faces_p))
        if rc != 0 or nf.value == 0:
            continue
        farr = cast(faces_p, POINTER(c_int * nf.value)).contents
        n_sol = c_int(0)
        sols_p = c_void_p()
        checks_p = c_void_p()
        r6 = pk.PK_FACE_make_solid_bodies(
            nf.value, farr, PK_FACE_heal_cap_c, 0, byref(n_sol),
            byref(sols_p), byref(checks_p))
        if r6 != 0 or n_sol.value == 0:
            continue
        for tag in cast(sols_p, POINTER(c_int * n_sol.value)).contents:
            # open sheets get "capped" into zero-volume solids; drop them
            # (STpre keeps open meshes out of the solid result).
            try:
                part = (sess.facet_body_adaptive(int(tag))
                        or sess.facet2(int(tag)) or sess.facet_go(int(tag)))
            except Exception:
                part = None
            if part is not None and len(part.triangles):
                vol = mesh_volume_m3(part.points, part.triangles)
                if abs(vol) < 1e-15:
                    continue
            solids.append(int(tag))
    return solids


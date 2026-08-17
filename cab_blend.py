# Parasolid V37 blend / chamfer ABI (decoded 2026-08-16 from STpreBase
# disassembly + live-kernel probes, docs/pskernel_user_guide.md 6.9).
#
# The old crash record (2-arg calls reading 0xFFFFFFFFFFFFFFFF) came from
# obsolete signatures.  The working V37 ABI:
#
#   PK_EDGE_set_blend_constant(n, edges[], radius, options, &n_out, &edges_out)
#       options o_t_version=1 (kernel current): {1, cliff_edge=0,
#       properties, xs_shape=0x56b9}
#   PK_EDGE_set_blend_chamfer(n, edges[], range_2, range_1, faces[]|NULL,
#       options, &n_out, &edges_out)
#       options o_t_version=1: {1, pad, properties, d1=1.0, d2=0.0}
#   PK_BODY_fix_blends(body, options, &n_blends, &blends, &unders, &topols,
#       &fault, &fault_edge, &fault_topol)
#       options o_t_version=1: {1, 0, 0, 0x5230, 0x523a, 0x5244, 0, NULL,
#       0x550a, 0, byte1}
#
# properties (PK_blend_properties_t, 0x30 bytes) is filled byte-exactly as
# STpre does (tokens 0x47ea/0x47f4/0x47fe/0x4809/0x4813/0x481c/0x4827,
# draw_fix=1, tolerance=1e-5, ribspace=0).
#
# Verified against the live kernel on a fresh PK_BODY_create_solid_block:
# constant blend radius 0.01 -> fix -> 1 blend face, 530 facet tris;
# chamfer 0.008/0.008 -> fix -> 1 blend face, 422 tris.
from __future__ import annotations

import ctypes as C
from typing import Optional


class BlendProperties(C.Structure):
    _fields_ = [
        ("propagate", C.c_int), ("vary", C.c_int), ("render_rib", C.c_int),
        ("draw_fix", C.c_ubyte), ("_pad", C.c_ubyte * 3),
        ("ov_smooth", C.c_int), ("ov_cliff", C.c_int),
        ("ov_cliff_end", C.c_int), ("ov_notch", C.c_int),
        ("tolerance", C.c_double), ("ribspace", C.c_double),
    ]


class ConstantBlendOptions(C.Structure):
    _fields_ = [
        ("o_t_version", C.c_int), ("cliff_edge", C.c_int),
        ("properties", BlendProperties), ("xs_shape", C.c_int),
    ]


class ChamferOptions(C.Structure):
    _fields_ = [
        ("o_t_version", C.c_int), ("_pad", C.c_int),
        ("properties", BlendProperties), ("d1", C.c_double),
        ("d2", C.c_double),
    ]


class FixBlendOptions(C.Structure):
    _fields_ = [
        ("o_t_version", C.c_int), ("f1", C.c_int), ("f2", C.c_int),
        ("f3", C.c_int), ("f4", C.c_int), ("f5", C.c_int),
        ("_pad1", C.c_int), ("ptr1", C.c_void_p), ("f6", C.c_int),
        ("_pad2", C.c_int), ("b1", C.c_ubyte), ("b2", C.c_ubyte),
        ("b3", C.c_ubyte), ("b4", C.c_ubyte),
    ]


def _default_properties() -> BlendProperties:
    p = BlendProperties()
    p.propagate = 0x47EA
    p.vary = 0x47F4
    p.render_rib = 0x47FE
    p.draw_fix = 1
    p.ov_smooth = 0x4809
    p.ov_cliff = 0x4813
    p.ov_cliff_end = 0x481C
    p.ov_notch = 0x4827
    p.tolerance = 1e-5
    p.ribspace = 0.0
    return p


def constant_blend_options() -> ConstantBlendOptions:
    o = ConstantBlendOptions()
    o.o_t_version = 1
    o.cliff_edge = 0
    o.properties = _default_properties()
    o.xs_shape = 0x56B9
    return o


def chamfer_options() -> ChamferOptions:
    o = ChamferOptions()
    o.o_t_version = 1
    o.properties = _default_properties()
    o.d1 = 1.0
    o.d2 = 0.0
    return o


def fix_blend_options() -> FixBlendOptions:
    o = FixBlendOptions()
    o.o_t_version = 1
    o.f2 = 0x5230
    o.f3 = 0x523A
    o.f4 = 0x5244
    o.f6 = 0x550A
    o.b1 = 1
    return o


def blend_edge(pk, edges, radius: float, *, chamfer: bool = False,
               range1: Optional[float] = None) -> tuple[int, int]:
    """Set a constant-radius blend (or chamfer) on edges; returns (rc, n)."""
    n_edges = len(edges)
    arr = (C.c_int * n_edges)(*[int(e) for e in edges])
    n_out = C.c_int(0)
    edges_out = C.c_void_p()
    if chamfer:
        fn = pk.PK_EDGE_set_blend_chamfer
        fn.restype = C.c_int
        fn.argtypes = [C.c_int, C.POINTER(C.c_int), C.c_double, C.c_double,
                       C.c_void_p, C.c_void_p, C.POINTER(C.c_int),
                       C.POINTER(C.c_void_p)]
        r1 = float(range1) if range1 is not None else float(radius)
        rc = fn(n_edges, arr, float(radius), r1, None,
                C.byref(chamfer_options()), C.byref(n_out),
                C.byref(edges_out))
    else:
        fn = pk.PK_EDGE_set_blend_constant
        fn.restype = C.c_int
        fn.argtypes = [C.c_int, C.POINTER(C.c_int), C.c_double, C.c_void_p,
                       C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
        rc = fn(n_edges, arr, float(radius),
                C.byref(constant_blend_options()), C.byref(n_out),
                C.byref(edges_out))
    return int(rc), int(n_out.value)


def fix_blends(pk, body: int) -> tuple[int, int, list[int]]:
    """Fix pending blends on a body; returns (rc, n_blends, blend_face_tags)."""
    fn = pk.PK_BODY_fix_blends
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.c_void_p, C.POINTER(C.c_int),
                   C.POINTER(C.c_void_p), C.POINTER(C.c_void_p),
                   C.POINTER(C.c_void_p), C.POINTER(C.c_int),
                   C.POINTER(C.c_int), C.POINTER(C.c_int)]
    n_blends = C.c_int(0)
    blends = C.c_void_p()
    unders = C.c_void_p()
    topols = C.c_void_p()
    fault = C.c_int(0)
    fault_edge = C.c_int(0)
    fault_topol = C.c_int(0)
    rc = fn(int(body), C.byref(fix_blend_options()), C.byref(n_blends),
            C.byref(blends), C.byref(unders), C.byref(topols),
            C.byref(fault), C.byref(fault_edge), C.byref(fault_topol))
    faces: list[int] = []
    if n_blends.value > 0 and blends.value:
        faces = [int(C.cast(blends, C.POINTER(C.c_int))[i])
                 for i in range(n_blends.value)]
    return int(rc), int(n_blends.value), faces


def find_g1_edges(pk, edge: int) -> list[int]:
    # Tangent-edge chain of an edge via PK_EDGE_find_g1_edges (blend
    # propagation: blending one edge of a smooth chain blends the chain).
    pk.PK_EDGE_find_g1_edges.restype = C.c_int
    pk.PK_EDGE_find_g1_edges.argtypes = [
        C.c_int, C.c_double, C.c_ubyte, C.POINTER(C.c_int),
        C.POINTER(C.c_void_p)]
    n = C.c_int(0)
    arr = C.c_void_p()
    if pk.PK_EDGE_find_g1_edges(int(edge), 0.01, 1, C.byref(n),
                                C.byref(arr)) != 0:
        return [int(edge)]
    if n.value <= 0 or not arr:
        return [int(edge)]
    return [int(C.cast(arr, C.POINTER(C.c_int))[i])
            for i in range(n.value)]



# ---------------------------------------------------------------------------
# R3.5: second-order geometry - variable-radius blends and spin sweeps.
#
# PK_EDGE_set_blend_variable (V37 legacy ABI, live-kernel verified):
#   options struct version 1 is only {o_t_version, properties} - 52 bytes,
#   NOT the V35 layout {.., rho_type, xs_shape}.  The kernel requires a
#   radius position at BOTH endpoints of the (open) edge chain; strictly
#   interior positions alone fail with rc 920.  With equal ranges off both
#   faces and all-zero rhos the cross-section stays circular, i.e. a true
#   variable-radius round whose radius varies smoothly along the edge.
#
#   rhos must be non-NULL even when all zero (NULL crashes the kernel).
# ---------------------------------------------------------------------------


class Vector3(C.Structure):
    """PK_VECTOR_t - Cartesian point / vector (double coord[3])."""
    _fields_ = [("coord", C.c_double * 3)]


class IntervalS(C.Structure):
    """PK_INTERVAL_t - a real interval (double value[2])."""
    _fields_ = [("value", C.c_double * 2)]


class BlendEdgeShape(C.Structure):
    """PK_blend_edge_shape_t - variable-radius rolling-ball blend shape.

    ranges_1[i]/ranges_2[i] are the blend ranges off the left/right face
    at positions[i]; equal ranges plus all-zero rhos give a circular
    (variable-radius round) cross-section."""
    _fields_ = [
        ("n_ranges", C.c_int),
        ("ranges_1", C.POINTER(C.c_double)),
        ("ranges_2", C.POINTER(C.c_double)),
        ("rhos", C.POINTER(C.c_double)),
        ("positions", C.POINTER(Vector3)),
    ]


class VariableBlendOptions(C.Structure):
    """PK_EDGE_set_blend_variable_o_t, V37 legacy version 1 (52 bytes)."""
    _fields_ = [
        ("o_t_version", C.c_int),
        ("properties", BlendProperties),
    ]


def _ask_edge_geometry(pk, edge: int):
    """PK_EDGE_ask_geometry -> (curve, ends, interval, sense) or None."""
    pk.PK_EDGE_ask_geometry.restype = C.c_int
    pk.PK_EDGE_ask_geometry.argtypes = [
        C.c_int, C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_int),
        C.POINTER(Vector3), C.POINTER(IntervalS), C.POINTER(C.c_int)]
    curve = C.c_int(0)
    cls = C.c_int(0)
    ends = (Vector3 * 2)()
    tint = IntervalS()
    sense = C.c_int(0)
    rc = pk.PK_EDGE_ask_geometry(int(edge), 1, C.byref(curve), C.byref(cls),
                                 ends, C.byref(tint), C.byref(sense))
    if rc != 0 or not curve.value:
        return None
    return (int(curve.value), [tuple(ends[i].coord) for i in range(2)],
            (float(tint.value[0]), float(tint.value[1])),
            int(sense.value))


def _curve_point(pk, curve: int, t: float):
    """Exact point on a curve via PK_CURVE_eval (n_derivs=0)."""
    pk.PK_CURVE_eval.restype = C.c_int
    pk.PK_CURVE_eval.argtypes = [
        C.c_int, C.c_double, C.c_int, C.POINTER(Vector3)]
    p = Vector3()
    rc = pk.PK_CURVE_eval(int(curve), float(t), 0, C.byref(p))
    if rc != 0:
        return None
    return tuple(float(v) for v in p.coord)


def variable_blend_edge(pk, edge: int, radii, *,
                        tolerance: float = 1e-5) -> tuple[int, int]:
    """Variable-radius blend on ONE edge (V37 legacy ABI, verified live).

    radii: sequence of (fraction, radius_m) pairs, 0 <= fraction <= 1
    measured along the edge from its start vertex to its end vertex.  The
    kernel demands a radius position at both chain endpoints, so f=0 and
    f=1 entries are added by linear extrapolation when missing (interior-
    only positions fail with rc 920).  The radius varies smoothly between
    the given positions and the cross-section remains circular.

    Returns (rc, n_blend_edges); follow with PK_BODY_fix_blends to make
    the blend part of the topology.
    """
    pts = sorted((float(f), float(r)) for f, r in radii)
    if len(pts) < 2:
        return 920, 0
    seen: list = []
    for f, r in pts:
        if not seen or abs(f - seen[-1][0]) > 1e-12:
            seen.append((f, r))
    pts = seen
    if pts[0][0] > 0.0:
        f0, r0 = pts[0]
        f1, r1 = pts[1]
        r = r0 + (0.0 - f0) * (r1 - r0) / (f1 - f0)
        pts.insert(0, (0.0, r))
    if pts[-1][0] < 1.0:
        f0, r0 = pts[-2]
        f1, r1 = pts[-1]
        r = r1 + (1.0 - f1) * (r1 - r0) / (f1 - f0)
        pts.append((1.0, r))
    geo = _ask_edge_geometry(pk, edge)
    if geo is None:
        return -1, 0
    curve, _ends, (t0, t1), _sense = geo
    n = len(pts)
    positions = (Vector3 * n)()
    for i, (f, _r) in enumerate(pts):
        p = _curve_point(pk, curve, t0 + f * (t1 - t0))
        if p is None:
            return -2, 0
        positions[i].coord[:] = p
    r1a = (C.c_double * n)(*[r for _f, r in pts])
    r2a = (C.c_double * n)(*[r for _f, r in pts])
    rhoa = (C.c_double * n)(*([0.0] * n))
    shape = BlendEdgeShape()
    shape.n_ranges = n
    shape.ranges_1 = C.cast(r1a, C.POINTER(C.c_double))
    shape.ranges_2 = C.cast(r2a, C.POINTER(C.c_double))
    shape.rhos = C.cast(rhoa, C.POINTER(C.c_double))
    shape.positions = C.cast(positions, C.POINTER(Vector3))
    opts = VariableBlendOptions()
    opts.o_t_version = 1
    opts.properties = _default_properties()
    opts.properties.tolerance = float(tolerance)
    pk.PK_EDGE_set_blend_variable.restype = C.c_int
    pk.PK_EDGE_set_blend_variable.argtypes = [
        C.c_int, BlendEdgeShape, C.c_void_p,
        C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    n_out = C.c_int(0)
    edges_out = C.c_void_p()
    rc = pk.PK_EDGE_set_blend_variable(int(edge), shape, C.byref(opts),
                                       C.byref(n_out), C.byref(edges_out))
    return int(rc), int(n_out.value)

def body_edges(pk, body: int) -> list[int]:
    """All edge tags of a body via PK_BODY_ask_edges."""
    pk.PK_BODY_ask_edges.restype = C.c_int
    pk.PK_BODY_ask_edges.argtypes = [
        C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_void_p)]
    n = C.c_int(0)
    arr = C.c_void_p()
    if pk.PK_BODY_ask_edges(int(body), C.byref(n), C.byref(arr)) != 0:
        return []
    return [int(C.cast(arr, C.POINTER(C.c_int))[i]) for i in range(n.value)]

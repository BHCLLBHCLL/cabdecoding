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

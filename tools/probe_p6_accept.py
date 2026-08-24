"""P6-2 几何验收：4 个 A 级算子黑盒调用 + facet 对拍（体积/包围盒变化）。

用法：& python tools/probe_p6_accept.py
"""
from __future__ import annotations

import ctypes as C
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ps_facet2_nodes as _ps  # noqa: E402
import cab_ps_ops  # noqa: E402
import cab_p6_ops  # noqa: E402


def vol_and_box(sess, tag):
    part = (sess.facet_body_adaptive(tag)
            or sess.facet2(tag) or sess.facet_go(tag))
    if part is None or part.triangles.size == 0:
        return None, None
    vol = cab_ps_ops.mesh_volume_m3(part.points, part.triangles)
    lo = part.points.min(0)
    hi = part.points.max(0)
    return vol, (tuple(lo), tuple(hi))


def main() -> int:
    sess = _ps._get_session()
    pk = sess.pk
    pk.PK_SESSION_set_check_arguments.restype = C.c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [C.c_int]
    pk.PK_SESSION_set_check_arguments(0)

    # --- hollow ---
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    v0, _ = vol_and_box(sess, b)
    rc = cab_p6_ops.hollow_body(b, -0.1, 1e-4)
    v1, _ = vol_and_box(sess, b)
    print(f"[hollow] rc={rc} vol {v0:.6f} -> {v1:.6f} "
          f"({'OK' if rc == 0 and v1 and v0 and v1 < v0 else 'FAIL'})", flush=True)

    # --- offset ---
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    v0, box0 = vol_and_box(sess, b)
    rc = cab_p6_ops.offset_body(b, 0.05, 1e-4)
    v1, box1 = vol_and_box(sess, b)
    ok = rc == 0 and v0 and v1 and v1 > v0 and box1[0][2] < box0[0][2]
    print(f"[offset] rc={rc} vol {v0:.6f} -> {v1:.6f} "
          f"({'OK' if ok else 'FAIL'})", flush=True)

    # --- replace ---
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    faces = sess.body_faces(b) or []
    top = None
    for f in faces:
        pl = sess.face_plane(f)
        if pl and pl[0][2] > 0.9:
            top = f
            break
    class _Axis1Sf(C.Structure):
        _fields_ = [("location", C.c_double * 3), ("axis", C.c_double * 3)]
    ax = _Axis1Sf()
    ax.location[:] = (0.0, 0.0, 1.2)
    ax.axis[:] = (0.0, 0.0, 1.0)
    surf = C.c_int(0)
    pk.PK_PLANE_create.restype = C.c_int
    pk.PK_PLANE_create.argtypes = [C.POINTER(_Axis1Sf), C.POINTER(C.c_int)]
    rp = pk.PK_PLANE_create(C.byref(ax), C.byref(surf))
    if rp == 0 and top:
        rc = cab_p6_ops.replace_faces(b, [top], [surf.value])
        _, box1 = vol_and_box(sess, b)
        ok = rc == 0 and box1 and abs(box1[1][2] - 1.2) < 1e-3
        print(f"[replace] rc={rc} top_z {box1[1][2]:.4f} "
              f"({'OK' if ok else 'FAIL'})", flush=True)
    else:
        print(f"[replace] plane create rc={rp} top={top} (skip)", flush=True)

    # --- imprint ---
    a = cab_ps_ops.create_solid_block((2.0, 2.0, 2.0))
    bb = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0), (0.5, 0, 0))
    e0 = len(sess.body_edges(a) or [])
    f0 = len(sess.body_faces(a) or [])
    faces_b = sess.body_faces(bb) or []
    out = cab_p6_ops.imprint_faces(a, faces_b)
    e1 = len(sess.body_edges(a) or [])
    f1 = len(sess.body_faces(a) or [])
    ok = (out["rc"] == 0 and out["n_edges"] > 0
          and e1 > e0 and f1 > f0)
    print(f"[imprint] rc={out['rc']} n_edges={out['n_edges']} "
          f"edges={out['edges'][:8]} edges {e0}->{e1} faces {f0}->{f1} "
          f"({'OK' if ok else 'FAIL'})", flush=True)

    # --- B 级 ---
    for name, fn in (("draft", cab_p6_ops.draft_body),
                     ("midsurface", cab_p6_ops.midsurface)):
        try:
            fn(0)
            print(f"[{name}] NOT-RAISED (unexpected)", flush=True)
        except cab_p6_ops.KernelNotSupportedError:
            print(f"[{name}] KernelNotSupportedError OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

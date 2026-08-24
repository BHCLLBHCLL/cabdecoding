"""P6-2 黑盒探针：按 V35 官方签名 live 调用 5 个算子，验证 rc 与几何结果。

签名已从 q-solid V35 官方文档核实（2023-12 生成，新式简化 API）：

  draft   PK_BODY_taper
          (body, n_refs_above, refs_above[], n_refs_below, refs_below[],
           parting_body, direction:VECTOR1, angle_above, angle_below,
           options, tracking, results)                                  12 参
  shell   PK_BODY_hollow_2
          (body, offset:double, tolerance:double, options, tracking, results)
  offset  PK_BODY_offset_2
          (body, offset:double, tolerance:double, options, tracking, results)
  replace PK_FACE_replace_surfs_2
          (n_faces, faces[], surfs[], senses[], tolerance:double,
           options, tracking, results)                                   8 参
  imprint PK_BODY_imprint_faces_2
          (body, n_faces, faces[], options, results, tracking)           6 参
          （注意 results 在 tracking 之前！）

options 用零化字节缓冲 + 按偏移写必需字段，尾部全零 = 全部默认值
（子结构 edge_data/vertex_data 等零值即为合法默认）。tracking/results
同样用零化大缓冲，内核只写结构前缀 + 分配数组指针，不会越界。

独立进程运行——签名仍可能出错导致的崩溃只影响本脚本。

用法：& python tools/probe_pk_operators_bb.py [taper|hollow|offset|replace|imprint|all]
"""
from __future__ import annotations

import ctypes as C
import math as _m
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ps_facet2_nodes as _ps  # noqa: E402
import cab_ps_ops  # noqa: E402

# --- 标准 token -----------------------------------------------------------
CHECK_YES, CHECK_NO = 21801, 21802  # PK_check_fa_fa_yes_c / no_c

PK_MAX = 32


class _ErrSF(C.Structure):
    _fields_ = [("function", C.c_char * PK_MAX),
                ("code", C.c_int),
                ("code_token", C.c_char * PK_MAX),
                ("severity", C.c_int),
                ("argument_number", C.c_int),
                ("argument_name", C.c_char * PK_MAX),
                ("argument_index", C.c_int),
                ("entity", C.c_int)]


def ask_last(pk) -> str:
    fn = pk.PK_ERROR_ask_last
    fn.restype = C.c_int
    fn.argtypes = [C.POINTER(C.c_int), C.POINTER(_ErrSF)]
    was = C.c_int(0)
    sf = _ErrSF()
    C.memset(C.byref(sf), 0, C.sizeof(sf))
    rc = fn(C.byref(was), C.byref(sf))
    if not was.value:
        return "(no error)"
    return (f"{sf.code_token.decode('utf-8', 'replace')} "
            f"sev={sf.severity} arg={sf.argument_name.decode('utf-8', 'replace')}")


class _Axis1Sf(C.Structure):
    _fields_ = [("location", C.c_double * 3), ("axis", C.c_double * 3)]


class _Vec3(C.Structure):
    _fields_ = [("v", C.c_double * 3)]


def _w(buf, off: int, val, ty=C.c_int):
    ty.from_buffer(buf, off).value = val


def _opts(fields: dict):
    """零化 options 缓冲，按字节偏移写入字段（未写字段=0=默认值）。"""
    buf = (C.c_byte * 128)()
    for off, (val, ty) in fields.items():
        _w(buf, off, val, ty)
    return buf


def _track():
    return (C.c_byte * 128)()


def _res(size=256):
    return (C.c_byte * size)()


def _tag(buf) -> int:
    return int((C.c_int).from_buffer(buf, 0).value)


def _carr(ints):
    return (C.c_int * max(1, len(ints)))(*[int(i) for i in ints])


def _mk_plane(pk, z) -> int:
    ax = _Axis1Sf()
    ax.location[:] = (0.0, 0.0, float(z))
    ax.axis[:] = (0.0, 0.0, 1.0)
    surf = C.c_int(0)
    pn = pk.PK_PLANE_create
    pn.restype = C.c_int
    pn.argtypes = [C.POINTER(_Axis1Sf), C.POINTER(C.c_int)]
    if pn(C.byref(ax), C.byref(surf)) != 0:
        return 0
    return int(surf.value)


def probe_taper(pk, sess) -> dict:
    body = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    faces = sess.body_faces(body) or []
    assert len(faces) >= 1
    top = None
    for f in faces:
        pl = sess.face_plane(f)
        if pl and pl[0][2] > 0.9:
            top = f
            break
    refs = cab_ps_ops.face_edges(pk, top) if top is not None else []
    refs = refs or [faces[0]]
    rarr = _carr(refs)
    dirv = _Vec3()
    dirv.v[:] = (0.0, 0.0, 1.0)
    fn = pk.PK_BODY_taper
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.c_int, C.POINTER(C.c_int),
                   C.c_int, C.POINTER(C.c_int), C.c_int,
                   C.POINTER(_Vec3), C.c_double, C.c_double,
                   C.c_void_p, C.c_void_p, C.c_void_p]
    out = {}
    # 扫描 (miter, method, 单边/四边)
    for miter in (0, 1):
        for method in (0, 1, 2):
            opts = _opts({0: (1, C.c_int),            # o_t_version
                            8: (1e-5, C.c_double),    # tolerance
                            16: (miter, C.c_int),     # miter_at_parting
                            20: (1, C.c_int),         # merge_face
                            24: (CHECK_NO, C.c_int),  # check_fa_fa
                            28: (method, C.c_int)})   # default_method
            track, res = _track(), _res()
            rc = fn(body, len(refs), rarr, 0, None, body, C.byref(dirv),
                    _m.radians(10.0), 0.0, C.cast(opts, C.c_void_p),
                    C.cast(track, C.c_void_p), C.cast(res, C.c_void_p))
            out[f"m={miter} d={method} r={len(refs)}"] = f"rc={rc} {ask_last(pk)}"
    # 单边引用
    one = _carr([refs[0]])
    for method in (0, 1, 2):
        opts = _opts({0: (1, C.c_int),
                        8: (1e-5, C.c_double),
                        16: (0, C.c_int),
                        20: (1, C.c_int),
                        24: (CHECK_NO, C.c_int),
                        28: (method, C.c_int)})
        track, res = _track(), _res()
        rc = fn(body, 1, one, 0, None, body, C.byref(dirv),
                _m.radians(10.0), 0.0, C.cast(opts, C.c_void_p),
                C.cast(track, C.c_void_p), C.cast(res, C.c_void_p))
        out[f"single m=0 d={method}"] = f"rc={rc} {ask_last(pk)}"
    return out


def probe_hollow(pk, sess) -> dict:
    body = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    opts = _opts({0: (1, C.c_int),            # o_t_version
                    16: (CHECK_NO, C.c_int)})   # check_fa_fa (offset 16)
    track, res = _track(), _res()
    fn = pk.PK_BODY_hollow_2
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.c_double, C.c_double,
                   C.c_void_p, C.c_void_p, C.c_void_p]
    rc = fn(body, -0.1, 1e-4, C.cast(opts, C.c_void_p),
            C.cast(track, C.c_void_p), C.cast(res, C.c_void_p))
    return {"rc": rc, "status": _tag(res)}


def probe_offset(pk, sess) -> dict:
    body = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    opts = _opts({0: (1, C.c_int),           # o_t_version
                    4: (0, C.c_int),           # allow_disjoint
                    8: (CHECK_NO, C.c_int)})   # check_fa_fa
    track, res = _track(), _res()
    fn = pk.PK_BODY_offset_2
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.c_double, C.c_double,
                   C.c_void_p, C.c_void_p, C.c_void_p]
    rc = fn(body, 0.05, 1e-4, C.cast(opts, C.c_void_p),
            C.cast(track, C.c_void_p), C.cast(res, C.c_void_p))
    return {"rc": rc, "status": _tag(res)}


def probe_replace(pk, sess) -> dict:
    body = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    faces = sess.body_faces(body) or []
    assert len(faces) >= 1
    surf = _mk_plane(pk, 1.2)
    if not surf:
        return {"rc": -1, "plane": "create-failed"}
    senses = _carr([1])
    farr = _carr([faces[0]])
    sarr = _carr([surf])
    opts = _opts({0: (1, C.c_int),            # o_t_version
                    4: (CHECK_NO, C.c_int)})    # check_fa_fa
    track, res = _track(), _res()
    fn = pk.PK_FACE_replace_surfs_2
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_int),
                   C.POINTER(C.c_int), C.c_double,
                   C.c_void_p, C.c_void_p, C.c_void_p]
    rc = fn(1, farr, sarr, senses, 1e-4, C.cast(opts, C.c_void_p),
            C.cast(track, C.c_void_p), C.cast(res, C.c_void_p))
    return {"rc": rc, "status": _tag(res)}


def probe_imprint(pk, sess) -> dict:
    body_a = cab_ps_ops.create_solid_block((2.0, 2.0, 2.0))
    body_b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    faces = sess.body_faces(body_b) or []
    farr = _carr(faces)
    opts = _opts({0: (1, C.c_int),        # o_t_version
                    4: (1, C.c_int),        # imprint_tool
                    8: (1, C.c_int)})       # imprint_overlapping
    track, res = _track(), _res()
    fn = pk.PK_BODY_imprint_faces_2
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.c_int, C.POINTER(C.c_int),
                   C.c_void_p, C.c_void_p, C.c_void_p]
    # 注意顺序：results 在第 5 参、tracking 在第 6 参
    rc = fn(body_a, len(faces), farr, C.cast(opts, C.c_void_p),
            C.cast(res, C.c_void_p), C.cast(track, C.c_void_p))
    n_edges = int((C.c_int).from_buffer(res, 0).value)
    return {"rc": rc, "n_edges": n_edges}


def probe_face_taper(pk, sess) -> dict:
    body = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    faces = sess.body_faces(body) or []
    assert len(faces) >= 1
    top = None
    for f in faces:
        pl = sess.face_plane(f)
        if pl and pl[0][2] > 0.9:
            top = f
            break
    top = top or faces[0]
    ax = _Axis1Sf()
    ax.location[:] = (0.0, 0.0, 0.5)
    ax.axis[:] = (0.0, 0.0, 1.0)
    opts = _opts({0: (1, C.c_int),            # o_t_version
                    8: (1e-5, C.c_double),    # tolerance?
                    16: (1, C.c_int)})
    track, res = _track(), _res()
    fn = pk.PK_FACE_taper
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.POINTER(_Axis1Sf), C.c_double,
                   C.c_void_p, C.c_void_p, C.c_void_p]
    out = {}
    for ver in (1, 2, 3, 4, 5):
        opts = _opts({0: (ver, C.c_int)})
        track, res = _track(), _res()
        rc = fn(top, C.byref(ax), _m.radians(10.0), C.cast(opts, C.c_void_p),
                C.cast(track, C.c_void_p), C.cast(res, C.c_void_p))
        out[f"v{ver}"] = f"rc={rc} {ask_last(pk)}"
    return out


PROBES = {
    "taper": probe_taper,
    "hollow": probe_hollow,
    "offset": probe_offset,
    "replace": probe_replace,
    "imprint": probe_imprint,
    "face_taper": probe_face_taper,
}


def main() -> int:
    sel = sys.argv[1] if len(sys.argv) > 1 else "all"
    if sel == "all":
        names = list(PROBES)
    else:
        names = [sel]
    prog = _ps.find_cradle_programs()
    print(f"KERNEL: {prog}", flush=True)
    sess = _ps._get_session()
    pk = sess.pk
    pk.PK_SESSION_set_check_arguments.restype = C.c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [C.c_int]
    pk.PK_SESSION_set_check_arguments(0)
    for name in names:
        try:
            out = PROBES[name](pk, sess)
        except Exception as exc:  # noqa: BLE001
            out = {"error": f"{type(exc).__name__}: {exc}"}
        print(f"[{name}] {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

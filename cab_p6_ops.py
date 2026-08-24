"""P6: PK 内核几何编辑六算子（hollow/offset/replace/imprint A 级，draft/midsurface B 级）。

P6-2 逐算子 ABI 校准成果（2026-08-24，V37 内核实测）：

  A 级（rc=0 黑盒验证 + 几何变化验证）：
    shell    -> PK_BODY_hollow_2(body, offset, tol, opts, track, res)
    offset   -> PK_BODY_offset_2(body, offset, tol, opts, track, res)
    replace  -> PK_FACE_replace_surfs_2(n, faces, surfs, senses, tol, opts, track, res)
    imprint  -> PK_BODY_imprint_faces_2(body, n_faces, faces, opts, res, track)
                KEY：public options 偏移 0x08 必须为 NULL（本内核把该 qword 当
                工具体列表指针；传入任何列表/标签都会导致
                PK_ERROR_bad_tolerance(1043)）。o_t_version=1，枚举字段填
                token（0x58fc/0x5906/0x60ff/0x616d）。
                results 布局 = {ptr,count} 对 x4（edges/vertices/target_faces/
                tool_faces），与 V35 文档 {count,ptr} 相反（实测）。

  B 级（无可用导出，定档见 DEV_SUMMARY 附录）：
    draft     -> PK_BODY_taper 全配置 PK_ERROR_not_implemented(5000)；
                 PK_FACE_taper 全版本 PK_ERROR_o_t_version_unknown(5022)。
    midsurface-> pskernel 无导出。
"""

from __future__ import annotations

import math
from ctypes import (
    POINTER, Structure, byref, cast, c_double, c_int, c_ubyte, c_void_p,
    memset, sizeof,
)
from typing import Optional

try:
    import ps_facet2_nodes as _ps
except Exception:  # pragma: no cover
    _ps = None

# --- 内核 token（V37 实测 / V35 文档）--------------------------------------
PK_check_fa_fa_yes_c = 21801
PK_check_fa_fa_no_c = 21802
# imprint 枚举（反汇编转换器默认值 + token 扫描）
_IMPRINT_COMPLETE_NO = 0x58FC     # PK_imprint_complete_no_c
_IMPRINT_EXTEND_TANGENT = 0x5906  # PK_imprint_extend_tangent_c
_IMPRINT_DIR_NO_CHECK = 0x60FF    # PK_imprint_dir_no_check_c
_IMPRINT_UPDATE_DEFAULT = 0x616D  # PK_boolean_update_default_c


class _P6TrackR(Structure):
    """PK_TOPOL_track_r_t（5 指针宽）。"""
    _fields_ = [
        ("n_track_records", c_int),
        ("track_records", c_void_p),
        ("internal_origs", c_void_p),
        ("internal_classes", c_void_p),
        ("internal_prods", c_void_p),
    ]


class _HollowOpts(Structure):
    """PK_BODY_hollow_o_t（实测布局：tolerance@8, check_fa_fa@0x10）。"""
    _fields_ = [
        ("o_t_version", c_int),       # 0x00
        ("_p4", c_int),               # 0x04
        ("tolerance", c_double),      # 0x08
        ("check_fa_fa", c_int),       # 0x10
    ]


class _OffsetOpts(Structure):
    """PK_BODY_offset_o_t（V35 布局：allow_disjoint@4, check_fa_fa@8）。"""
    _fields_ = [
        ("o_t_version", c_int),       # 0x00
        ("allow_disjoint", c_int),    # 0x04
        ("check_fa_fa", c_int),       # 0x08
    ]


class _ReplaceOpts(Structure):
    """PK_FACE_replace_surfs_o_t（check_fa_fa@4）。"""
    _fields_ = [
        ("o_t_version", c_int),       # 0x00
        ("check_fa_fa", c_int),       # 0x04
    ]


class _ImprintOpts(Structure):
    """PK_BODY_imprint_faces_o_t（V37 实测布局）。

    KEY：0x08 的 qword 必须为 NULL —— 本内核把该字段当工具体列表指针，
    传非 NULL 会触发 PK_ERROR_bad_tolerance(1043)（工具列表解析后几何
    阶段失败）。枚举字段直接填 token 值（0x58fc 等，无翻译）。
    """
    _fields_ = [
        ("o_t_version", c_int),            # 0x00
        ("imprint_tool", c_ubyte),         # 0x04 LOGICAL
        ("imprint_overlapping", c_ubyte),  # 0x05
        ("extend_face_list", c_ubyte),     # 0x06
        ("_p7", c_ubyte),                  # 0x07
        ("_tool_list", c_void_p),          # 0x08 必须 NULL
        ("complete_targ", c_int),          # 0x10
        ("extend_targ", c_int),            # 0x14
        ("complete_tool", c_int),          # 0x18
        ("extend_tool", c_int),            # 0x1c
        ("dir", c_int),                    # 0x20
        ("update", c_int),                 # 0x24
        ("have_tol", c_ubyte),             # 0x28
        ("_p29", c_ubyte * 7),             # 0x29..0x2f
        ("tolerance", c_double),           # 0x30
    ]


class _ImprintR(Structure):
    """PK_imprint_r_t（V37 实测布局：{ptr, count} 对 x4）。"""
    _fields_ = [
        ("edges", c_void_p),           # 0x00
        ("n_edges", c_int),            # 0x08
        ("vertices", c_void_p),        # 0x10
        ("n_vertices", c_int),         # 0x18
        ("target_faces", c_void_p),    # 0x20
        ("n_target_faces", c_int),     # 0x28
        ("tool_faces", c_void_p),      # 0x30
        ("n_tool_faces", c_int),       # 0x38
    ]


def available() -> bool:
    return _ps is not None and _ps.available()


def _session():
    sess = _ps._get_session()
    sess.pk.PK_SESSION_set_check_arguments.restype = c_int
    sess.pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    sess.pk.PK_SESSION_set_check_arguments(0)
    return sess


def hollow_body(body_tag: int, offset: float, tolerance: float = 1e-4) -> int:
    """``PK_BODY_hollow_2`` 抽壳（offset<0 向内抽）。返回内核 rc。"""
    if not available():
        raise RuntimeError("pskernel not available")
    pk = _session().pk
    opts = _HollowOpts()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 1
    opts.tolerance = float(tolerance)
    opts.check_fa_fa = PK_check_fa_fa_no_c
    track = _P6TrackR()
    res = _P6TrackR()
    memset(byref(track), 0, sizeof(track))
    memset(byref(res), 0, sizeof(res))
    fn = pk.PK_BODY_hollow_2
    fn.restype = c_int
    fn.argtypes = [c_int, c_double, c_double, c_void_p, c_void_p, c_void_p]
    return int(fn(int(body_tag), float(offset), float(tolerance),
                  byref(opts), byref(track), byref(res)))


def offset_body(body_tag: int, offset: float, tolerance: float = 1e-4) -> int:
    """``PK_BODY_offset_2`` 整体偏移。返回内核 rc。"""
    if not available():
        raise RuntimeError("pskernel not available")
    pk = _session().pk
    opts = _OffsetOpts()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 1
    opts.allow_disjoint = 0
    opts.check_fa_fa = PK_check_fa_fa_no_c
    track = _P6TrackR()
    res = _P6TrackR()
    memset(byref(track), 0, sizeof(track))
    memset(byref(res), 0, sizeof(res))
    fn = pk.PK_BODY_offset_2
    fn.restype = c_int
    fn.argtypes = [c_int, c_double, c_double, c_void_p, c_void_p, c_void_p]
    return int(fn(int(body_tag), float(offset), float(tolerance),
                  byref(opts), byref(track), byref(res)))


def replace_faces(body_tag: int, face_tags: list[int],
                  surf_tags: list[int], senses: Optional[list[int]] = None,
                  tolerance: float = 1e-4) -> int:
    """``PK_FACE_replace_surfs_2`` 用曲面替换面。返回内核 rc。"""
    if not available():
        raise RuntimeError("pskernel not available")
    if not face_tags or len(face_tags) != len(surf_tags):
        raise ValueError("face/surf tag lists must be non-empty and equal")
    pk = _session().pk
    senses = senses or [1] * len(face_tags)
    opts = _ReplaceOpts()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 1
    opts.check_fa_fa = PK_check_fa_fa_no_c
    n = len(face_tags)
    farr = (c_int * n)(*[int(t) for t in face_tags])
    sarr = (c_int * n)(*[int(t) for t in surf_tags])
    sense_arr = (c_int * n)(*[int(s) for s in senses])
    track = _P6TrackR()
    res = _P6TrackR()
    memset(byref(track), 0, sizeof(track))
    memset(byref(res), 0, sizeof(res))
    fn = pk.PK_FACE_replace_surfs_2
    fn.restype = c_int
    fn.argtypes = [c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int),
                   c_double, c_void_p, c_void_p, c_void_p]
    return int(fn(n, farr, sarr, sense_arr, float(tolerance),
                  byref(opts), byref(track), byref(res)))


def imprint_faces(body_tag: int, tool_face_tags: list[int],
                  imprint_tool: bool = False,
                  tolerance: float = 0.0) -> dict:
    """``PK_BODY_imprint_faces_2`` 压印：把 tool 面的边压到 body 上。

    KEY（本会话破解）：options 0x08 置 NULL，o_t_version=1，枚举填 token。
    返回 {"rc", "n_edges", "edges": [...], "n_vertices", "vertices": [...]}。
    """
    if not available():
        raise RuntimeError("pskernel not available")
    if not tool_face_tags:
        raise ValueError("no tool faces")
    pk = _session().pk
    opts = _ImprintOpts()
    memset(byref(opts), 0, sizeof(opts))
    opts.o_t_version = 1
    opts.imprint_tool = 1 if imprint_tool else 0
    opts.complete_targ = _IMPRINT_COMPLETE_NO
    opts.extend_targ = _IMPRINT_EXTEND_TANGENT
    opts.complete_tool = _IMPRINT_COMPLETE_NO
    opts.extend_tool = _IMPRINT_EXTEND_TANGENT
    opts.dir = _IMPRINT_DIR_NO_CHECK
    opts.update = _IMPRINT_UPDATE_DEFAULT
    opts.have_tol = 1 if tolerance > 0 else 0
    opts.tolerance = float(tolerance)
    n = len(tool_face_tags)
    farr = (c_int * n)(*[int(t) for t in tool_face_tags])
    res = _ImprintR()
    trk = _P6TrackR()
    memset(byref(res), 0, sizeof(res))
    memset(byref(trk), 0, sizeof(trk))
    fn = pk.PK_BODY_imprint_faces_2
    fn.restype = c_int
    fn.argtypes = [c_int, c_int, POINTER(c_int), c_void_p, c_void_p, c_void_p]
    rc = int(fn(int(body_tag), n, farr, byref(opts), byref(res), byref(trk)))
    edges = []
    if res.n_edges > 0 and res.edges:
        try:
            edges = [int(cast(res.edges, POINTER(c_int))[i])
                     for i in range(res.n_edges)]
        except (OSError, ValueError):
            edges = []
    vertices = []
    if res.n_vertices > 0 and res.vertices:
        try:
            vertices = [int(cast(res.vertices, POINTER(c_int))[i])
                        for i in range(res.n_vertices)]
        except (OSError, ValueError):
            vertices = []
    return {"rc": rc, "n_edges": res.n_edges, "edges": edges,
            "n_vertices": res.n_vertices, "vertices": vertices}


class KernelNotSupportedError(NotImplementedError):
    """B 级定档：该内核无可用导出实现。"""


def draft_body(body_tag: int, *args, **kwargs):
    """B 级：PK_BODY_taper not_implemented / PK_FACE_taper 版本未知。"""
    raise KernelNotSupportedError(
        "draft(PK_BODY_taper) 在本内核返回 PK_ERROR_not_implemented(5000)，"
        "B 级定档；请用 Edit Solid 现有面操作代替")


def midsurface(body_tag: int, *args, **kwargs):
    """B 级：pskernel 无 midsurface 导出。"""
    raise KernelNotSupportedError(
        "midsurface 无 PK 导出，B 级定档；请用 STpre 中面流程代替")

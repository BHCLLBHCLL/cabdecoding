"""P6: PK 内核几何编辑六算子测试（hollow/offset/replace/imprint A 级 + draft/midsurface B 级）。

覆盖：
- 4 个 A 级算子 rc=0 + 几何变化（facet 体积/包围盒/拓扑对拍）
- imprint 关键约束回归：options 0x08 置 NULL（非 NULL → 1043 bad_tolerance）
- results 布局 {ptr,count} 对（n_edges 读取正确）
- B 级算子（draft/midsurface）抛 KernelNotSupportedError
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ctypes as C
import pytest

import cab_p6_ops
import cab_ps_ops

pytestmark = pytest.mark.skipif(
    not cab_p6_ops.available(), reason="pskernel not available")


def _sess():
    return cab_p6_ops._session()


def _vol(sess, tag):
    part = (sess.facet_body_adaptive(tag)
            or sess.facet2(tag) or sess.facet_go(tag))
    if part is None or part.triangles.size == 0:
        return None, None, None
    return (cab_ps_ops.mesh_volume_m3(part.points, part.triangles),
            part.points.min(0), part.points.max(0))


# ---------------------------------------------------------------- shell
def test_hollow_reduces_volume():
    sess = _sess()
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    v0, _, _ = _vol(sess, b)
    rc = cab_p6_ops.hollow_body(b, -0.1, 1e-4)
    v1, _, _ = _vol(sess, b)
    assert rc == 0
    assert v0 is not None and v1 is not None
    assert v1 < v0  # 抽壳后体积变小
    assert v1 > 0.3  # 仍为实心壳（未塌缩）


# ---------------------------------------------------------------- offset
def test_offset_grows_block():
    sess = _sess()
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    v0, lo0, _ = _vol(sess, b)
    rc = cab_p6_ops.offset_body(b, 0.05, 1e-4)
    v1, lo1, _ = _vol(sess, b)
    assert rc == 0
    assert v1 is not None and v0 is not None
    assert v1 == pytest.approx(1.1 ** 3, rel=1e-2)  # 每侧 +0.05
    assert lo1[0] < lo0[0]  # 包围盒外扩


# ---------------------------------------------------------------- replace
def test_replace_moves_face_to_plane():
    sess = _sess()
    pk = sess.pk
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0))
    faces = sess.body_faces(b) or []
    top = None
    for f in faces:
        pl = sess.face_plane(f)
        if pl and pl[0][2] > 0.9:
            top = f
            break
    assert top is not None
    class _Axis1Sf(C.Structure):
        _fields_ = [("location", C.c_double * 3), ("axis", C.c_double * 3)]
    ax = _Axis1Sf()
    ax.location[:] = (0.0, 0.0, 1.2)
    ax.axis[:] = (0.0, 0.0, 1.0)
    surf = C.c_int(0)
    pk.PK_PLANE_create.restype = C.c_int
    pk.PK_PLANE_create.argtypes = [C.POINTER(_Axis1Sf), C.POINTER(C.c_int)]
    assert pk.PK_PLANE_create(C.byref(ax), C.byref(surf)) == 0
    rc = cab_p6_ops.replace_faces(b, [top], [surf.value])
    _, _, hi = _vol(sess, b)
    assert rc == 0
    assert abs(hi[2] - 1.2) < 1e-3  # 顶面被换到 z=1.2 平面


# ---------------------------------------------------------------- imprint
def test_imprint_adds_edges_and_returns_them():
    sess = _sess()
    a = cab_ps_ops.create_solid_block((2.0, 2.0, 2.0))
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0), (0.5, 0, 0))
    e0 = len(sess.body_edges(a) or [])
    f0 = len(sess.body_faces(a) or [])
    faces_b = sess.body_faces(b) or []
    out = cab_p6_ops.imprint_faces(a, faces_b)
    assert out["rc"] == 0
    assert out["n_edges"] > 0
    assert len(out["edges"]) == out["n_edges"]
    e1 = len(sess.body_edges(a) or [])
    f1 = len(sess.body_faces(a) or [])
    assert e1 > e0 and f1 > f0  # 目标体被压印出新边/新面


def test_imprint_tool_list_null_is_key():
    """回归：options 0x08 必须为 NULL；填工具体列表 → PK_ERROR_bad_tolerance(1043)。"""
    sess = _sess()
    pk = sess.pk
    a = cab_ps_ops.create_solid_block((2.0, 2.0, 2.0))
    b = cab_ps_ops.create_solid_block((1.0, 1.0, 1.0), (0.5, 0, 0))
    faces = sess.body_faces(b) or []
    farr = (C.c_int * len(faces))(*faces)

    class _BL(C.Structure):
        _fields_ = [("version", C.c_int), ("count", C.c_int),
                    ("array", C.c_void_p)]
    class _BA(C.Structure):
        _fields_ = [("version", C.c_int), ("body", C.c_int)]
    ba = _BA()
    ba.version = 1
    ba.body = b
    bl = _BL()
    bl.version = 1
    bl.count = 1
    bl.array = C.cast(C.byref(ba), C.c_void_p)

    opts = cab_p6_ops._ImprintOpts()
    C.memset(C.byref(opts), 0, C.sizeof(opts))
    opts.o_t_version = 1
    opts.complete_targ = 0x58FC
    opts.extend_targ = 0x5906
    opts.complete_tool = 0x58FC
    opts.extend_tool = 0x5906
    opts.dir = 0x60FF
    opts.update = 0x616D
    # 非 NULL 工具体列表 → 1043
    opts._tool_list = C.cast(C.byref(bl), C.c_void_p)
    res = cab_p6_ops._ImprintR()
    trk = cab_p6_ops._P6TrackR()
    fn = pk.PK_BODY_imprint_faces_2
    fn.restype = C.c_int
    fn.argtypes = [C.c_int, C.c_int, C.POINTER(C.c_int),
                   C.c_void_p, C.c_void_p, C.c_void_p]
    rc_bad = int(fn(a, len(faces), farr, C.byref(opts),
                    C.byref(res), C.byref(trk)))
    assert rc_bad != 0  # 1043 PK_ERROR_bad_tolerance

    # 置 NULL → rc=0
    opts._tool_list = None
    rc_ok = int(fn(a, len(faces), farr, C.byref(opts),
                   C.byref(res), C.byref(trk)))
    assert rc_ok == 0


# ---------------------------------------------------------------- B 级
def test_draft_is_b_level():
    with pytest.raises(cab_p6_ops.KernelNotSupportedError, match="draft"):
        cab_p6_ops.draft_body(0)


def test_midsurface_is_b_level():
    with pytest.raises(cab_p6_ops.KernelNotSupportedError, match="midsurface"):
        cab_p6_ops.midsurface(0)


def test_available_flag():
    assert cab_p6_ops.available() is True

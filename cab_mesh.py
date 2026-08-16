"""M4: meshing (Mesh -> Meshing).

Generates the ``<element>`` occupancy table from the ``<mesh_block>`` axes
and the tessellated CAD surfaces:

1. cell centres are computed on the structured grid;
2. every part is classified cell-by-cell with an even-odd ray cast (+X)
   against its triangle surface (parity per cell);
3. panel / open-surface parts (attribute ``panel`` or kind ``panel`` /
   ``quad_panel``) use face-thin occupancy instead of solid ray cast;
4. occupied cells are merged into i/j/k boxes and written back as
   ``<element><parts name=...><body><list>`` entries (1-based inclusive
   ``i1,i2,j1,j2,k1,k2,0,1,1``), plus the Domain ``<analysis>`` box.

v1 limitations (documented, to be refined with STpre golden data):
- cells exactly on a surface are resolved with a small epsilon;
- panel face-thin marks cells whose centres lie near a triangle
  (half-cell band); not a full STpre panel scheme;
- merge is a greedy axis-aligned box merge, not STpre's exact run encoding.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

import cab_vtk
from cabxml import StpreModel


def _inside_yz(a: np.ndarray, b: np.ndarray, c: np.ndarray,
               y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """2D point-in-triangle test on the yz projection (vectorised)."""
    def cross(p, q, r):
        return (q[1] - p[1]) * (r[1] - p[1]) - \
            (q[0] - p[0]) * (r[0] - p[0])
    d1 = (b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (y - a[0])
    d2 = (c[0] - b[0]) * (z - b[1]) - (c[1] - b[1]) * (y - b[0])
    d3 = (a[0] - c[0]) * (z - c[1]) - (a[1] - c[1]) * (y - c[0])
    has_neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    has_pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return ~(has_neg & has_pos)


def classify_part_cells(xc: np.ndarray, yc: np.ndarray, zc: np.ndarray,
                        pts: np.ndarray, tris: np.ndarray,
                        cell_range: Optional[tuple[int, int, int, int, int, int]]
                        = None, samples: str = "center",
                        edge_eps: float = 0.0) -> np.ndarray:
    """Even-odd +X ray cast of one closed part over the cell grid.

    ``xc/yc/zc`` are cell centres (metres).  Returns a bool mask of shape
    ``(len(xc), len(yc), len(zc))``.  ``edge_eps`` (metres) is the STpre
    Edge tolerance: candidate cells near a surface and the boundary-hit
    test are expanded by it, so a larger value recognizes parts as larger.
    """
    if samples == "corners":
        ni, nj, nk = len(xc), len(yc), len(zc)
        votes = np.zeros((ni, nj, nk), dtype=np.int32)
        hx = np.zeros(ni)
        hy = np.zeros(nj)
        hz = np.zeros(nk)
        hx[1:-1] = (xc[2:] - xc[:-2]) / 4.0
        hy[1:-1] = (yc[2:] - yc[:-2]) / 4.0
        hz[1:-1] = (zc[2:] - zc[:-2]) / 4.0
        if ni > 1:
            hx[0] = hx[1] if ni > 2 else (xc[1] - xc[0]) / 2.0
            hx[-1] = hx[-2] if ni > 2 else (xc[-1] - xc[-2]) / 2.0
        if nj > 1:
            hy[0] = hy[1] if nj > 2 else (yc[1] - yc[0]) / 2.0
            hy[-1] = hy[-2] if nj > 2 else (yc[-1] - yc[-2]) / 2.0
        if nk > 1:
            hz[0] = hz[1] if nk > 2 else (zc[1] - zc[0]) / 2.0
            hz[-1] = hz[-2] if nk > 2 else (zc[-1] - zc[-2]) / 2.0
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    votes += classify_part_cells(
                        xc + sx * hx, yc + sy * hy, zc + sz * hz,
                        pts, tris, cell_range=cell_range,
                        samples="center", edge_eps=edge_eps).astype(np.int32)
        return votes >= 5
    ni, nj, nk = len(xc), len(yc), len(zc)
    mask = np.zeros((ni, nj, nk), dtype=np.int32)
    if tris is None or len(tris) == 0 or len(pts) == 0:
        return mask.astype(bool)
    i0, i1, j0, j1, k0, k1 = cell_range or (0, ni - 1, 0, nj - 1, 0, nk - 1)
    i0 = max(0, i0); i1 = min(ni - 1, i1)
    j0 = max(0, j0); j1 = min(nj - 1, j1)
    k0 = max(0, k0); k1 = min(nk - 1, k1)
    if i0 > i1 or j0 > j1 or k0 > k1:
        return mask.astype(bool)
    tri = pts[tris]  # (T,3,3)
    tmin = tri.min(axis=1)
    tmax = tri.max(axis=1)
    eps = max(float(edge_eps), 1e-10)
    for t in range(len(tri)):
        a, b, c = tri[t]
        n = np.cross(b - a, c - a)
        if abs(n[0]) < 1e-12:
            continue  # ray (+X) parallel to the triangle plane
        # candidate j/k from the yz bbox, i from centres left of tmax x
        jj0 = max(j0, int(np.searchsorted(
            yc, tmin[t, 1] - eps, "left")))
        jj1 = min(j1, int(np.searchsorted(
            yc, tmax[t, 1] + eps, "right")) - 1)
        kk0 = max(k0, int(np.searchsorted(
            zc, tmin[t, 2] - eps, "left")))
        kk1 = min(k1, int(np.searchsorted(
            zc, tmax[t, 2] + eps, "right")) - 1)
        ii1 = min(i1, int(np.searchsorted(
            xc, tmax[t, 0] + eps, "right")) - 1)
        if jj0 > jj1 or kk0 > kk1 or ii1 < i0:
            continue
        Y, Z = np.meshgrid(yc[jj0:jj1 + 1], zc[kk0:kk1 + 1],
                           indexing="ij")
        # Perturb the ray origin slightly so rays that pass exactly through a
        # shared triangle edge (a common case on uniform grids) are counted
        # by exactly one of the two adjacent triangles.
        scale = max(float(zc[-1] - zc[0]), 1e-12)
        Y = Y + 1e-11 * scale
        Z = Z + 2e-11 * scale
        inside = _inside_yz(
            np.array([a[1], a[2]]), np.array([b[1], b[2]]),
            np.array([c[1], c[2]]), Y, Z)
        # x on the triangle plane at (y,z): a + (n_y*(y-a_y)+n_z*(z-a_z))/(-n_x)
        x_int = a[0] + (n[1] * (Y - a[1]) + n[2] * (Z - a[2])) / (-n[0])
        for i in range(i0, ii1 + 1):
            # samples exactly on the surface count as inside (boundary cells)
            hit = inside & (xc[i] < x_int + eps)
            if hit.any():
                mask[i, jj0:jj1 + 1, kk0:kk1 + 1] ^= hit
    return mask.astype(bool)


_PANEL_KINDS = frozenset({"panel", "quad_panel"})
_PANEL_ATTRS = frozenset({"panel", "sheet", "open"})

# ---------------------------------------------------------------------------
# R9-B: cut-cell 分类（Option -> Cut Cell Setting）
#
# 离线考证（手册 + CradleCFD_2023.2 官方样本）：
# - 手册 HTML_STpre_Eng/Cutcell_Setting.html：[Criteria] 为实数
#   0 < c < 1（min 1e-10, max 0.9999，默认 0.05）。单元内 cut-cell 零件
#   体积分数 >= 1-Criteria 记完全覆盖（solid）；< Criteria 记流体；
#   介于中间为部分单元（cut cell）。Criteria 越大越接近楼梯近似。
# - 样本 Exercise_e/Function/exA23-2/exA23-2b_cut_cell_e.s：开启后 .s
#   发射 CUTCELL_OPTION(volume_min_ratio, thin_shape_model) 与
#   CUTCELL_GAP 段；cut-cell 零件的 PARTS 盒列表移入 .ccel 二进制。
# - 样本 exA23-2b_cut_cell.cab XML：零件级注册 = <parts> 下
#   <cutcell> T </cutcell>；analysis_set 存 cutcell_criteria 等全局值
#   （staircase 版也有这些 analysis_set 值但不发射 .s 段——零件级
#   注册才是真开关）。
# 本实现的体积分数按零件 AABB 与格的解析交（对齐盒零件精确，
# 曲面零件为一级近似）。
# ---------------------------------------------------------------------------

CUTCELL_CRITERIA_MIN = 1e-10      # 手册下限
CUTCELL_CRITERIA_MAX = 0.9999     # 手册上限
CUTCELL_CRITERIA_DEFAULT = 0.05   # 手册默认


def clamp_cutcell_criteria(value: float) -> float:
    """把 criteria 钳制到手册范围 [1e-10, 0.9999]。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return CUTCELL_CRITERIA_DEFAULT
    return min(max(v, CUTCELL_CRITERIA_MIN), CUTCELL_CRITERIA_MAX)


def cell_volume_fractions(x_edges: np.ndarray, y_edges: np.ndarray,
                          z_edges: np.ndarray,
                          lo, hi) -> np.ndarray:
    """每个格与轴对齐盒 ``[lo, hi]`` 的相交体积分数（解析，向量化）。

    ``x/y/z_edges`` 是格边界坐标表（长度 ni+1/nj+1/nk，米），返回
    ``(ni, nj, nk)`` 分数表：1.0 = 格完全在盒内，0.0 = 完全在外，
    中间值 = 按三轴重叠长度比例的乘积（盒面平直切割的精确解）。
    """
    x_edges = np.asarray(x_edges, float)
    y_edges = np.asarray(y_edges, float)
    z_edges = np.asarray(z_edges, float)
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)

    def _axis_frac(edges: np.ndarray, a: float, b: float) -> np.ndarray:
        width = edges[1:] - edges[:-1]
        width = np.where(width > 0.0, width, 1e-300)
        ov = np.minimum(edges[1:], b) - np.maximum(edges[:-1], a)
        return np.clip(ov, 0.0, None) / width

    fx = _axis_frac(x_edges, lo[0], hi[0])
    fy = _axis_frac(y_edges, lo[1], hi[1])
    fz = _axis_frac(z_edges, lo[2], hi[2])
    return fx[:, None, None] * fy[None, :, None] * fz[None, None, :]


def classify_part_cells_cut(x_edges: np.ndarray, y_edges: np.ndarray,
                            z_edges: np.ndarray, lo, hi,
                            criteria: float = CUTCELL_CRITERIA_DEFAULT
                            ) -> tuple[np.ndarray, np.ndarray]:
    """cut-cell 近似分类一个零件（AABB 体积分数）。

    返回 ``(mask, fractions)``：

    - ``fractions`` 为每格体积分数表（见 :func:`cell_volume_fractions`）；
    - ``mask`` 按手册 [Criteria] 判据二值化：分数 >= 1-criteria 记
      solid 占用（与 :func:`classify_part_cells` 相同的掩码语义），
      其余格不占用；``criteria <= 分数 < 1-criteria`` 的格即
      "cut cell"（部分单元），由分数表承载。

    ``criteria`` 钳制到 [1e-10, 0.9999]；0.5 时退化为中点二值化
    （楼梯近似），趋近 0 时 solid 掩码只含几乎全满的格。
    """
    crit = clamp_cutcell_criteria(criteria)
    fracs = cell_volume_fractions(x_edges, y_edges, z_edges, lo, hi)
    return fracs >= (1.0 - crit), fracs


def set_part_cutcell(model: StpreModel, part_name: str, enabled: bool
                     ) -> bool:
    """注册/取消一个零件的 cut-cell 零件标记（工程级，存 XML）。

    样本 exA23-2b_cut_cell.cab 实证格式：``<parts>`` 下
    ``<cutcell> T </cutcell>``；取消注册即删除该子节点。
    返回 False 当零件不存在。panel 零件按手册不支持 cut-cell，
    调用方负责过滤（本函数不强制）。
    """
    import xml.etree.ElementTree as ET
    p = model.find_part(part_name)
    if p is None:
        return False
    old = p.find("cutcell")
    if enabled:
        if old is None:
            e = ET.SubElement(p, "cutcell")
            e.tail = "\n         "
        old = p.find("cutcell")
        old.text = " T "
    elif old is not None:
        p.remove(old)
    return True


def part_cutcell_enabled(model: StpreModel, part_name: str) -> bool:
    """零件是否注册为 cut-cell 零件（无 <cutcell> 或文本非 T 均为否）。"""
    p = model.find_part(part_name)
    if p is None:
        return False
    e = p.find("cutcell")
    return e is not None and (e.text or "").strip().upper() in ("T", "1")


def is_panel_part(kind: str = "", attribute: str = "") -> bool:
    """True when the part should use face-thin (open surface) occupancy."""
    k = (kind or "").strip().lower()
    a = (attribute or "").strip().lower()
    return k in _PANEL_KINDS or a in _PANEL_ATTRS


def classify_panel_cells(xc: np.ndarray, yc: np.ndarray, zc: np.ndarray,
                         pts: np.ndarray, tris: np.ndarray,
                         cell_range: Optional[tuple[int, int, int, int, int, int]]
                         = None, face_search: float = 1.0) -> np.ndarray:
    """Face-thin occupancy: cells whose centres lie near a triangle.

    Marks a one-cell band around each open surface so panel / sheet parts
    are not ignored by the solid even-odd ray cast (which yields empty
    masks on non-watertight geometry).  ``face_search`` is the STpre
    "Search range for element face" in multiples of the cell width.
    """
    ni, nj, nk = len(xc), len(yc), len(zc)
    mask = np.zeros((ni, nj, nk), dtype=bool)
    if tris is None or len(tris) == 0 or len(pts) == 0:
        return mask
    i0, i1, j0, j1, k0, k1 = cell_range or (0, ni - 1, 0, nj - 1, 0, nk - 1)
    i0 = max(0, i0); i1 = min(ni - 1, i1)
    j0 = max(0, j0); j1 = min(nj - 1, j1)
    k0 = max(0, k0); k1 = min(nk - 1, k1)
    if i0 > i1 or j0 > j1 or k0 > k1:
        return mask

    def _full(centers: np.ndarray) -> np.ndarray:
        n = len(centers)
        w = np.zeros(n)
        if n >= 2:
            w[1:-1] = (centers[2:] - centers[:-2]) / 2.0
            w[0] = centers[1] - centers[0]
            w[-1] = centers[-1] - centers[-2]
        else:
            w[:] = 1e-6
        return np.maximum(w, 1e-12)

    fs = max(float(face_search), 0.0)
    wx, wy, wz = _full(xc), _full(yc), _full(zc)
    tri = pts[tris]
    tmin = tri.min(axis=1)
    tmax = tri.max(axis=1)
    for t in range(len(tri)):
        a, b, c = tri[t]
        n = np.cross(b - a, c - a)
        area2 = np.linalg.norm(n)
        if area2 < 1e-18:
            continue
        n_unit = n / area2
        # bbox expanded by the search range (multiples of cell width)
        pad = max(float(wx.max()), float(wy.max()), float(wz.max())) * fs
        ii0 = max(i0, int(np.searchsorted(xc, tmin[t, 0] - pad, "left")))
        ii1 = min(i1, int(np.searchsorted(xc, tmax[t, 0] + pad, "right")) - 1)
        jj0 = max(j0, int(np.searchsorted(yc, tmin[t, 1] - pad, "left")))
        jj1 = min(j1, int(np.searchsorted(yc, tmax[t, 1] + pad, "right")) - 1)
        kk0 = max(k0, int(np.searchsorted(zc, tmin[t, 2] - pad, "left")))
        kk1 = min(k1, int(np.searchsorted(zc, tmax[t, 2] + pad, "right")) - 1)
        if ii0 > ii1 or jj0 > jj1 or kk0 > kk1:
            continue
        v0 = c - a
        v1 = b - a
        dot00 = float(np.dot(v0, v0))
        dot01 = float(np.dot(v0, v1))
        dot11 = float(np.dot(v1, v1))
        denom = dot00 * dot11 - dot01 * dot01
        if abs(denom) < 1e-24:
            continue
        inv = 1.0 / denom
        Xs, Ys, Zs = np.meshgrid(
            xc[ii0:ii1 + 1], yc[jj0:jj1 + 1], zc[kk0:kk1 + 1],
            indexing="ij")
        HX, HY, HZ = np.meshgrid(
            wx[ii0:ii1 + 1], wy[jj0:jj1 + 1], wz[kk0:kk1 + 1],
            indexing="ij")
        dx = Xs - a[0]
        dy = Ys - a[1]
        dz = Zs - a[2]
        dist = np.abs(n_unit[0] * dx + n_unit[1] * dy + n_unit[2] * dz)
        band = fs * (abs(n_unit[0]) * HX + abs(n_unit[1]) * HY
                     + abs(n_unit[2]) * HZ) + 1e-12
        near = dist <= band
        if not near.any():
            continue
        # project onto plane then barycentric
        px = Xs - n_unit[0] * (n_unit[0] * dx + n_unit[1] * dy
                               + n_unit[2] * dz)
        py = Ys - n_unit[1] * (n_unit[0] * dx + n_unit[1] * dy
                               + n_unit[2] * dz)
        pz = Zs - n_unit[2] * (n_unit[0] * dx + n_unit[1] * dy
                               + n_unit[2] * dz)
        v2x = px - a[0]
        v2y = py - a[1]
        v2z = pz - a[2]
        dot02 = v0[0] * v2x + v0[1] * v2y + v0[2] * v2z
        dot12 = v1[0] * v2x + v1[1] * v2y + v1[2] * v2z
        u = (dot11 * dot02 - dot01 * dot12) * inv
        v = (dot00 * dot12 - dot01 * dot02) * inv
        inside = near & (u >= -0.05) & (v >= -0.05) & ((u + v) <= 1.05)
        if inside.any():
            mask[ii0:ii1 + 1, jj0:jj1 + 1, kk0:kk1 + 1] |= inside
    return mask


def classify_part_cells_grid(centers3: np.ndarray, pts: np.ndarray,
                             tris: np.ndarray,
                             edge_eps: float = 0.0) -> np.ndarray:
    """Even-odd +X ray cast over an arbitrary 3-D cell-centre grid.

    ``centers3`` has shape ``(ni, nj, nk, 3)`` (Cartesian metres) and the
    returned mask keeps the same index space — used for cylindrical
    R/θ/Z grids whose Cartesian centres are not separable per axis.
    """
    ni, nj, nk, _ = centers3.shape
    mask = np.zeros((ni, nj, nk), dtype=np.int32)
    if tris is None or len(tris) == 0 or len(pts) == 0:
        return mask.astype(bool)
    X = centers3[..., 0]
    Y = centers3[..., 1]
    Z = centers3[..., 2]
    tri = pts[tris]
    tmin = tri.min(axis=1)
    tmax = tri.max(axis=1)
    eps = max(float(edge_eps), 1e-10)
    scale = max(float(np.ptp(X)), float(np.ptp(Y)), float(np.ptp(Z)), 1e-12)
    for t in range(len(tri)):
        a, b, c = tri[t]
        n = np.cross(b - a, c - a)
        if abs(n[0]) < 1e-12:
            continue  # ray (+X) parallel to the triangle plane
        # candidate cells must lie LEFT of the triangle plane (ray +X);
        # no lower x bound — like the separable path's per-triangle i range.
        sel = ((X <= tmax[t, 0] + eps)
               & (Y >= tmin[t, 1] - eps) & (Y <= tmax[t, 1] + eps)
               & (Z >= tmin[t, 2] - eps) & (Z <= tmax[t, 2] + eps))
        if not sel.any():
            continue
        Xs = X[sel]
        Ys = Y[sel] + 1e-11 * scale
        Zs = Z[sel] + 2e-11 * scale
        inside = _inside_yz(
            np.array([a[1], a[2]]), np.array([b[1], b[2]]),
            np.array([c[1], c[2]]), Ys, Zs)
        x_int = a[0] + (n[1] * (Ys - a[1]) + n[2] * (Zs - a[2])) / (-n[0])
        hit = inside & (Xs < x_int + eps)
        if hit.any():
            mask[sel] ^= hit
    return mask.astype(bool)


def classify_panel_cells_grid(centers3: np.ndarray, pts: np.ndarray,
                              tris: np.ndarray,
                              face_search: float = 1.0) -> np.ndarray:
    """Face-thin band over an arbitrary 3-D cell-centre grid (cylindrical)."""
    ni, nj, nk, _ = centers3.shape
    mask = np.zeros((ni, nj, nk), dtype=bool)
    if tris is None or len(tris) == 0 or len(pts) == 0:
        return mask
    fs = max(float(face_search), 0.0)
    X = centers3[..., 0]
    Y = centers3[..., 1]
    Z = centers3[..., 2]
    tri = pts[tris]
    tmin = tri.min(axis=1)
    tmax = tri.max(axis=1)
    # conservative cell-width estimate for the band
    width = max(
        float(np.median(np.abs(np.diff(np.unique(X))))),
        float(np.median(np.abs(np.diff(np.unique(Y))))),
        float(np.median(np.abs(np.diff(np.unique(Z))))),
        1e-12)
    pad = width * fs
    for t in range(len(tri)):
        a, b, c = tri[t]
        n = np.cross(b - a, c - a)
        area2 = float(np.linalg.norm(n))
        if area2 < 1e-18:
            continue
        n_unit = n / area2
        sel = ((X >= tmin[t, 0] - pad) & (X <= tmax[t, 0] + pad)
               & (Y >= tmin[t, 1] - pad) & (Y <= tmax[t, 1] + pad)
               & (Z >= tmin[t, 2] - pad) & (Z <= tmax[t, 2] + pad))
        if not sel.any():
            continue
        Xs = X[sel]
        Ys = Y[sel]
        Zs = Z[sel]
        dx = Xs - a[0]
        dy = Ys - a[1]
        dz = Zs - a[2]
        dist = np.abs(n_unit[0] * dx + n_unit[1] * dy + n_unit[2] * dz)
        near = dist <= pad + 1e-12
        if not near.any():
            continue
        px = Xs - n_unit[0] * (n_unit[0] * dx + n_unit[1] * dy
                               + n_unit[2] * dz)
        py = Ys - n_unit[1] * (n_unit[0] * dx + n_unit[1] * dy
                               + n_unit[2] * dz)
        pz = Zs - n_unit[2] * (n_unit[0] * dx + n_unit[1] * dy
                               + n_unit[2] * dz)
        v0 = c - a
        v1 = b - a
        v2x = px - a[0]
        v2y = py - a[1]
        v2z = pz - a[2]
        dot00 = float(v0 @ v0)
        dot01 = float(v0 @ v1)
        dot11 = float(v1 @ v1)
        denom = dot00 * dot11 - dot01 * dot01
        if abs(denom) < 1e-24:
            continue
        inv = 1.0 / denom
        dot02 = v0[0] * v2x + v0[1] * v2y + v0[2] * v2z
        dot12 = v1[0] * v2x + v1[1] * v2y + v1[2] * v2z
        uu = (dot11 * dot02 - dot01 * dot12) * inv
        vv = (dot00 * dot12 - dot01 * dot02) * inv
        inside = near & (uu >= -0.05) & (vv >= -0.05) & ((uu + vv) <= 1.05)
        if inside.any():
            mask[sel] |= inside
    return mask


def _merge_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int, int, int]]:
    """Greedy merge of occupied cells into 1-based inclusive boxes."""
    boxes: list[tuple[int, int, int, int, int, int]] = []
    ni, nj, nk = mask.shape
    for j in range(nj):
        for k in range(nk):
            i = 0
            while i < ni:
                if not mask[i, j, k]:
                    i += 1
                    continue
                i2 = i
                while i2 + 1 < ni and mask[i2 + 1, j, k]:
                    i2 += 1
                boxes.append((i, i2, j, j, k, k))
                i = i2 + 1
    changed = True
    while changed:
        changed = False
        merged: list[tuple[int, int, int, int, int, int]] = []
        used = [False] * len(boxes)
        for x in range(len(boxes)):
            if used[x]:
                continue
            cur = boxes[x]
            for y in range(x + 1, len(boxes)):
                if used[y]:
                    continue
                o = boxes[y]
                # merge along j
                if (cur[0] == o[0] and cur[1] == o[1]
                        and cur[4] == o[4] and cur[5] == o[5]
                        and abs(cur[3] - o[2]) <= 1
                        and (cur[2] <= o[3] + 1 and o[2] <= cur[3] + 1)):
                    cur = (cur[0], cur[1], min(cur[2], o[2]),
                           max(cur[3], o[3]), cur[4], cur[5])
                    used[y] = True
                    changed = True
                elif (cur[0] == o[0] and cur[1] == o[1]
                      and cur[2] == o[2] and cur[3] == o[3]
                      and abs(cur[5] - o[4]) <= 1
                      and (cur[4] <= o[5] + 1 and o[4] <= cur[5] + 1)):
                    cur = (cur[0], cur[1], cur[2], cur[3],
                           min(cur[4], o[4]), max(cur[5], o[5]))
                    used[y] = True
                    changed = True
            merged.append(cur)
            used[x] = True
        boxes = merged
    return [(a + 1, b + 1, c + 1, d + 1, e + 1, f + 1)
            for a, b, c, d, e, f in boxes]


def classify_cells(axes_mm: dict[str, list[float]], parts: list,
                   transforms: Optional[dict[str, str]] = None,
                   progress: Optional[Callable[[int, int], None]] = None
                   , samples: str = "center",
                   part_kinds: Optional[dict[str, str]] = None,
                   part_attrs: Optional[dict[str, str]] = None,
                   edge_eps: float = 0.0,
                   face_search: float = 1.0,
                   element_threshold: float = 0.5,
                   workers: int = 1,
                   coordinate: str = "cartesian",
                   cutcell: bool = False,
                   cutcell_criteria: float = CUTCELL_CRITERIA_DEFAULT,
                   return_cutcell: bool = False,
                   ):
    """Classify every part against the structured grid.

    Returns ``(analysis_box, part_boxes)``; boxes are 1-based inclusive
    ``(i1,i2,j1,j2,k1,k2)``.  ``parts`` are TessPart-like objects with
    ``.name/.points/.triangles`` in metres.

    Panel / open-surface parts (see :func:`is_panel_part`) use
    :func:`classify_panel_cells` (face-thin band) instead of solid ray cast.

    ``edge_eps`` / ``face_search`` / ``element_threshold`` map to the STpre
    Mesh:Set division → Others meshing parameters:

    * ``edge_eps`` — edge tolerance (m), expands surface-hit classification;
    * ``face_search`` — search range for element face (multiples of cell
      width), used as the panel band width;
    * ``element_threshold`` — reference point inside a cell (0..1, 0.5 =
      centre); shifts the ray-cast sample along the cell diagonal.

    R9-B cut-cell（Option -> Cut Cell Setting 开启时）：

    * ``cutcell`` — 开启后 solid 零件改走 :func:`classify_part_cells_cut`
      （零件 AABB 体积分数分类，分数 >= 1-criteria 记 solid），边界格
      的部分占用由分数表承载；panel 零件与圆柱坐标格不走 cut 路径
      （手册：panel 不可注册 cut-cell；分数仅对笛卡尔格有解析交）。
    * ``cutcell_criteria`` — 手册 [Criteria]（默认 0.05，钳制
      [1e-10, 0.9999]）。
    * ``return_cutcell`` — True 时返回三元组
      ``(analysis_box, part_boxes, part_fractions)``，分数表按零件名
      索引（未走 cut 路径的零件不出现在表中）；False 保持二元组返回
      （既有调用/e2e 零回归）。
    """
    coord = (coordinate or "cartesian").strip().lower()
    x = np.asarray(axes_mm.get("x", []), float) / 1000.0
    if coord == "cylindrical":
        y = np.asarray(axes_mm.get("y", []), float)      # theta in degrees
    else:
        y = np.asarray(axes_mm.get("y", []), float) / 1000.0
    z = np.asarray(axes_mm.get("z", []), float) / 1000.0
    if len(x) < 2 or len(y) < 2 or len(z) < 2:
        raise ValueError("mesh_block needs at least 2 points per axis")
    xc = 0.5 * (x[:-1] + x[1:])
    yc = 0.5 * (y[:-1] + y[1:])
    zc = 0.5 * (z[:-1] + z[1:])
    ni, nj, nk = len(xc), len(yc), len(zc)
    centers3: Optional[np.ndarray] = None
    if coord == "cylindrical":
        R, TH, ZZ = np.meshgrid(xc, yc, zc, indexing="ij")
        thr = np.deg2rad(TH)
        centers3 = np.stack(
            [R * np.cos(thr), R * np.sin(thr), ZZ], axis=-1)
    if samples == "center" and abs(float(element_threshold) - 0.5) > 1e-9:
        def _widths(c: np.ndarray) -> np.ndarray:
            w = np.zeros(len(c))
            if len(c) >= 2:
                w[1:-1] = (c[2:] - c[:-2]) / 2.0
                w[0] = c[1] - c[0]
                w[-1] = c[-1] - c[-2]
            return np.maximum(w, 1e-12)
        shift = float(element_threshold) - 0.5
        xc_use = xc + shift * _widths(xc)
        yc_use = yc + shift * _widths(yc)
        zc_use = zc + shift * _widths(zc)
    else:
        xc_use, yc_use, zc_use = xc, yc, zc
    transforms = transforms or {}
    part_kinds = part_kinds or {}
    part_attrs = part_attrs or {}
    part_boxes: dict[str, list[tuple[int, int, int, int, int, int]]] = {}
    cutcell_fracs: dict[str, np.ndarray] = {}   # R9-B: 每零件体积分数表

    def _classify_part(part) -> Optional[list[tuple[int, int, int, int, int, int]]]:
        if coord == "cylindrical":
            if centers3 is None:
                return None
            pts = np.asarray(part.points, dtype=np.float64)
            tris = np.asarray(part.triangles, dtype=np.int64)
            if len(pts) == 0 or len(tris) == 0:
                return None
            pts = cab_vtk._apply_transform(
                pts, transforms.get(part.name, ""))
            kind = part_kinds.get(part.name, getattr(part, "kind", "") or "")
            attr = part_attrs.get(
                part.name, getattr(part, "attribute", "") or "")
            if is_panel_part(kind, attr):
                mask = classify_panel_cells_grid(
                    centers3, pts, tris, face_search=face_search)
            else:
                mask = classify_part_cells_grid(
                    centers3, pts, tris, edge_eps=edge_eps)
            if mask.any():
                return _merge_boxes(mask)
            return None
        pts = np.asarray(part.points, dtype=np.float64)
        tris = np.asarray(part.triangles, dtype=np.int64)
        if len(pts) == 0 or len(tris) == 0:
            return None
        pts = cab_vtk._apply_transform(
            pts, transforms.get(part.name, ""))
        lo = pts.min(0)
        hi = pts.max(0)
        kind = part_kinds.get(part.name, getattr(part, "kind", "") or "")
        attr = part_attrs.get(
            part.name, getattr(part, "attribute", "") or "")
        panel = is_panel_part(kind, attr)
        # Thin panels often sit between cell centres — expand by ~half cell.
        if panel:
            def _pad(centers: np.ndarray) -> float:
                if len(centers) < 2:
                    return 1e-6
                return float(np.median(np.diff(centers))) * 0.51
            pad = (_pad(xc), _pad(yc), _pad(zc))
            xc_b, yc_b, zc_b = xc, yc, zc
        else:
            eps = max(float(edge_eps), 1e-9)
            pad = (eps, eps, eps)
            xc_b, yc_b, zc_b = xc_use, yc_use, zc_use
        i0 = max(0, int(np.searchsorted(xc_b, lo[0] - pad[0], "left")))
        i1 = min(ni - 1, int(np.searchsorted(
            xc_b, hi[0] + pad[0], "right")) - 1)
        j0 = max(0, int(np.searchsorted(yc_b, lo[1] - pad[1], "left")))
        j1 = min(nj - 1, int(np.searchsorted(
            yc_b, hi[1] + pad[1], "right")) - 1)
        k0 = max(0, int(np.searchsorted(zc_b, lo[2] - pad[2], "left")))
        k1 = min(nk - 1, int(np.searchsorted(
            zc_b, hi[2] + pad[2], "right")) - 1)
        if i0 > i1 or j0 > j1 or k0 > k1:
            return None
        if panel:
            mask = classify_panel_cells(
                xc, yc, zc, pts, tris,
                cell_range=(i0, i1, j0, j1, k0, k1),
                face_search=face_search)
        elif cutcell:
            # R9-B cut-cell：solid 零件按 AABB 体积分数分类（分数表
            # 记录边界格的部分占用；分数 >= 1-criteria 记 solid）。
            mask, fracs = classify_part_cells_cut(
                x, y, z, lo, hi, criteria=cutcell_criteria)
            cutcell_fracs[part.name] = fracs
        else:
            mask = classify_part_cells(
                xc_use, yc_use, zc_use, pts, tris,
                cell_range=(i0, i1, j0, j1, k0, k1), samples=samples,
                edge_eps=edge_eps)
        if mask.any():
            return _merge_boxes(mask)
        return None

    parts_list = list(parts)
    workers = max(1, int(workers or 1))
    if workers > 1 and len(parts_list) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_classify_part, p): p
                       for p in parts_list}
            done = 0
            for fut in as_completed(futures):
                part = futures[fut]
                boxes = fut.result()
                if boxes:
                    part_boxes[part.name] = boxes
                done += 1
                if progress is not None:
                    progress(done, len(parts_list))
    else:
        for idx, part in enumerate(parts_list):
            boxes = _classify_part(part)
            if boxes:
                part_boxes[part.name] = boxes
            if progress is not None:
                progress(idx + 1, len(parts_list))
    analysis_box = (1, ni, 1, nj, 1, nk)
    if return_cutcell:
        return analysis_box, part_boxes, cutcell_fracs
    return analysis_box, part_boxes


def apply_elements(model: StpreModel, analysis_name: str,
                   analysis_box: tuple[int, int, int, int, int, int],
                   part_boxes: dict[str, list[tuple[int, int, int, int, int, int]]]
                   ) -> None:
    """Write the ``<element>`` section (replaces an existing one)."""
    import xml.etree.ElementTree as ET

    old = model.doc.root.find("element")
    if old is not None:
        model.doc.root.remove(old)
    el = ET.Element("element")
    el.tail = "\n"
    an = ET.SubElement(el, "analysis")
    an.attrib["name"] = analysis_name
    an.tail = "\n   "
    body = ET.SubElement(an, "body")
    body.attrib["num"] = "1"
    body.tail = "\n      "
    lst = ET.SubElement(body, "list")
    lst.attrib["no"] = "1"
    lst.text = " " + ",".join(str(v) for v in analysis_box) + " "
    lst.tail = "\n      "
    for name, boxes in part_boxes.items():
        p = ET.SubElement(el, "parts")
        p.attrib["name"] = name
        p.tail = "\n   "
        pb = ET.SubElement(p, "body")
        pb.attrib["num"] = str(len(boxes))
        pb.tail = "\n      "
        for n, box in enumerate(boxes, start=1):
            l = ET.SubElement(pb, "list")
            l.attrib["no"] = str(n)
            l.text = " " + ",".join(str(v) for v in box) + " "
            l.tail = "\n      "
    model.doc.root.append(el)


def update_part_elements(model: StpreModel, part_name: str,
                         boxes: list[tuple[int, int, int, int, int, int]]
                         ) -> bool:
    """Create/replace the ``<element>/<parts name=...>`` entry of one part.

    Used by [Meshing of specified part] (Gridding dialog, Others tab).
    Returns False when no ``<element>`` section exists yet (run full
    Meshing first).
    """
    import xml.etree.ElementTree as ET

    el = model.elements()
    if el is None:
        return False
    for parts in el.findall("parts"):
        if parts.attrib.get("name") == part_name:
            el.remove(parts)
    p = ET.SubElement(el, "parts")
    p.attrib["name"] = part_name
    p.tail = "\n   "
    pb = ET.SubElement(p, "body")
    pb.attrib["num"] = str(len(boxes))
    pb.tail = "\n      "
    for n, box in enumerate(boxes, start=1):
        l = ET.SubElement(pb, "list")
        l.attrib["no"] = str(n)
        l.text = " " + ",".join(str(v) for v in box) + " "
        l.tail = "\n      "
    return True


def cell_mask_from_boxes(ni: int, nj: int, nk: int,
                         boxes: list[list[int]]) -> np.ndarray:
    """0-based boolean occupancy mask of 1-based inclusive i/j/k boxes."""
    mask = np.zeros((ni, nj, nk), dtype=bool)
    for b in boxes:
        if len(b) < 6:
            continue
        i0, i1, j0, j1, k0, k1 = [int(v) for v in b[:6]]
        i0 = max(0, i0 - 1); i1 = min(ni - 1, i1 - 1)
        j0 = max(0, j0 - 1); j1 = min(nj - 1, j1 - 1)
        k0 = max(0, k0 - 1); k1 = min(nk - 1, k1 - 1)
        if i0 <= i1 and j0 <= j1 and k0 <= k1:
            mask[i0:i1 + 1, j0:j1 + 1, k0:k1 + 1] = True
    return mask


def _boxes_from_mask(mask: np.ndarray) -> list[tuple[int, int, int, int, int, int]]:
    """Merge an occupancy mask back into 1-based inclusive boxes."""
    return _merge_boxes(mask)


def toggle_cells_effective(model: StpreModel, part_name: str,
                           cells: list[tuple[int, int, int]],
                           effective: bool) -> int:
    """Add/remove individual cells (1-based i/j/k) to/from a part's elements.

    Returns the number of box-list entries of the part after the edit
    (0 when the part has no ``<element>`` entry and cells were removed).
    Used by [Mesh] - [Editing Mesh] (-> Effective / -> Ineffective).
    """
    axes = model.mesh_axes()
    ni = max(len(axes.get("x", [])), 1) - 1
    nj = max(len(axes.get("y", [])), 1) - 1
    nk = max(len(axes.get("z", [])), 1) - 1
    if ni < 1 or nj < 1 or nk < 1:
        return 0
    boxes = [list(b) for b in model.part_boxes(part_name)]
    mask = cell_mask_from_boxes(ni, nj, nk, boxes)
    for (i, j, k) in cells:
        if 1 <= i <= ni and 1 <= j <= nj and 1 <= k <= nk:
            mask[i - 1, j - 1, k - 1] = effective
    new_boxes = _boxes_from_mask(mask)
    update_part_elements(model, part_name, new_boxes)
    return len(new_boxes)


def classify_interferences(model: StpreModel, max_gap: int = 2
                           ) -> list[tuple[str, str, str]]:
    """Element-level interference classification of every part pair.

    Statuses match the STpre [Checking Parts Interferences] dialog:

    - ``Interference`` — index boxes overlap (share at least one cell);
    - ``Contact``      — boxes touch on a face (no shared cell, but faces
      are adjacent in index space);
    - ``Separation``   — boxes are within ``max_gap`` cells of each other
      (close enough that STpre reports a separation/contact candidate).

    Shape-level geometry (CAD surfaces) is not resolved here; the element
    occupancy table is used as the part shape (phase-1 approximation).
    """
    el = model.elements()
    if el is None:
        return []
    boxes: dict[str, list[list[int]]] = {}
    for parts in el.findall("parts"):
        name = parts.attrib.get("name", "")
        if name:
            b = model.part_boxes(name)
            if b:
                boxes[name] = b

    def overlap(a: list[int], b: list[int]) -> bool:
        # strict: sharing only a face (<= on one axis) is a Contact, not an
        # Interference (the shared face does not consume any cells)
        return all(a[i] < b[i + 1] and b[i] < a[i + 1] for i in (0, 2, 4))

    def contact(a: list[int], b: list[int]) -> bool:
        """Face adjacency: no axis leaves a gap (touch or shared face)."""
        for i in (0, 2, 4):
            if max(a[i] - b[i + 1] - 1, b[i] - a[i + 1] - 1, 0) > 0:
                return False
        return True

    def gap(a: list[int], b: list[int]) -> int:
        g = 0
        for i in (0, 2, 4):
            g = max(g, max(a[i] - b[i + 1] - 1, b[i] - a[i + 1] - 1, 0))
        return g

    out: list[tuple[str, str, str]] = []
    keys = sorted(boxes)
    for i, na in enumerate(keys):
        for nb in keys[i + 1:]:
            if any(overlap(ba, bb) for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb, "Interference"))
                continue
            if any(contact(ba, bb) for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb, "Contact"))
                continue
            if any(gap(ba, bb) <= max_gap
                   for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb, "Separation"))
    return out


def find_interferences(model: StpreModel) -> list[tuple[str, str]]:
    """Pairs of parts whose ``element`` index boxes overlap (AABB test).

    Used by the Gridding dialog [Reconstruct] button: interference check
    between meshed parts, like STpre's [List of Parts Interferences after
    Meshing].
    """
    el = model.elements()
    if el is None:
        return []
    import xml.etree.ElementTree as ET  # noqa: F401
    boxes: dict[str, list[list[int]]] = {}
    for parts in el.findall("parts"):
        name = parts.attrib.get("name", "")
        if name:
            b = model.part_boxes(name)
            if b:
                boxes[name] = b

    def overlap(a: list[int], b: list[int]) -> bool:
        return all(a[i] <= b[i + 1] and b[i] <= a[i + 1] for i in (0, 2, 4))

    out: list[tuple[str, str]] = []
    keys = sorted(boxes)
    for i, na in enumerate(keys):
        for nb in keys[i + 1:]:
            if any(overlap(ba, bb) for ba in boxes[na] for bb in boxes[nb]):
                out.append((na, nb))
    return out


def resolve_interferences(model: StpreModel) -> int:
    """Trim overlapping cells from lower-priority parts (tree order wins).

    Cell-level resolution: for every interfering pair, the later part's
    boxes are clipped against the earlier part's boxes axis by axis.
    Returns the number of part entries changed.
    """
    import xml.etree.ElementTree as ET

    el = model.elements()
    if el is None:
        return 0
    order = [p.name for p in model.parts()]
    prio = {n: i for i, n in enumerate(order)}
    entries: list[tuple[str, ET.Element, list[list[int]]]] = []
    for parts in el.findall("parts"):
        name = parts.attrib.get("name", "")
        body = parts.find("body")
        if body is None:
            continue
        boxes = [[int(x) for x in lst.text.split(",")]
                 for lst in body.findall("list") if lst.text]
        # unregistered parts keep element-section order after real parts
        prio.setdefault(name, len(order) + len(entries))
        entries.append((name, body, boxes))
    changed = 0

    def clip(box: list[int], other: list[int]) -> list[list[int]]:
        """Subtract ``other`` from ``box`` -> up to 6 residual boxes.

        Exact axis-aligned subtraction: the slabs protruding outside
        ``other`` along each axis, with the overlap core dropped.
        """
        if not all(box[i] <= other[i + 1] and other[i] <= box[i + 1]
                   for i in (0, 2, 4)):
            return [box]
        x0, x1 = box[0], box[1]
        y0, y1 = box[2], box[3]
        z0, z1 = box[4], box[5]
        ox0, ox1 = other[0], other[1]
        oy0, oy1 = other[2], other[3]
        oz0, oz1 = other[4], other[5]
        res: list[list[int]] = []
        # x slabs outside other
        if x0 < ox0:
            res.append([x0, ox0 - 1, y0, y1, z0, z1])
        if x1 > ox1:
            res.append([ox1 + 1, x1, y0, y1, z0, z1])
        xa, xb = max(x0, ox0), min(x1, ox1)
        # y slabs outside other (inside x overlap)
        if y0 < oy0:
            res.append([xa, xb, y0, oy0 - 1, z0, z1])
        if y1 > oy1:
            res.append([xa, xb, oy1 + 1, y1, z0, z1])
        ya, yb = max(y0, oy0), min(y1, oy1)
        # z slabs outside other (inside x and y overlap)
        if z0 < oz0:
            res.append([xa, xb, ya, yb, z0, oz0 - 1])
        if z1 > oz1:
            res.append([xa, xb, ya, yb, oz1 + 1, z1])
        return [b for b in res
                if b[0] <= b[1] and b[2] <= b[3] and b[4] <= b[5]]

    fixed: dict[str, list[list[int]]] = {}
    for name, _body, boxes in entries:
        cur = [list(b) for b in boxes]
        for other, _obody, oboxes in entries:
            if prio.get(other, 0) >= prio.get(name, 0):
                continue
            for ob in oboxes:
                nxt: list[list[int]] = []
                for b in cur:
                    nxt.extend(clip(b, ob))
                cur = nxt
        fixed[name] = [b for b in cur if b[0] <= b[1] and b[2] <= b[3]
                       and b[4] <= b[5]]
    for name, body, boxes in entries:
        if fixed.get(name) == boxes:
            continue
        for lst in list(body):
            body.remove(lst)
        body.attrib["num"] = str(len(fixed[name]))
        for n, box in enumerate(fixed[name], start=1):
            l = ET.SubElement(body, "list")
            l.attrib["no"] = str(n)
            l.text = " " + ",".join(str(v) for v in box) + " "
            l.tail = "\n      "
        changed += 1
    return changed


def find_flux_face_duplicates(model: StpreModel
                              ) -> list[tuple[str, list[str]]]:
    """Domain faces bound to more than one flux-type condition value.

    Mirrors the STpre "Check duplication of flux condition faces" option
    (``mesh_control/check_scheme``): a face carrying two different flux
    values is ambiguous for the solver.
    """
    from cabxml import _first
    by_face: dict[str, set[str]] = {}
    for c in model.conditions():
        region = _first(c, "region")
        val = _first(c, "value")
        if region is None or val is None:
            continue
        rname = (region.text or "").strip()
        vname = (val.text or "").strip()
        v = model.find_value(vname)
        if v is None or v.attrib.get("type") != "flux":
            continue
        by_face.setdefault(rname, set()).add(vname)
    return [(face, sorted(names))
            for face, names in by_face.items() if len(names) > 1]

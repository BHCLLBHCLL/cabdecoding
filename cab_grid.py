"""M3: gridding (Mesh -> Gridding).

Implements the STpre gridding semantics documented in the Pre manual:

* vertex detection: All / Representative / Axis plane / Min/Max /
  Not considered / Uniform;
* gridding method: rough grids only / rough + detailed mesh (standard length
  + geometric ratio, internal/external) / by number of elements;
* threshold length acts as the lower limit of element width.

The generated axes are written back to ``<mesh_control>`` (RootBlock
parameters) and ``<mesh_block>`` (x/y/z coordinate tables), the same XML
structure STpre produces.  One documented v1 limitation: "Representative"
and "Axis plane" are approximated with the All/MinMax vertex sets; exact
feature-face recognition is deferred until golden comparison with STpre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np

import stpre_rules


Vec3 = Union[float, tuple[float, float, float]]


def _as3(v: Vec3, default: float = 1.0) -> tuple[float, float, float]:
    if isinstance(v, (int, float)):
        return (float(v), float(v), float(v))
    return tuple(float(x) for x in v[:3])


@dataclass
class GridSpec:
    """Gridding parameters (coordinates in ``unit``, e.g. mm)."""

    unit: str = "mm"
    domain_min: tuple[float, float, float] = (-100.0, -100.0, -100.0)
    domain_max: tuple[float, float, float] = (150.0, 300.0, 315.0)
    vertex_detection: str = "minmax"
    # all | representative | axis_plane | minmax | not_considered | uniform
    method: str = "rough_and_detail"
    # rough_only | rough_and_detail | num_elements
    standard_length: Vec3 = 2.0
    threshold_length: Vec3 = 0.1
    geometric_ratio: Vec3 = 1.2          # internal ratio
    geometric_ratio_external: Optional[Vec3] = None
    common: bool = True
    target_elements: Optional[int] = None
    target_per_axis: Optional[tuple[int, int, int]] = None
    discard_existing: bool = True

    def ratio_internal(self) -> tuple[float, float, float]:
        return _as3(self.geometric_ratio)

    def ratio_external(self) -> tuple[float, float, float]:
        if self.geometric_ratio_external is None:
            return _as3(self.geometric_ratio)
        return _as3(self.geometric_ratio_external)


_DETECTION_ENUM = {
    "all": 0, "representative": 1, "axis_plane": 2,
    "minmax": 3, "not_considered": 4, "uniform": 5,
}
_METHOD_ENUM = {
    "rough_only": 0, "rough_and_detail": 1, "num_elements": 2,
}


def detection_index(spec: GridSpec) -> int:
    return _DETECTION_ENUM.get(spec.vertex_detection, 3)


def method_index(spec: GridSpec) -> int:
    return _METHOD_ENUM.get(spec.method, 1)


def _clip_dedupe(vals: list[float], lo: float, hi: float) -> list[float]:
    out: list[float] = []
    for v in sorted(vals):
        if v < lo or v > hi:
            continue
        if not out or v - out[-1] > 1e-9:
            out.append(v)
    if not out or out[0] > lo + 1e-9:
        out.insert(0, lo)
    if out[-1] < hi - 1e-9:
        out.append(hi)
    return out


def rough_grids(part_points: dict[str, np.ndarray], spec: GridSpec,
                part_vertices: Optional[dict[str, np.ndarray]] = None
                ) -> dict[str, list[float]]:
    """Rough grid coordinates per axis from part vertices + domain bounds.

    ``part_points`` maps part name -> tessellation points in ``spec.unit``
    (used for min/max and as vertex fallback).  ``part_vertices`` maps part
    name -> real B-rep vertex coordinates when available (STpre "All" /
    "Representative" use the Parasolid vertices, not the display mesh).
    """
    dmin = np.asarray(spec.domain_min, dtype=float)
    dmax = np.asarray(spec.domain_max, dtype=float)
    vertices = part_vertices or {}
    thrs = _as3(spec.threshold_length)
    out: dict[str, list[float]] = {}
    for ax_i, ax in enumerate("xyz"):
        if spec.vertex_detection == "uniform":
            out[ax] = [dmin[ax_i], dmax[ax_i]]
            continue
        vals: list[float] = []
        if spec.vertex_detection in ("all", "representative",
                                     "axis_plane", "minmax",
                                     "not_considered"):
            # STpre probe: not_considered still grids with part min/max
            # planes (only vertex detection is skipped); identical to
            # minmax for convex parts (tr03: vd4 == vd3).
            for arr in part_points.values():
                if arr is None or len(arr) == 0:
                    continue
                col = arr[:, ax_i]
                vals.append(float(col.min()))
                vals.append(float(col.max()))
        if spec.vertex_detection in ("all", "representative"):
            sources = vertices or part_points
            for arr in sources.values():
                if arr is None or len(arr) == 0:
                    continue
                vals.extend(float(v) for v in arr[:, ax_i])
        out[ax] = _clip_dedupe(
            vals, dmin[ax_i], dmax[ax_i], tol=max(thrs[ax_i], 1e-9))
    return out


def _target_counts(spec: GridSpec) -> tuple[int, int, int]:
    if spec.target_per_axis is not None:
        return tuple(max(2, int(v)) for v in spec.target_per_axis)
    n = spec.target_elements or 1_000_000
    # STpreBase MeshBlock::SetElementNum disassembly (M16): per-axis counts
    # from domain lengths and target total; non-cube via length ratios.
    return tuple(max(2, int(v)) for v in stpre_rules.auto1_per_axis_counts(
        spec.domain_min, spec.domain_max, n))


def _refine_axis(rough: list[float], std: float, ratio: float,
                 threshold: float, internal: list[bool]) -> list[float]:
    """Divide every rough interval with a geometric series."""
    if std <= 0.0:
        std = 1.0
    if ratio <= 0.0:
        ratio = 1.0
    out = [rough[0]]
    for k, (a, b) in enumerate(zip(rough[:-1], rough[1:])):
        r = ratio if internal[k] else ratio
        length = b - a
        if length <= 1e-12:
            continue
        n = max(1, int(round(length / std)))
        if abs(r - 1.0) < 1e-9:
            xs = np.linspace(a, b, n + 1)
        else:
            first = length * (1.0 - r) / (1.0 - r ** n)
            xs = a + first * (1.0 - r ** np.arange(n + 1)) / (1.0 - r)
        for x in xs[1:]:
            x = float(x)
            if x - out[-1] >= threshold - 1e-12 or abs(x - b) < 1e-12:
                out.append(x)
    if abs(out[-1] - rough[-1]) > 1e-9:
        out.append(rough[-1])
    return out


def refine_grids(rough: dict[str, list[float]], spec: GridSpec,
                 part_bounds: Optional[tuple[np.ndarray, np.ndarray]] = None
                 ) -> dict[str, list[float]]:
    """Detailed mesh axes from rough grids + standard length/ratio."""
    if spec.method == "rough_only":
        return {ax: list(v) for ax, v in rough.items()}
    if spec.method == "num_elements":
        counts = _target_counts(spec)
        out: dict[str, list[float]] = {}
        dmin = np.asarray(spec.domain_min, float)
        dmax = np.asarray(spec.domain_max, float)
        qs = spec.ratio_external()
        lo = part_bounds[0] if part_bounds is not None else None
        hi = part_bounds[1] if part_bounds is not None else None
        for i, ax in enumerate("xyz"):
            if lo is not None and hi is not None:
                out[ax] = _auto1_axis(
                    dmin[i], dmax[i], float(lo[i]), float(hi[i]),
                    counts[i], qs[i])
            else:
                out[ax] = list(np.linspace(dmin[i], dmax[i], counts[i]))
        return out
    stds = _as3(spec.standard_length)
    thrs = _as3(spec.threshold_length)
    r_ex = spec.ratio_external()
    r_in = spec.ratio_internal()
    lo = part_bounds[0] if part_bounds is not None else None
    hi = part_bounds[1] if part_bounds is not None else None
    out = {}
    for i, ax in enumerate("xyz"):
        axis_pts = [rough[ax][0]]
        for a, b in zip(rough[ax][:-1], rough[ax][1:]):
            if lo is not None and hi is not None:
                mid = (a + b) * 0.5
                internal = lo[i] <= mid <= hi[i]
            else:
                internal = True
            if internal:
                axis_pts.extend(_inner_symmetric(
                    a, b, stds[i], r_in[i], thrs[i]))
            else:
                if b <= lo[i] + 1e-9:
                    part_side = b          # interval left of the part
                elif a >= hi[i] - 1e-9:
                    part_side = a          # interval right of the part
                else:
                    part_side = b
                axis_pts.extend(_stpre_external(
                    a, b, part_side, stds[i], r_ex[i], thrs[i]))
        if axis_pts[-1] != rough[ax][-1]:
            axis_pts.append(rough[ax][-1])
        out[ax] = _clip_dedupe(axis_pts, rough[ax][0], rough[ax][-1])
    return out


def _equal_split(a: float, b: float, std: float,
                 threshold: float) -> list[float]:
    """STpre internal-region division: equal spacing by standard length."""
    length = b - a
    if length <= 1e-12:
        return []
    n = max(1, stpre_rules._trunc_round(length / std)) if std > 0 else 1
    if threshold > 0 and length / n < threshold:
        n = max(1, int(length / threshold))
    return list(np.linspace(a, b, n + 1)[1:-1])


def _symmetric_sum(n: int, g0: float, q: float) -> float:
    """Sum of the symmetric two-sided geometric sequence (ratio_in>1)."""
    if n <= 0:
        return 0.0
    if n % 2 == 1:
        k = (n + 1) // 2          # 2*(1+..+q^(k-2)) + q^(k-1)
        if k == 1:
            return g0
        return g0 * (2.0 * (q ** (k - 1) - 1.0) / (q - 1.0) + q ** (k - 1))
    k = n // 2
    return g0 * 2.0 * (q ** k - 1.0) / (q - 1.0)


def _inner_symmetric(a: float, b: float, std: float, ratio: float,
                     threshold: float) -> list[float]:
    """STpre internal region with geometric_ratio > 1: symmetric two-sided
    series from both part faces (probe ratio_in=1.2: 1,1.285,1.653,2.124,
    1.653,1.285,1 over 10 mm).  n is the largest count whose nominal-ratio
    sum fits the length; the actual q is then solved to fill it exactly.
    """
    length = b - a
    if length <= 1e-12 or ratio <= 1.0 + 1e-9:
        return _equal_split(a, b, std, threshold)
    g0 = max(std, threshold)
    if g0 <= 0.0 or g0 >= length:
        return _equal_split(a, b, std, threshold)
    n = 1
    while _symmetric_sum(n + 1, g0, ratio) <= length + 1e-12:
        n += 1
    if n < 3:
        return _equal_split(a, b, std, threshold)
    lo_q, hi_q = ratio, max(ratio * 2.0, 2.0)
    for _ in range(80):
        mid = 0.5 * (lo_q + hi_q)
        if _symmetric_sum(n, g0, mid) < length:
            lo_q = mid
        else:
            hi_q = mid
    qa = 0.5 * (lo_q + hi_q)
    if abs(_symmetric_sum(n, g0, qa) - length) > 1e-6 * max(1.0, length):
        return _equal_split(a, b, std, threshold)
    if n % 2 == 1:
        k = (n + 1) // 2
        seq = [g0 * qa ** i for i in range(k - 1)]
        seq += [g0 * qa ** (k - 1)]
        seq += [g0 * qa ** i for i in range(k - 2, -1, -1)]
    else:
        k = n // 2
        seq = [g0 * qa ** i for i in range(k)]
        seq += [g0 * qa ** i for i in range(k - 1, -1, -1)]
    pts = [a]
    x = a
    for d in seq[:-1]:
        x += d
        pts.append(x)
    return pts[1:]


def _auto1_axis(dmin: float, dmax: float, part_lo: float, part_hi: float,
                n: int, q: float) -> list[float]:
    """STpre auto1 axis layout (M17 closed form): P + L/R split by
    argmin max(g0L,g0R); inner equal spacing s=p/P; outer geometric with
    exact-sum first spacings."""
    if n < 3 or part_hi <= part_lo:
        return list(np.linspace(dmin, dmax, n))
    part_lo = max(part_lo, dmin)
    part_hi = min(part_hi, dmax)
    if part_hi <= part_lo:
        return list(np.linspace(dmin, dmax, n))
    try:
        lay = stpre_rules.auto1_axis_layout(
            part_lo, part_hi, dmin, dmax, n, q)
    except (ValueError, ZeroDivisionError):
        return list(np.linspace(dmin, dmax, n))
    pts = [dmin]
    if lay["L"] and lay["g0L"]:
        g0 = lay["g0L"]
        if abs(q - 1.0) < 1e-9:
            step = (part_lo - dmin) / lay["L"]
            for k in range(1, lay["L"]):
                pts.append(part_lo - k * step)
        else:
            for k in range(1, lay["L"]):
                pts.append(part_lo - g0 * (q ** k - 1.0) / (q - 1.0))
    pts.append(part_lo)
    inner = np.linspace(part_lo, part_hi, lay["P"] + 1)
    pts.extend(float(v) for v in inner[1:-1])
    pts.append(part_hi)
    if lay["R"] and lay["g0R"]:
        g0 = lay["g0R"]
        if abs(q - 1.0) < 1e-9:
            step = (dmax - part_hi) / lay["R"]
            for k in range(1, lay["R"]):
                pts.append(part_hi + k * step)
        else:
            for k in range(1, lay["R"]):
                pts.append(part_hi + g0 * (q ** k - 1.0) / (q - 1.0))
    pts.append(dmax)
    return _clip_dedupe(pts, dmin, dmax)


def _stpre_external(a: float, b: float, part_side: float, std: float,
                    q: float, threshold: float) -> list[float]:
    """STpre external-region division: geometric series dense at the part.

    Golden data (ex4_e x-axis, domain -100..0): the first gap at the part
    side equals the standard length (1.0) and the *actual* ratio is solved
    so the geometric series exactly fills the interval (q ~ 1.19416, not
    the nominal 1.2): 1.0, 1.1941, 1.426, ..., 17.095.
    """
    length = b - a
    if length <= 1e-12:
        return []
    if std <= 0 or q <= 1.0:
        return _equal_split(a, b, std, threshold)
    g0 = max(std, threshold)
    n = max(1, int(np.ceil(
        np.log(length * (q - 1) / g0 + 1.0) / np.log(q))))
    if n <= 1:
        return []
    # solve actual ratio qa in (1, q] such that g0*(qa^n-1)/(qa-1) == length
    lo_q, hi_q = 1.0 + 1e-9, max(q, 1.0 + 1e-9)
    qa = 1.0
    for _ in range(60):
        mid = 0.5 * (lo_q + hi_q)
        s = g0 * (mid ** n - 1.0) / (mid - 1.0)
        if s < length:
            lo_q = mid
        else:
            hi_q = mid
    qa = 0.5 * (lo_q + hi_q)
    if abs(qa - 1.0) < 1e-9:
        return _equal_split(a, b, std, threshold)
    pts = [part_side]
    for k in range(1, n):
        cum = g0 * (qa ** k - 1) / (qa - 1)
        x = part_side - cum if part_side == b else part_side + cum
        if (part_side == b and x <= a) or (part_side == a and x >= b):
            break
        if all(abs(x - p) >= max(threshold, 1e-9) for p in pts):
            pts.append(x)
    return pts


def _refine_axis_ratios(rough: list[float], std: float,
                        ratios: list[float], threshold: float) -> list[float]:
    """Geometric-series division with a per-interval ratio list."""
    out = [rough[0]]
    for k, (a, b) in enumerate(zip(rough[:-1], rough[1:])):
        r = ratios[k] if k < len(ratios) else 1.0
        if r <= 0.0:
            r = 1.0
        length = b - a
        if length <= 1e-12:
            continue
        n = max(1, int(round(length / std)))
        if abs(r - 1.0) < 1e-9:
            xs = np.linspace(a, b, n + 1)
        else:
            first = length * (1.0 - r) / (1.0 - r ** n)
            xs = a + first * (1.0 - r ** np.arange(n + 1)) / (1.0 - r)
        for x in xs[1:]:
            x = float(x)
            if x - out[-1] >= threshold - 1e-12 or abs(x - b) < 1e-12:
                out.append(x)
    if abs(out[-1] - rough[-1]) > 1e-9:
        out.append(rough[-1])
    return out


def build_axes(part_points: dict[str, np.ndarray], spec: GridSpec,
               part_vertices: Optional[dict[str, np.ndarray]] = None,
               part_bounds: Optional[tuple[np.ndarray, np.ndarray]] = None
               ) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Return ``(rough, detailed)`` axes; detailed is the final mesh.

    ``part_bounds`` ``(lo, hi)`` in the same unit as ``spec`` enables
    STpre external geometric-ratio refinement outside the parts.
    """
    rough = rough_grids(part_points, spec, part_vertices=part_vertices)
    if spec.method == "rough_only":
        return rough, {ax: list(v) for ax, v in rough.items()}
    detailed = refine_grids(rough, spec, part_bounds=part_bounds)
    return rough, detailed


def divide_interval(axis_vals: list[float], a: float, b: float, n: int,
                    ratio: float = 1.0, mode: str = "forward",
                    threshold: float = 0.0,
                    retain: Optional[list[float]] = None
                    ) -> list[float]:
    """Re-divide the ``(a, b)`` interval of an axis into ``n`` elements.

    ``mode`` selects the geometric-ratio direction (STpre Detail meshing):
    ``forward`` (-->), ``symmetric`` (--><--), ``backward`` (<--).
    ``retain`` lists rough-grid coordinates inside the range that must be
    kept (sub-intervals are divided proportionally).  Lines closer than
    ``threshold`` to a neighbour are dropped.
    """
    if n < 1 or b - a <= 1e-12:
        return sorted(axis_vals)
    keep = sorted(v for v in (retain or []) if a + 1e-9 < v < b - 1e-9)
    bounds = [a] + keep + [b]
    counts = [max(1, int(round(n * (bounds[i + 1] - bounds[i]) / (b - a))))
              for i in range(len(bounds) - 1)]
    # fix rounding so the total is exactly n
    while sum(counts) > n and max(counts) > 1:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < n:
        counts[counts.index(min(counts))] += 1
    ratio = ratio if ratio > 0.0 else 1.0
    new_pts: list[float] = []
    for i, cnt in enumerate(counts):
        lo, hi = bounds[i], bounds[i + 1]
        length = hi - lo
        if abs(ratio - 1.0) < 1e-9:
            xs = np.linspace(lo, hi, cnt + 1)[1:-1]
        elif mode == "symmetric":
            half = cnt // 2
            first = (length / 2.0) * (1.0 - ratio) / (1.0 - ratio ** half) \
                if half > 0 else 0.0
            left = lo + first * (1.0 - ratio ** np.arange(1, half + 1)) \
                / (1.0 - ratio)
            right = hi - (left - lo)[::-1]
            xs = np.concatenate([left, right]) if cnt % 2 == 0 else \
                np.concatenate([left, [(lo + hi) / 2.0], right])
        elif mode == "backward":
            first = length * (1.0 - ratio) / (1.0 - ratio ** cnt)
            xs = hi - first * (1.0 - ratio ** np.arange(1, cnt)) \
                / (1.0 - ratio)
        else:  # forward
            first = length * (1.0 - ratio) / (1.0 - ratio ** cnt)
            xs = lo + first * (1.0 - ratio ** np.arange(1, cnt)) \
                / (1.0 - ratio)
        new_pts.extend(float(x) for x in xs)
    out: list[float] = []
    for v in sorted(axis_vals):
        if a + 1e-9 < v < b - 1e-9 and v not in keep:
            continue  # old interior lines of the range are replaced
        out.append(v)
    for x in new_pts:
        if all(abs(x - v) >= max(threshold, 1e-9) for v in out):
            out.append(x)
    return sorted(out)


def delete_grid_lines(entries: list[tuple[float, str]], target: str,
                      part_minmax: Optional[list[float]] = None
                      ) -> list[tuple[float, str]]:
    """STpre Deletion tab semantics on one axis' ``(value, mark)`` list.

    ``target``: ``all_but_rough`` keeps B/S/F lines; ``all`` keeps block
    boundaries and lines through part min/max coordinates (``part_minmax``);
    fixed marks are cancelled (F -> N) before filtering when requested by
    the caller.
    """
    if len(entries) <= 2:
        return entries
    keep: list[tuple[float, str]] = []
    refs = set()
    for v in (part_minmax or []):
        refs.add(round(float(v), 9))
    for i, (val, mark) in enumerate(entries):
        boundary = i == 0 or i == len(entries) - 1 or mark == "B"
        if target == "all_but_rough":
            if boundary or mark in ("S", "F"):
                keep.append((val, mark))
        elif target == "all":
            if boundary or round(val, 9) in refs:
                keep.append((val, mark))
        else:
            keep.append((val, mark))
    return keep

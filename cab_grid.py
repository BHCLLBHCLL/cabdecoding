"""M3: gridding (Mesh -> Gridding).

Implements the STpre gridding semantics documented in the Pre manual:

* vertex detection: All / Representative / Axis plane / Min/Max /
  Not considered / Uniform;
* gridding method: rough grids only / rough + detailed mesh (standard length
  + geometric ratio, internal/external) / by number of elements;
* threshold length acts as the lower limit of element width;
* domain coordinate type (cartesian / cylindrical / axial) is stored on the
  model (``analysis_region@type`` + ``mesh_control/domain_coordinate``) but
  **native axis generation remains cartesian AABB** — cylindrical/axial are
  type flags for downstream / STpre API, not a polar mesher yet.

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
    # Stored on the model; native build_axes still uses cartesian AABB.
    domain_coordinate: str = "cartesian"  # cartesian | cylindrical | axial
    vertex_detection: str = "representative"
    # all | representative | axis_plane | minmax | not_considered | uniform
    method: str = "rough_and_detail"
    # rough_only | rough_and_detail | num_elements
    standard_length: Vec3 = 0.5
    threshold_length: Vec3 = 0.1
    geometric_ratio: Vec3 = 1.0          # internal ratio
    # None → ratio_external() falls back to geometric_ratio (compat);
    # Mesh:Set division UI sets external = 1.1 explicitly.
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


def _clip_dedupe(vals: list[float], lo: float, hi: float,
                 tol: float = 1e-9) -> list[float]:
    out: list[float] = []
    for v in sorted(vals):
        if v < lo - tol or v > hi + tol:
            continue
        vv = min(max(v, lo), hi)
        # Snap to nanometre precision to absorb the ~1e-13 mm floating point
        # noise a part transform (metres -> mm) leaves on vertex coordinates;
        # without this, a nominal 2.5 mm segment becomes 2.49999999999998 and
        # _trunc_round flips 3 -> 2 (off-by-one grid line vs STpre).
        vv = round(vv, 9)
        if not out or vv - out[-1] > tol:
            out.append(vv)
    if not out or out[0] > lo + 1e-9:
        out.insert(0, lo)
    if out[-1] < hi - 1e-9:
        out.append(hi)
    return out


def _effective_detection(name: str, spec: GridSpec,
                          part_detections=None) -> str:
    """Per-part vertex-detection override (STpre part select_vertex).

    STpre reads each part's own select_vertex mode in the grid collector
    (MeshCoarseDivide part loop, vtable+0x7c8 switch) - the global mode is
    only the default.  "default"/None falls back to the global mode.
    """
    d = (part_detections or {}).get(name)
    if not d or d == "default":
        return spec.vertex_detection
    return d


def rough_grids(part_points: dict[str, np.ndarray], spec: GridSpec,
                part_vertices: Optional[dict[str, np.ndarray]] = None,
                part_detections: Optional[dict[str, str]] = None
                ) -> dict[str, list[float]]:
    """Rough grid coordinates per axis from part vertices + domain bounds.

    ``part_points`` maps part name -> tessellation points in ``spec.unit``
    (used for min/max and as vertex fallback).  ``part_vertices`` maps part
    name -> real B-rep vertex coordinates when available (STpre "All" /
    "Representative" use the Parasolid vertices, not the display mesh).
    ``part_detections`` carries per-part vertex-detection overrides
    (STpre part select_vertex); a part set to "uniform" contributes
    nothing at all.
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
        for name, arr in part_points.items():
            if arr is None or len(arr) == 0:
                continue
            mode = _effective_detection(name, spec, part_detections)
            if mode == "uniform":
                continue          # STpre: uniform parts are fully ignored
            col = arr[:, ax_i]
            # STpre probe: not_considered still grids with part min/max
            # planes (only vertex detection is skipped); identical to
            # minmax for convex parts (tr03: vd4 == vd3).  NOTE: vd_0
            # "all" in STpre projects ONLY display-mesh nodes that lie
            # INSIDE the computational-domain box (3D test, all axes;
            # diag_all_diff76-79 2026-08-16: clip -> x 5/5, z 84/84
            # exact, only y=47.5 left, supplied by the part AABB
            # extreme).  Part AABB min/max per axis are always added
            # even when their node is outside the box (tr03 impeller
            # corner (-22.5, 47.5, 0) supplies gold y=47.5).  Merge of
            # close projections happens in _clip_dedupe with tol =
            # threshold (STpre merges S-lines within threshold, keep
            # first).  Our display mesh uses the decoded STpre recipe
            # (ps_facet2_nodes.stpre_recipe) and reproduces the STpre
            # facet planes exactly (tr03: 2206 tris).
            vals.append(float(col.min()))
            vals.append(float(col.max()))
            if mode == "all":
                inside = np.all(
                    (arr >= dmin - 1e-6) & (arr <= dmax + 1e-6), axis=1)
                vals.extend(float(v) for v in arr[inside, ax_i])
            elif mode == "representative":
                src = (vertices or part_points).get(name)
                if src is not None and len(src):
                    # STpre rep projects ONLY vertices that lie INSIDE
                    # the domain box (3D test, diag_rep_sector 2026-08-16:
                    # tr03 z=-8.103 line is absent because its only
                    # vertices sit at y=-29.05, outside the domain;
                    # every "dropped" value traces to out-of-box
                    # vertices; in-domain vertices all keep).  Same clip
                    # rule as the "all" display-mesh nodes.
                    inside_v = np.all(
                        (src >= dmin - 1e-6) & (src <= dmax + 1e-6),
                        axis=1)
                    vals.extend(float(v) for v in src[inside_v, ax_i])
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
        if ax not in rough:
            continue
        axis_pts = list(rough[ax])   # keep every rough grid line
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
        out[ax] = _clip_dedupe(
            axis_pts, rough[ax][0], rough[ax][-1], tol=max(thrs[i], 1e-9))
    return out


def _equal_split(a: float, b: float, std: float,
                 threshold: float) -> list[float]:
    """STpre internal-region division: equal spacing by standard length.

    Interval count ``n = floor(L/std + 2/3)`` (diag_all_diff81/82
    2026-08-16, tr03 all-mode gold: q=1.303 -> 1, 1.338 -> 2, 2.235 -> 2,
    2.349 -> 3, 13.333 (=40/3) -> 14; carry when frac(L/std) > 1/3).
    Also fits the earlier box probes (2.5 -> 3).

    The 2/3 addend is the *float32-rounded* value (C++ ``2.0f/3.0f``
    promoted to double = 0.66666668653...): tr03 x interval L=40/3
    (13.333333333333305 double) must give n=14 in STpre; with an exact
    double 2/3 the sum is 13.999999999999972 -> 13.  The float32 constant
    pushes the decision boundary to L/std > 13.333333313..., matching
    every gold probe (diag_all_diff85 2026-08-16)."""
    import math
    length = b - a
    if length <= 1e-12:
        return []
    n = max(1, int(length / std + 0.6666666865348816)) if std > 0 else 1
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
               part_bounds: Optional[tuple[np.ndarray, np.ndarray]] = None,
               part_detections: Optional[dict[str, str]] = None
               ) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Return ``(rough, detailed)`` axes; detailed is the final mesh.

    ``part_bounds`` ``(lo, hi)`` in the same unit as ``spec`` enables
    STpre external geometric-ratio refinement outside the parts.
    ``part_detections`` applies per-part vertex-detection overrides
    (STpre part select_vertex).
    """
    rough = rough_grids(part_points, spec, part_vertices=part_vertices,
                        part_detections=part_detections)
    if spec.method == "rough_only":
        return rough, {ax: list(v) for ax, v in rough.items()}
    coord = getattr(spec, "domain_coordinate", "cartesian")
    if coord == "cylindrical":
        return rough, _build_cylindrical_axes(
            rough, spec, part_points=part_points, part_bounds=part_bounds,
            part_detections=part_detections)
    if coord == "axial":
        return rough, _build_axial_axes(
            rough, spec, part_points=part_points, part_bounds=part_bounds)
    if spec.vertex_detection == "uniform":
        # STpre "uniform" ignores the part entirely: the whole domain is
        # divided by the standard length (no internal/external split, no
        # geometric ratio).  Pass no part_bounds so refine_grids treats
        # every interval as internal.
        detailed = refine_grids(rough, spec, part_bounds=None)
    else:
        detailed = refine_grids(rough, spec, part_bounds=part_bounds)
    return rough, detailed


def _radial_part_extent(part_points) -> tuple[float, float]:
    """Radial [r_lo, r_hi] of the parts from r = sqrt(x^2+y^2).

    STpre COM probe (SetCylindricalDomain + ExecuteGrid, 2026-08-15):
    a part whose XY bounding box contains the axis contributes r_lo = 0
    (its minmax radial range is [0, r_max]); otherwise r_lo is the
    smallest vertex radius.  r_hi is always the largest vertex radius.
    """
    r_proj: list[float] = []
    contains_axis = False
    for arr in (part_points or {}).values():
        arr = np.asarray(arr, dtype=np.float64)
        if len(arr) == 0:
            continue
        r = np.hypot(arr[:, 0], arr[:, 1])
        r_proj.extend(float(v) for v in r)
        if (float(arr[:, 0].min()) <= 0.0 <= float(arr[:, 0].max())
                and float(arr[:, 1].min()) <= 0.0
                <= float(arr[:, 1].max())):
            contains_axis = True
    if not r_proj:
        return 0.0, 0.0
    r_lo = 0.0 if contains_axis else min(r_proj)
    return r_lo, max(r_proj)


def _build_cylindrical_axes(rough: dict[str, list[float]], spec: GridSpec,
                            *, part_points=None,
                            part_bounds=None,
                            part_detections=None) -> dict[str, list[float]]:
    """Cylindrical layout: x=R, y=theta(deg), z=Z.

    STpre stores R / theta / Z in the mesh_block tables (r unit=mm,
    t unit=radian, z unit=mm, system=1; COM probe 2026-08-15).
    R and Z run the real internal/external refine path with the radial
    part extent (sqrt(x^2+y^2) of the tessellation) instead of the
    cartesian x bounds, so a part centred on the axis grids its inner
    region [0, r_out] and its outer region [r_out, r_max] correctly.
    Theta is uniform in degrees with n = span_deg / standard_length
    (probe: 360/5 -> 72 cells, 180/5 -> 36, 360/2.5 -> 144).
    """
    std = _as3(spec.standard_length)[0] or 1.0
    dmin = np.asarray(spec.domain_min, float)
    dmax = np.asarray(spec.domain_max, float)
    rmin = float(dmin[0])
    rmax = float(dmax[0])
    tmin = float(dmin[1])
    tmax = float(dmax[1])
    thrs = _as3(spec.threshold_length)
    # -- radial part extent from the tessellation (r = sqrt(x^2+y^2)) ------
    active = {
        name: arr for name, arr in (part_points or {}).items()
        if _effective_detection(name, spec, part_detections) != "uniform"}
    r_proj: list[float] = []
    z_vals: list[float] = []
    for arr in active.values():
        arr = np.asarray(arr, dtype=np.float64)
        if len(arr) == 0:
            continue
        r = np.hypot(arr[:, 0], arr[:, 1])
        r_proj.extend(float(v) for v in r)
        z_vals.append(float(arr[:, 2].min()))
        z_vals.append(float(arr[:, 2].max()))
    r_lo, r_hi = _radial_part_extent(active)
    z_lo = min(z_vals) if z_vals else float(dmin[2])
    z_hi = max(z_vals) if z_vals else float(dmax[2])
    # -- R axis: rough radial lines (part min/max + vertex projections) ----
    r_rough: list[float] = [rmin, rmax, r_lo, r_hi]
    if spec.vertex_detection in ("all", "representative"):
        r_rough.extend(r_proj)
    r_rough = _clip_dedupe(r_rough, rmin, rmax, tol=max(thrs[0], 1e-9))
    r_bounds = (np.array([r_lo, 0.0, z_lo]), np.array([r_hi, 0.0, z_hi]))
    r_axis = refine_grids({"x": r_rough}, spec, part_bounds=r_bounds)["x"]
    # -- Z axis: cartesian z bounds are already axial ----------------------
    z_bounds = (np.array([r_lo, 0.0, z_lo]), np.array([r_hi, 0.0, z_hi]))
    z_axis = refine_grids({"z": list(rough["z"])}, spec,
                          part_bounds=z_bounds)["z"]
    # -- theta: uniform span/std cells (STpre probe) ------------------------
    span = max(tmax - tmin, 0.0)
    n_theta = max(1, stpre_rules._trunc_round(span / max(std, 1e-9)))
    theta = list(np.linspace(tmin, tmax, n_theta + 1))
    return {"x": r_axis, "y": theta, "z": z_axis}


def _build_axial_axes(rough: dict[str, list[float]], spec: GridSpec,
                      *, part_points=None,
                      part_bounds=None) -> dict[str, list[float]]:
    """Axial-symmetry layout (STpre COM probe 2026-08-15).

    The domain stays cartesian (x = R, z = Z); the Y axis collapses to
    exactly two lines with y_max = y_min + min(x_len, z_len) and the
    analysis flag is analysis_set/axissymmetry = 1.
    """
    dmin = np.asarray(spec.domain_min, float)
    dmax = np.asarray(spec.domain_max, float)
    xlen = float(dmax[0] - dmin[0])
    zlen = float(dmax[2] - dmin[2])
    ymin = float(dmin[1])
    ymax = ymin + min(xlen, zlen)
    x_axis = refine_grids({"x": list(rough["x"])}, spec,
                          part_bounds=part_bounds)["x"]
    z_axis = refine_grids({"z": list(rough["z"])}, spec,
                          part_bounds=part_bounds)["z"]
    return {"x": x_axis, "y": [ymin, ymax], "z": z_axis}


def _block_internal_points(lo: float, hi: float, std: float, ratio: float,
                           limit: float) -> list[float]:
    """Interior grid lines of one block interval (STpre child refinement)."""
    if hi <= lo:
        return []
    if ratio and abs(ratio - 1.0) > 1e-9:
        try:
            pts = _inner_symmetric(lo, hi, std, ratio, limit)
        except Exception:
            pts = []
        return [float(v) for v in pts if lo < v < hi]
    n = max(1, stpre_rules._trunc_round((hi - lo) / std)) if std > 0 else 1
    return list(np.linspace(lo, hi, n + 1)[1:-1])


def _parse_block_vec(text: str, default: float) -> tuple[float, float, float]:
    if isinstance(text, (tuple, list)):
        vals = [float(x) for x in text[:3]]
        while len(vals) < 3:
            vals.append(default)
        return (vals[0], vals[1], vals[2])
    try:
        vals = [float(x) for x in (text or "").split(",")[:3]]
        while len(vals) < 3:
            vals.append(default)
        return (vals[0], vals[1], vals[2])
    except ValueError:
        return (default, default, default)


def _mark_priority(mark: str) -> int:
    return {"B": 4, "CS": 3, "C": 3, "F": 2, "S": 2, "N": 1}.get(
        (mark or "N").upper(), 0)


def _merge_block_axis(entries: list[tuple[float, str]], block: dict,
                      ax_i: int, spec: GridSpec,
                      is_root: bool) -> list[tuple[float, str]]:
    """Overlay one block's refinement onto an axis entry list."""
    lo_mm = block.get("min")
    hi_mm = block.get("max")
    if not lo_mm or not hi_mm:
        return entries
    lo, hi = float(lo_mm[ax_i]), float(hi_mm[ax_i])
    divide = _parse_block_vec(
        block.get("divide", ""), _as3(spec.standard_length)[ax_i])
    ratio = _parse_block_vec(
        block.get("ratio", ""), spec.ratio_internal()[ax_i])
    limit = _parse_block_vec(
        block.get("limit", ""), _as3(spec.threshold_length)[ax_i])
    interior = _block_internal_points(
        lo, hi, divide[ax_i], ratio[ax_i], limit[ax_i])
    if is_root:
        # root keeps its own rough/detailed lines; only children overlay
        keep = list(entries)
    else:
        keep = [(v, m) for v, m in entries if not (lo < v < hi)]
        keep.append((lo, "CS"))
        keep.append((hi, "C"))
        keep.extend((float(v), "N") for v in interior)
    merged: dict[float, str] = {}
    for v, m in keep:
        key = round(float(v), 9)
        if key not in merged or _mark_priority(m) > _mark_priority(
                merged[key]):
            merged[key] = (m or "N").upper()
    return sorted(merged.items(), key=lambda kv: kv[0])


def build_axes_multiblock(part_points: dict[str, np.ndarray],
                          spec: GridSpec, blocks: list[dict], *,
                          part_vertices: Optional[dict] = None,
                          part_bounds=None, child_only: bool = False
                          ) -> tuple[dict[str, list[float]],
                                     dict[str, list[float]],
                                     dict[str, list[tuple[float, str]]]]:
    """Root + nested child-block gridding (STpre multiblock layout).

    Returns ``(rough, detailed, entries)``; ``entries`` carries per-axis
    ``(coord, mark)`` pairs where child boundaries are ``CS``/``C``.
    """
    rough, detailed = build_axes(
        part_points, spec, part_vertices=part_vertices,
        part_bounds=part_bounds)
    root = blocks[0] if blocks else None
    if root is None or not root.get("children"):
        plain = {}
        for i, ax in enumerate("xyz"):
            vals = detailed[ax]
            plain[ax] = [
                (v, "B" if i in (0, len(vals) - 1) else "N")
                for i, v in enumerate(vals)]
        return rough, detailed, plain
    dmin = np.asarray(spec.domain_min, float)
    dmax = np.asarray(spec.domain_max, float)
    entries_out: dict[str, list[tuple[float, str]]] = {}
    for ax_i, ax in enumerate("xyz"):
        if child_only:
            entries: list[tuple[float, str]] = [
                (float(dmin[ax_i]), "B"), (float(dmax[ax_i]), "B")]
        else:
            entries = [
                (v, "B" if idx in (0, len(detailed[ax]) - 1) else "N")
                for idx, v in enumerate(detailed[ax])]

        def apply_block(blk: dict, is_root: bool) -> None:
            nonlocal entries
            if not is_root or not child_only:
                entries = _merge_block_axis(
                    entries, blk, ax_i, spec, is_root=is_root)
            for child in blk.get("children", []):
                apply_block(child, is_root=False)

        apply_block(root, is_root=True)
        if not entries:
            entries = [(float(dmin[ax_i]), "B"), (float(dmax[ax_i]), "B")]
        entries_out[ax] = entries
    detailed_mb = {ax: [v for v, _m in entries_out[ax]] for ax in "xyz"}
    return rough, detailed_mb, entries_out


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


def parse_fine_divide(text: str) -> Optional[tuple[int, int, int]]:
    """Parse ``<mesh_fine_divide>x,y,z</...>``; 0/1 means no extra split."""
    if not (text or "").strip():
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        return None
    try:
        return (int(float(parts[0])), int(float(parts[1])),
                int(float(parts[2])))
    except ValueError:
        return None


def part_aabb_mm(part, tess=None) -> Optional[tuple[tuple, tuple]]:
    """Part AABB in millimetres from tessellation (m) or XML base/size."""
    pts = None
    if tess is not None:
        raw = getattr(tess, "points", None)
        if raw is not None:
            arr = np.asarray(raw, dtype=float)
            if arr.size:
                pts = arr
    if pts is not None:
        xf = getattr(part, "transform", "") or ""
        try:
            import cab_vtk
            pts = cab_vtk._apply_transform(pts, xf) * 1000.0
        except Exception:
            pts = np.asarray(pts, dtype=float) * 1000.0
        lo = tuple(float(v) for v in pts.min(axis=0)[:3])
        hi = tuple(float(v) for v in pts.max(axis=0)[:3])
        return lo, hi
    base = (getattr(part, "base", "") or "").strip()
    size = (getattr(part, "size", "") or "").strip()
    if not base or not size:
        return None
    try:
        b = [float(v) for v in base.split(",")[:3]]
        s = [float(v) for v in size.split(",")[:3]]
    except ValueError:
        return None
    if len(b) != 3 or len(s) != 3:
        return None
    lo = tuple(b)
    hi = tuple(b[i] + s[i] for i in range(3))
    return lo, hi


def refine_axes_by_fine_divide(
        axes: dict[str, list[float]], parts, bounds_by_name=None
        ) -> dict[str, list[float]]:
    """Insert grid lines so each part has at least n cells on that axis.

    Official samples: exA02-2b fan ``2,0,0``, exA05-2 fan ``0,5,0``.
    ``n<=1`` (including 0) is a no-op. Idempotent: a later call skips an
    axis when the part AABB already spans ``n`` or more cells.
    """
    bounds_by_name = bounds_by_name or {}
    out = {ax: list(vals) for ax, vals in axes.items()}
    jobs: list[tuple[tuple[int, int, int], tuple, tuple]] = []
    for p in parts:
        ns = parse_fine_divide(getattr(p, "mesh_fine_divide", "") or "")
        if ns is None or max(ns) <= 1:
            continue
        aabb = bounds_by_name.get(getattr(p, "name", ""))
        if aabb is None:
            aabb = part_aabb_mm(p, None)
        if aabb is None:
            continue
        jobs.append((ns, aabb[0], aabb[1]))
    for i, ax in enumerate("xyz"):
        vals = out.get(ax) or []
        if len(vals) < 2:
            continue
        axis_jobs = sorted(
            ((ns[i], lo, hi) for ns, lo, hi in jobs if ns[i] > 1),
            key=lambda t: -t[0])
        for n, lo, hi in axis_jobs:
            plo, phi = float(lo[i]), float(hi[i])
            if plo > phi:
                plo, phi = phi, plo
            idxs = [j for j in range(len(vals) - 1)
                    if vals[j + 1] > plo + 1e-9 and vals[j] < phi - 1e-9]
            if not idxs or len(idxs) >= n:
                continue
            span_a = vals[idxs[0]]
            span_b = vals[idxs[-1] + 1]
            vals = divide_interval(vals, span_a, span_b, n)
        out[ax] = vals
    return out


def apply_fine_divide_to_model(model, meshes=None) -> dict[str, list[float]]:
    """Refine ``mesh_block`` axes from part ``mesh_fine_divide`` and write back."""
    axes = model.mesh_axes()
    if not axes or any(len(v) < 2 for v in axes.values()):
        return axes
    mesh_by = {getattr(m, "name", ""): m for m in (meshes or [])}
    bounds = {}
    parts = list(model.parts())
    for p in parts:
        aabb = part_aabb_mm(p, mesh_by.get(p.name))
        if aabb is not None:
            bounds[p.name] = aabb
    refined = refine_axes_by_fine_divide(axes, parts, bounds)
    for ax in "xyz":
        old = model.mesh_axis_entries(ax)
        old_vals = [v for v, _m in old]
        new_vals = refined.get(ax) or []
        if len(old_vals) == len(new_vals) and all(
                abs(a - b) < 1e-9 for a, b in zip(old_vals, new_vals)):
            continue
        mark = {round(v, 9): m for v, m in old}
        n = len(new_vals)
        entries = []
        for i, v in enumerate(new_vals):
            m = mark.get(round(v, 9), "")
            if i in (0, n - 1) and not m:
                m = "B"
            entries.append((v, m or "N"))
        model.set_mesh_axis(ax, entries)
    return refined

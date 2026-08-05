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


def rough_grids(part_points: dict[str, np.ndarray], spec: GridSpec
                ) -> dict[str, list[float]]:
    """Rough grid coordinates per axis from part vertices + domain bounds.

    ``part_points`` maps part name -> world-space points in ``spec.unit``.
    """
    dmin = np.asarray(spec.domain_min, dtype=float)
    dmax = np.asarray(spec.domain_max, dtype=float)
    out: dict[str, list[float]] = {}
    for ax_i, ax in enumerate("xyz"):
        if spec.vertex_detection == "uniform":
            out[ax] = [dmin[ax_i], dmax[ax_i]]
            continue
        vals: list[float] = []
        if spec.vertex_detection in ("all", "representative",
                                     "axis_plane", "minmax"):
            for arr in part_points.values():
                if arr is None or len(arr) == 0:
                    continue
                col = arr[:, ax_i]
                vals.append(float(col.min()))
                vals.append(float(col.max()))
        if spec.vertex_detection in ("all", "representative"):
            for arr in part_points.values():
                if arr is None or len(arr) == 0:
                    continue
                vals.extend(float(v) for v in arr[:, ax_i])
        # not_considered: domain bounds only
        out[ax] = _clip_dedupe(vals, dmin[ax_i], dmax[ax_i])
    return out


def _target_counts(spec: GridSpec) -> tuple[int, int, int]:
    if spec.target_per_axis is not None:
        return tuple(max(2, int(v)) for v in spec.target_per_axis)
    d = np.asarray(spec.domain_max, float) - np.asarray(spec.domain_min, float)
    d = np.maximum(d, 1e-12)
    geo = float(np.cbrt(d.prod()))
    n = spec.target_elements or 1_000_000
    counts = tuple(max(2, int(round((n ** (1.0 / 3.0)) * (d[i] / geo))))
                   for i in range(3))
    return counts


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
        for i, ax in enumerate("xyz"):
            out[ax] = list(np.linspace(dmin[i], dmax[i], counts[i]))
        return out
    stds = _as3(spec.standard_length)
    thrs = _as3(spec.threshold_length)
    r_in = spec.ratio_internal()
    r_ex = spec.ratio_external()
    lo = part_bounds[0] if part_bounds is not None else None
    hi = part_bounds[1] if part_bounds is not None else None
    out = {}
    for i, ax in enumerate("xyz"):
        if lo is None or hi is None:
            internal = [True] * (len(rough[ax]) - 1)
        else:
            internal = [
                (a + b) * 0.5 >= lo[i] and (a + b) * 0.5 <= hi[i]
                for a, b in zip(rough[ax][:-1], rough[ax][1:])
            ]
        ratio = [r_in[i] if k else r_ex[i] for k in internal]
        out[ax] = _refine_axis_ratios(rough[ax], stds[i], ratio, thrs[i])
    return out


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


def build_axes(part_points: dict[str, np.ndarray], spec: GridSpec
               ) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Return ``(rough, detailed)`` axes; detailed is the final mesh."""
    rough = rough_grids(part_points, spec)
    if spec.method == "rough_only":
        return rough, {ax: list(v) for ax, v in rough.items()}
    detailed = refine_grids(rough, spec)
    return rough, detailed

"""Reverse-engineered STpre gridding formulas (from DLL + black-box probes).

Sources
-------
* ``STpreBase_Bx64.dll`` ``MeshBlock::SetElementNum`` (RVA 0x1E3C40):
  auto1 per-axis cell counts from domain lengths and target element number.
* ``STpreBase_Bx64.dll`` ``MeshBlock::CalcFineCoord`` (RVA 0x1CB000):
  geometric coordinate generation with first spacing
  ``g0 = L*(1-q)/(1-q**n)`` (q == 1 -> uniform ``L/n``).
* ``MeshBlock::CalcRatio1/CalcRatio2`` (RVA 0x1CB4F0 / 0x1CB840):
  iterative geometric-ratio solvers (bisection + Newton, tol 1e-5).
* Multi-instance probes (``data/stpre_probe_20260808_*.json``): auto1
  outer left/right counts minimise ``|g0L - g0R|``.

The formulas here are standalone and testable; cab_grid/cab_gui may call
them when the native algorithm is being aligned to STpre.
"""

from __future__ import annotations

import math
from typing import Optional


def _trunc_round(x: float) -> int:
    """STpre-style rounding: ``cvttsd2si(x + 0.5)`` (truncate)."""
    return int(x + 0.5)


def auto1_per_axis_counts(
        domain_min: tuple[float, float, float],
        domain_max: tuple[float, float, float],
        target_elements: int,
        *,
        axis_symmetry: bool = False,
) -> tuple[int, int, int]:
    """Auto1 per-axis cell counts (SetElementNum disassembly).

    Cartesian branch::

        nx = trunc(((Lx^2 / (Ly*Lz)) * N)^(1/3) + 0.5)
        ny = trunc(nx * Ly / Lx + 0.5)
        nz = trunc(nx * Lz / Lx + 0.5)

    Axis-symmetry branch::

        nx = trunc(sqrt((Lx / Lz) * N) + 0.5)
        nz = trunc(nx * Lz / Lx + 0.5)
        ny = 1

    Validated against STpre probe: domain 100x50x25 mm, N=8000 ->
    (40, 20, 10) cells (41x21x11 points); cube domain -> round(N^(1/3)).
    """
    lx = domain_max[0] - domain_min[0]
    ly = domain_max[1] - domain_min[1]
    lz = domain_max[2] - domain_min[2]
    if min(lx, ly, lz) <= 0.0:
        raise ValueError("domain lengths must be positive")
    if target_elements <= 0:
        raise ValueError("target_elements must be positive")
    n = float(target_elements)
    if axis_symmetry:
        nx = _trunc_round(math.sqrt((lx / lz) * n))
        nz = _trunc_round(nx * lz / lx)
        return (nx, 1, nz)
    nx = _trunc_round(((lx * lx) / (ly * lz) * n) ** (1.0 / 3.0))
    ny = _trunc_round(nx * ly / lx)
    nz = _trunc_round(nx * lz / lx)
    return (nx, ny, nz)


def geometric_first_spacing(length: float, n: int, q: float) -> float:
    """First spacing of an n-interval geometric series over ``length``.

    Formula from ``CalcFineCoord``: ``g0 = L*(1-q)/(1-q**n)``;
    ``q == 1`` falls back to uniform ``L/n``.
    """
    if n <= 0 or length <= 0.0:
        raise ValueError("length and n must be positive")
    if q <= 0.0:
        raise ValueError("ratio must be positive")
    if abs(q - 1.0) < 1e-15:
        return length / n
    return length * (1.0 - q) / (1.0 - q ** n)


def geometric_coords(start: float, length: float, n: int, q: float,
                     ) -> list[float]:
    """n+1 coordinates ``start + sum(g0*q^i)`` (CalcFineCoord loop)."""
    g0 = geometric_first_spacing(length, n, q)
    out = [start]
    x = start
    g = g0
    for _ in range(n):
        x += g
        out.append(x)
        g *= q
    return out


def outer_g0(outer_len: float, n: int, q: float) -> float:
    """First outer spacing that makes the geometric sum exactly outer_len."""
    return geometric_first_spacing(outer_len, n, q)


def split_outer_counts(
        left_len: float,
        right_len: float,
        total: int,
        q: float = 1.2,
) -> tuple[int, int, float, float]:
    """Auto1 outer left/right split: minimise ``max(g0L, g0R)``.

    Returns ``(L, R, g0L, g0R)``.  ``total = n - P``.
    A zero-length side forces the corresponding count to 0.
    Rule validated against 13 STpre probe cases (the coarser outer side is
    made as fine as possible, i.e. the worst first spacing is minimised).
    """
    if left_len <= 0.0 and right_len <= 0.0:
        raise ValueError("at least one outer side must be positive")
    if left_len <= 0.0:
        return (0, total, 0.0, outer_g0(right_len, total, q))
    if right_len <= 0.0:
        return (total, 0, outer_g0(left_len, total, q), 0.0)
    best = None
    for l in range(1, total):
        r = total - l
        if r < 1:
            continue
        g0l = outer_g0(left_len, l, q)
        g0r = outer_g0(right_len, r, q)
        score = max(g0l, g0r)
        if best is None or score < best[0]:
            best = (score, l, r, g0l, g0r)
    if best is None:
        raise ValueError("total must be >= 2")
    return (best[1], best[2], best[3], best[4])


def inner_segment_split(seg_len: float, std: float) -> tuple[int, float]:
    """Vertex-plane segment: ``n = trunc(seg_len/std + 0.5)``, spacing
    ``seg_len/n`` (observed for all/representative on rotated boxes)."""
    if seg_len <= 0.0 or std <= 0.0:
        raise ValueError("segment length and std must be positive")
    n = max(1, _trunc_round(seg_len / std))
    return n, seg_len / n


def _outer_min_count(outer_len: float, s: float, q: float) -> int:
    """Smallest interval count whose geometric series (g0=s, ratio q)
    reaches ``outer_len``: ``ceil(log(1 + L*(q-1)/s) / log q)``."""
    if outer_len <= 0.0:
        return 0
    if s <= 0.0 or q <= 1.0:
        return max(1, int(math.ceil(outer_len / max(s, 1e-12))))
    return max(1, int(math.ceil(
        math.log1p(outer_len * (q - 1.0) / s) / math.log(q))))


def auto1_inner_count(
        part_len: float,
        left_len: float,
        right_len: float,
        n: int,
        q: float = 1.2,
) -> int:
    """Auto1 inner-region cell count P (closed form, validated).

    ``P`` is the smallest integer >= 1 with
    ``P + Lmin(p/P) + Rmin(p/P) >= n``, where ``Lmin/Rmin`` are the
    geometric-series interval counts from each part face to the domain
    boundary (``_outer_min_count``).

    Verified against 13 STpre probe cases (n=10..46, part 5/10/20 mm,
    centred/offset/boundary, cube/non-cube domains).
    """
    if part_len <= 0.0 or n < 3:
        raise ValueError("part_len must be positive and n >= 3")
    for p in range(1, n):
        s = part_len / p
        total = (p
                 + _outer_min_count(left_len, s, q)
                 + _outer_min_count(right_len, s, q))
        if total >= n:
            return p
    return n - 1


def auto1_axis_layout(
        part_lo: float,
        part_hi: float,
        domain_min: float,
        domain_max: float,
        n: int,
        q: float = 1.2,
) -> dict:
    """Full auto1 per-axis layout: counts + first spacings.

    Returns ``P, L, R, s, g0L, g0R`` (``g0`` = None when a side is empty).
    """
    left_len = part_lo - domain_min
    right_len = domain_max - part_hi
    part_len = part_hi - part_lo
    p = auto1_inner_count(part_len, left_len, right_len, n, q)
    s = part_len / p
    l, r, g0l, g0r = split_outer_counts(left_len, right_len, n - p, q)
    return {
        "P": p, "L": l, "R": r, "s": s,
        "g0L": g0l if l > 0 else None,
        "g0R": g0r if r > 0 else None,
    }


def calc_ratio(
        n: int,
        length: float,
        g0: float,
        *,
        tol: float = 1e-5,
        q_min: float = 1.0,
        q_max: float = 10.0,
) -> Optional[float]:
    """Solve q so that ``g0*(q**n-1)/(q-1) == length`` (CalcRatio style).

    Returns None when no root exists in [q_min, q_max].
    """
    def f(q: float) -> float:
        if abs(q - 1.0) < 1e-12:
            return g0 * n - length
        return g0 * (q ** n - 1.0) / (q - 1.0) - length

    lo, hi = q_min, q_max
    flo = f(lo)
    fhi = f(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0.0:
        return None
    for _ in range(500):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) < 1e-14:
            return mid
        if flo * fm <= 0.0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)

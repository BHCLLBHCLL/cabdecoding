"""Reverse-engineered STpre formula tests (no STpre launch)."""
from __future__ import annotations

import math

import stpre_rules


def test_auto1_per_axis_counts_cube():
    cube = (0.0, 0.0, 0.0), (50.0, 50.0, 50.0)
    assert stpre_rules.auto1_per_axis_counts(*cube, 8000) == (20, 20, 20)
    assert stpre_rules.auto1_per_axis_counts(*cube, 1000) == (10, 10, 10)
    assert stpre_rules.auto1_per_axis_counts(*cube, 2000) == (13, 13, 13)
    assert stpre_rules.auto1_per_axis_counts(*cube, 100000) == (46, 46, 46)


def test_auto1_per_axis_counts_noncube_matches_probe():
    dom = (0.0, 0.0, 0.0), (100.0, 50.0, 25.0)
    assert stpre_rules.auto1_per_axis_counts(*dom, 8000) == (40, 20, 10)


def test_auto1_axis_symmetry():
    dom = (0.0, 0.0, 0.0), (100.0, 50.0, 25.0)
    nx, ny, nz = stpre_rules.auto1_per_axis_counts(
        *dom, 8000, axis_symmetry=True)
    assert ny == 1
    assert nz == stpre_rules._trunc_round(nx * 25.0 / 100.0)


def test_geometric_first_spacing():
    assert stpre_rules.geometric_first_spacing(10.0, 10, 1.0) == 1.0
    g0 = stpre_rules.geometric_first_spacing(10.0, 7, 1.2)
    assert math.isclose(g0, 10.0 * (-0.2) / (1.0 - 1.2 ** 7), rel_tol=1e-12)
    coords = stpre_rules.geometric_coords(0.0, 10.0, 4, 1.0)
    assert coords == [0.0, 2.5, 5.0, 7.5, 10.0]


def test_split_outer_counts_base():
    l, r, g0l, g0r = stpre_rules.split_outer_counts(25.0, 15.0, 14, 1.2)
    assert (l, r) == (8, 6)
    assert math.isclose(g0l, 1.515, abs_tol=1e-3)
    assert math.isclose(g0r, 1.511, abs_tol=1e-3)


def test_inner_segment_split_rotated_box():
    n, spacing = stpre_rules.inner_segment_split(3.66, 1.0)
    assert n == 4
    assert math.isclose(spacing, 0.915, abs_tol=1e-3)


def test_calc_ratio_outer_base():
    q = stpre_rules.calc_ratio(10, 25.0, 1.0)
    assert q is not None
    assert math.isclose(q, 1.1922, abs_tol=1e-3)

"""§29 H1d batch — free-surface family (VOF2 / SURF_CONTROL /
SURF_PROPERTY), byte-checked against official samples.

Corpus rules verified across all 295 samples:
- SURF_PROPERTY and SURF_CONTROL co-occur 48/48 (zero exceptions);
  VOF2 appears in 38/48, driven by a defined second phase.
- SURF_CONTROL has exactly two keyword variants, never mixed:
  two-phase transport (transport_phase..filling_check, +buoyancy_in_mars
  in 2 blocks) and single-phase (hydrostatic_pressure..
  afterward_interpolation).
- Order in exA09-4: VOF2 → SURF_CONTROL → SURF_PROPERTY → SUFS_REGION.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model(**attrs):
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.analysis_etc_section("free_surf")
    for k, v in attrs.items():
        m.set_free_surf_attr(k, v)
    return m


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _build(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def test_two_phase_full_family():
    """exA09-4.s:108-111 / :176-194 / :193-196 — VOF2 (29-wide density +
    3-space 水 + '   /'), SURF_CONTROL two-phase variant, SURF_PROPERTY
    two tension rows (_i idx 6-wide + _f 26-wide)."""
    m = _model(type="vof", phase2_name="水", phase2_density="1.0",
               tension="0,0.0727")
    lines = _build(m)
    i = lines.index("VOF2")
    assert lines[i:i + 4] == [
        "VOF2",
        f"{1.0:29.14e}",
        "   水",
        "   /",
    ]
    j = lines.index("SURF_CONTROL")
    assert lines[j:j + 17] == [
        "SURF_CONTROL",
        "various",
        "transport_phase",
        f"{2:>15d}",
        "fractional_step",
        f"{5:>15d}",
        "tension_phase",
        f"{1:>15d}",
        "listout_vof",
        f"{0:>15d}",
        "cutoff_vof",
        f"{1:>15d}{1e-4:26.14e}",
        "conservation_term",
        f"{1:>15d}",
        "filling_check",
        f"{0:>15d}{95.0:26.14e}",
        "/",
    ]
    k = lines.index("SURF_PROPERTY")
    assert lines[k:k + 3] == [
        "SURF_PROPERTY",
        f"{1:>6d}{0.0:26.14e}",
        f"{2:>6d}{0.0727:26.14e}",
    ]
    assert lines[k + 3] == "/"
    assert i < j < k


def test_single_phase_variant():
    """exA10-1.s — single-phase SURF_CONTROL variant, no VOF2 card."""
    m = _model(type="mars", tension="0.0727")
    lines = _build(m)
    assert "VOF2" not in lines
    j = lines.index("SURF_CONTROL")
    assert lines[j:j + 12] == [
        "SURF_CONTROL",
        "various",
        "hydrostatic_pressure",
        f"{0:>15d}",
        "surface_shape",
        f"{1:>15d}",
        "listout_flow",
        f"{1:>15d}",
        "volume_correction",
        f"{0:>15d}",
        "afterward_interpolation",
        f"{0:>15d}",
    ]
    assert lines[j + 12] == "/"
    k = lines.index("SURF_PROPERTY")
    assert lines[k + 1] == f"{1:>6d}{0.0727:26.14e}"


def test_buoyancy_in_mars_extra_lines():
    """exA15-7.s — buoyancy_in_mars appends int + 4×26-wide float line."""
    m = _model(type="mars", phase2_name="水", phase2_density="1.0",
               tension="0,0.0727", buoyancy_in_mars="1",
               buoyancy_vals="0.003495,98.0,0.00022544,98.0")
    lines = _build(m)
    j = lines.index("SURF_CONTROL")
    assert lines[j + 16] == "buoyancy_in_mars"
    assert lines[j + 17] == f"{1:>15d}"
    assert lines[j + 18] == (
        f"{0.003495:26.14e}{98.0:26.14e}"
        f"{0.00022544:26.14e}{98.0:26.14e}")
    assert lines[j + 19] == "/"


def test_cutoff_triple_takes_first_value():
    """cutoff storage 'EPSVF,0.5,eps_save' triple -> card EPSVF (first
    value only)."""
    m = _model(type="vof", phase2_name="oil", phase2_density="0.8",
               cutoff="0.0005,0.5,1e-06", tension="0,0.02")
    lines = _build(m)
    j = lines.index("SURF_CONTROL")
    assert lines[j + 11] == f"{1:>15d}{0.0005:26.14e}"


def test_surf_property_absent_without_tension():
    """SURF_PROPERTY rows come from the tension attribute; without it the
    card is omitted (SURF_CONTROL still emits from free_surf)."""
    m = _model(type="mars")
    lines = _build(m)
    assert "SURF_CONTROL" in lines
    assert "SURF_PROPERTY" not in lines


def test_family_absent_without_free_surf():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    lines = _build(m)
    for cmd in ("VOF2", "SURF_CONTROL", "SURF_PROPERTY"):
        assert cmd not in lines, cmd


def test_ex4e_golden_zero_leak():
    from cab_container import CabArchive
    from cabxml import parse_stpre
    from s_export import build_sdat
    arch = CabArchive.parse(open("tests/ex4_e.cab", "rb").read())
    members = {mm.name: mm for mm in arch.fill_member_data()}
    m = StpreModel(parse_stpre(members["ex4_e.xml"].data))
    props = PropertyModel(parse_property(new_property_bytes()))
    s = build_sdat(m, props)
    for cmd in ("VOF2", "SURF_CONTROL", "SURF_PROPERTY"):
        assert f"\r\n{cmd}\r\n" not in s, cmd

"""§23 C6 batch: free-surface conditions — SURF_POROUS energy-attenuation
emission (exA15-6 evidence), wave_gen storage, and the storage-only
Fluid Interface / Laser / Reaction-PDF conditions."""
from __future__ import annotations

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


# --------------------------------- SURF_POROUS (exA15-6 evidence)

def test_surf_porous_matches_official_layout():
    """surface_porous energy_decay bound via <parts> emits the exA15-6
    energyattenuation card verbatim (dir width 15 + fluid_no width 12,
    five _f numbers, parts line)."""
    from s_export import build_sdat
    m = _model()
    assert m.upsert_value("surface_porous", "自由表面1", [
        ("kind", "energy_decay", None),
        ("direction", "-X", None),
        ("fluid_no", "2", None),
        ("decay", "2,0,0,3", None),
        ("depth", "7", "m"),
    ])
    assert m.bind_condition("parts", "attenuation_zone_xm", "自由表面1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("SURF_POROUS")
    assert lines[i:i + 6] == [
        "SURF_POROUS",
        "energyattenuation",
        f"{-1:15d}{2:12d}",
        f"{2.0:29.14e}" + "".join(f"{v:26.14e}" for v in (0.0, 0.0, 3.0, 7.0)),
        "   attenuation_zone_xm",
        "   /",
    ]
    assert lines.index("SURF_POROUS") < lines.index("MEIX_VAR")


def test_surf_porous_absent_and_direction_gate():
    from s_export import build_sdat
    m = _model()
    # no values -> no section
    assert "SURF_POROUS" not in build_sdat(m, _props())
    # unsupported axis direction (-Y/+Z have no corpus mapping) -> skipped
    m.upsert_value("surface_porous", "az_y", [
        ("kind", "energy_decay", None),
        ("direction", "-Y", None),
        ("fluid_no", "2", None),
        ("decay", "2,0,0,3", None),
        ("depth", "7", "m")])
    m.bind_condition("parts", "az_y_parts", "az_y")
    assert "SURF_POROUS" not in build_sdat(m, _props())

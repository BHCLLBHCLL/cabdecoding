"""W1: VFDE MREF/MRCL derived from radiation XML (max_reflection / smrt_rays)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

ROOT = Path(__file__).resolve().parents[1]
EX4_CAB = ROOT / "tests" / "ex4_e.cab"


@pytest.fixture()
def ex4_models():
    from cab_container import CabArchive
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    arch = CabArchive.parse(EX4_CAB.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return (StpreModel(parse_stpre(members["ex4_e.xml"])),
            PropertyModel(parse_property(members["_ex4_e_property.xml"])))


def _vfde_map(text: str) -> dict[str, str]:
    lines = text.splitlines()
    i = lines.index("VFDE")
    out = {}
    for row in lines[i + 1:]:
        s = row.strip()
        if s == "/":
            break
        key, _, rest = s.partition(" ")
        out[key] = rest.strip()
    return out


def test_vfde_mref_mrcl_from_xml(ex4_models):
    import s_export
    model, props = ex4_models
    model.set_radiation_type("vf")
    model.set_radiation_param("max_particle", "12345")
    model.set_radiation_param("max_reflection", "17")
    model.set_radiation_param("smrt_rays", "888")
    model.set_radiation_param("space_cycle", "3")
    model.set_radiation_param("max_group_num", "2222")
    cards = _vfde_map(s_export.build_sdat(model, props))
    assert cards["MPCL"] == "12345"
    assert cards["MREF"] == "17"
    assert cards["MRCL"] == "888"
    assert cards["IXYZ"] == "3"
    assert cards["MAXM"] == "2222"
    assert cards["LEAP"] == "1"
    assert cards["EM1"] == "0.99"


def test_vfde_mrcl_defaults_to_mpcl(ex4_models):
    import s_export
    model, props = ex4_models
    model.set_radiation_type("vf")
    model.set_radiation_param("max_particle", "20000")
    model.set_radiation_param("max_reflection", "100")
    cards = _vfde_map(s_export.build_sdat(model, props))

    assert cards["MREF"] == "100"
    assert "MRCL" not in cards  # golden ex4_e.s: MRCL only when smrt_rays set
    assert cards["MPCL"] == "20000"

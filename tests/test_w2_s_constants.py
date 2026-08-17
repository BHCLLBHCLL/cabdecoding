"""W2: pin .s hdr1/hdr2 tails and VFDE LEAP/EM1 (no invented XML tags)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import s_export

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


def _ints(line: str, width: int = 12) -> list[int]:
    s = line.rstrip()
    return [int(s[i:i + width]) for i in range(0, len(s), width) if s[i:i + width].strip()]


def test_pinned_hdr_and_vfde_constants(ex4_models):
    assert s_export.HDR1_TAIL == (1, 1, 0, 0, 0)
    assert s_export.HDR2_TAIL == (0, 0, 0, 0, 0, 0)
    assert s_export.VFDE_LEAP == 1
    assert s_export.VFDE_EM1 == 0.99
    model, props = ex4_models
    lines = s_export.build_sdat(model, props).splitlines()
    marker = next(i for i, l in enumerate(lines) if l.strip() == "1")
    hdr1 = _ints(lines[marker + 1])
    hdr2 = _ints(lines[marker + 2])
    assert tuple(hdr1[-5:]) == s_export.HDR1_TAIL
    assert tuple(hdr2[-6:]) == s_export.HDR2_TAIL
    i = lines.index("VFDE")
    cards = {}
    for row in lines[i + 1:]:
        s = row.strip()
        if s == "/":
            break
        key, _, rest = s.partition(" ")
        cards[key] = rest.strip()
    assert cards["LEAP"] == "1"
    assert cards["EM1"] == "0.99"

"""hdr1 col6 from analysis_etc/particle/max_num (official ST Example)."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
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
    return [int(s[i:i + width]) for i in range(0, len(s), width)
            if s[i:i + width].strip()]


def _hdr1(sdat: str) -> list[int]:
    lines = sdat.splitlines()
    marker = next(i for i, l in enumerate(lines) if l.strip() == "1")
    return _ints(lines[marker + 1])


def _set_particle(model, max_num: int) -> None:
    aet = model.root.find("analysis_etc")
    if aet is None:
        aet = ET.SubElement(model.root, "analysis_etc")
    particle = aet.find("particle")
    if particle is None:
        particle = ET.SubElement(aet, "particle")
    mx = particle.find("max_num")
    if mx is None:
        mx = ET.SubElement(particle, "max_num")
    mx.text = f" {max_num} "


def test_hdr1_default_without_particle(ex4_models):
    model, props = ex4_models
    assert s_export.hdr1_tail(model) == s_export.HDR1_TAIL
    assert tuple(_hdr1(s_export.build_sdat(model, props))[-5:]) == (
        1, 1, 0, 0, 0)


def test_hdr1_particle_max_num_10000(ex4_models):
    model, props = ex4_models
    _set_particle(model, 10000)
    assert s_export.hdr1_tail(model) == (1, 1, 10000, 0, 0)
    assert tuple(_hdr1(s_export.build_sdat(model, props))[-5:]) == (
        1, 1, 10000, 0, 0)


def test_hdr1_particle_max_num_1e6(ex4_models):
    model, props = ex4_models
    _set_particle(model, 1000000)
    assert s_export.hdr1_tail(model) == (1, 1, 1000000, 0, 0)
    assert tuple(_hdr1(s_export.build_sdat(model, props))[-5:]) == (
        1, 1, 1000000, 0, 0)

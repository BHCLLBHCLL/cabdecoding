"""P3: .s / .xemt export parity with the official exporter output."""

import os
import re
import sys

import pytest

import xemt_export
from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
from s_export import build_sdat


HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")
S_OFFICIAL = os.path.join(HERE, "ex4_e.s")
XEMT_OFFICIAL = os.path.join(HERE, "ex4_e.xemt")
FLDDECODING = r"D:\training\cgns\flddecoding"


def _models():
    arch = CabArchive.parse(open(CAB, "rb").read())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return (StpreModel(parse_stpre(members["ex4_e.xml"])),
            PropertyModel(parse_property(members["_ex4_e_property.xml"])))


def _floats(line: str) -> list[float]:
    return [float(x) for x in line.split()
            if re.fullmatch(r"[+-]?[\d.eE+-]+", x)]


def test_s_export_structural_parity():
    model, props = _models()
    ours = build_sdat(model, props)
    official = open(S_OFFICIAL, encoding="utf-8-sig").read()
    a, b = official.splitlines(), ours.splitlines()
    assert len(a) == len(b)
    structural = 0
    for x, y in zip(a, b):
        if x == y:
            continue
        fx, fy = _floats(x), _floats(y)
        if len(fx) == len(fy) and fx and all(
                abs(p - q) < 1e-12 for p, q in zip(fx, fy)):
            continue
        structural += 1
    # only known CXYZ last-digit rounding from XML float text can differ
    assert structural == 0


def test_s_export_consumed_by_flddecoding():
    if not os.path.isdir(FLDDECODING):
        pytest.skip("flddecoding repo not available")
    sys.path.insert(0, FLDDECODING)
    try:
        from s_model import parse_sdat
    finally:
        sys.path.pop(0)
    model, props = _models()
    ours = parse_sdat(build_sdat(model, props))
    official = parse_sdat(open(S_OFFICIAL, encoding="utf-8-sig").read())
    assert ours.basename == official.basename == "ex4_e"
    assert (ours.ni, ours.nj, ours.nk) == (official.ni, official.nj,
                                           official.nk) == (98, 242, 62)
    assert [len(a) for a in ours.cxyz] == [99, 243, 63]
    for a, b in zip(ours.cxyz, official.cxyz):
        assert a.shape == b.shape
        assert abs(a - b).max() < 1e-9
    assert [p.name for p in ours.parts] == [p.name for p in official.parts]
    assert [p.material_id for p in ours.parts] == \
        [p.material_id for p in official.parts]
    assert [len(p.boxes) for p in ours.parts] == \
        [len(p.boxes) for p in official.parts]
    assert ours.ambient_temp == official.ambient_temp == 20.0
    assert [r for r in ours.region_names] == [r for r in official.region_names]


def test_xemt_export_matches_official():
    model, props = _models()
    ours = xemt_export.build_emt(model, props)
    official = open(XEMT_OFFICIAL, encoding="utf-8-sig").read()
    a = [ln for ln in ours.splitlines() if "date/time" not in ln]
    b = [ln for ln in official.splitlines() if "date/time" not in ln]
    assert a == b
    assert len([ln for ln in official.splitlines()
                if "<mat " in ln]) == 7
    assert len([ln for ln in official.splitlines()
                if "<part " in ln]) == 32


def test_xemt_material_numbers():
    model, props = _models()
    ours = xemt_export.build_emt(model, props)
    order = []
    for m in re.finditer(r'<mat no="(\d+)" name="([^"]+)"', ours):
        order.append((int(m.group(1)), m.group(2)))
    assert [n for n, _ in order] == list(range(1, 8))
    assert order[0][1] == "air(incompressible/20C)"
    assert order[6][1] == "diecast_magnesium(300K)"
    assert '<part no="2" name="lower_cover_01" mat="7"/>' in ours
    assert '<part no="32" name="(cuboid)_U_04" mat="4"/>' in ours
    assert '<fluid no="1" name="Domain(cuboid)" mat="1"/>' in ours


def test_s_export_key_values():
    model, props = _models()
    s = build_sdat(model, props)
    assert "          98         242          62" in s
    assert "     -9.80000000000000e+00" in s          # gravity
    assert "   air(incompressible/20C) ! (1)" in s    # fluid property
    assert "diecast_magnesium(300K) ! (7)" in s
    assert "total-pres    0   ! Flux1" in s
    assert "   @UNDEFINEDMOM" in s
    assert "source    0   ! HeatSource8" in s
    assert s.endswith("GOGO\r\n")

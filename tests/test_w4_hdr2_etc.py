"""hdr2 col4/6/8 from fusion, free_surf, and moving_body (official ST Example)."""
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


def _hdr2(sdat: str) -> list[int]:
    lines = sdat.splitlines()
    marker = next(i for i, l in enumerate(lines) if l.strip() == "1")
    return _ints(lines[marker + 2])


def _ensure(parent, path: str, text=None):
    el = parent
    for tag in path.split("/"):
        child = el.find(tag)
        if child is None:
            child = ET.SubElement(el, tag)
        el = child
    if text is not None:
        el.text = f" {text} "
    return el


def test_hdr2_default_ex4(ex4_models):
    model, props = ex4_models
    assert s_export.hdr2_tail(model) == s_export.HDR2_TAIL
    assert tuple(_hdr2(s_export.build_sdat(model, props))[-6:]) == (
        0, 0, 0, 0, 0, 0)


def test_hdr2_fusion_col4(ex4_models):
    model, props = ex4_models
    _ensure(model.root, "analysis_etc/fusion")
    assert s_export.hdr2_tail(model)[0] == 2
    assert _hdr2(s_export.build_sdat(model, props))[3] == 2


def test_hdr2_free_surf_col6(ex4_models):
    model, props = ex4_models
    _ensure(model.root, "analysis_etc/free_surf")
    assert s_export.hdr2_tail(model)[2] == 1
    assert _hdr2(s_export.build_sdat(model, props))[5] == 1


def test_hdr2_moving_body_col8(ex4_models):
    model, props = ex4_models
    _ensure(model.root, "analysis_set/moving_body", "2")
    assert s_export.hdr2_tail(model)[4] == 2
    assert _hdr2(s_export.build_sdat(model, props))[7] == 2


def test_hdr2_overlays_combine(ex4_models):
    model, props = ex4_models
    _ensure(model.root, "analysis_etc/fusion")
    _ensure(model.root, "analysis_etc/free_surf")
    _ensure(model.root, "analysis_set/moving_body", "1")
    assert s_export.hdr2_tail(model) == (2, 0, 1, 0, 1, 0)
    assert tuple(_hdr2(s_export.build_sdat(model, props))[-6:]) == (
        2, 0, 1, 0, 1, 0)

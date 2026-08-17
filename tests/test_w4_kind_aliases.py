"""Official STpre part type aliases (2023.2 ST Example)."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from cab_parts import tess_for_part
from cabxml import (
    PART_KIND_ALIASES, StpreModel, canonical_part_kind, new_stpre_bytes,
    parse_stpre,
)


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("alias")))


def _add_raw(model, name, type_, children):
    model.add_part(name=name, kind=type_, attribute="solid")
    el = model.find_part(name)
    el.attrib["type"] = type_
    for tag, text, attrib in children:
        c = ET.SubElement(el, tag)
        c.text = f" {text} "
        if attrib:
            c.attrib.update(attrib)
    return el


def test_canonical_part_kind_table():
    assert PART_KIND_ALIASES["axial_fan_model"] == "axial_fan"
    assert canonical_part_kind("spin_rectangle") == "revolved"
    assert canonical_part_kind("case_cube") == "enclosure"
    assert canonical_part_kind("hexa") == "hexahedron"
    assert canonical_part_kind("air_outlet") == "diffuser"
    assert canonical_part_kind("cube") == "cube"


def test_network_package_two_resist():
    m = _model()
    el = _add_raw(m, "TR", "network", [
        ("package", "TWO_RESIST", None),
        ("base", "0,0,0", {"unit": "mm"}),
        ("size", "20,20,2", {"unit": "mm"}),
    ])
    assert canonical_part_kind("network", el) == "two_resistor"
    info = next(p for p in m.parts() if p.name == "TR")
    assert info.kind == "two_resistor"
    assert info.elem.attrib["type"] == "network"
    assert m.part_params("TR") is not None
    # serialize keeps official type
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.find_part("TR").attrib["type"] == "network"
    assert next(p for p in again.parts() if p.name == "TR").kind == (
        "two_resistor")


def test_parts_kind_aliases_roundtrip_type():
    m = _model()
    _add_raw(m, "Fan", "axial_fan_model", [
        ("center", "0,0,0", {"unit": "mm"}),
        ("size", "100,400", {"unit": "mm"}),
        ("thick", "150,150", {"unit": "mm"}),
    ])
    _add_raw(m, "Case", "case_cube", [
        ("base", "0,0,0", {"unit": "mm"}),
        ("size", "510,110,155", {"unit": "mm"}),
    ])
    kinds = {p.name: p.kind for p in m.parts()}
    assert kinds["Fan"] == "axial_fan"
    assert kinds["Case"] == "enclosure"
    xml = m.doc.serialize().decode("utf-8")
    assert 'type="axial_fan_model"' in xml
    assert 'type="case_cube"' in xml


def test_tess_axial_fan_model_size_thick():
    m = _model()
    _add_raw(m, "Fan", "axial_fan_model", [
        ("center", "0,0,0", {"unit": "mm"}),
        ("size", "100,400", {"unit": "mm"}),
        ("thick", "150,150", {"unit": "mm"}),
    ])
    part = next(p for p in m.parts() if p.name == "Fan")
    tess = tess_for_part(part)
    assert tess is not None
    xy = np.linalg.norm(tess.points[:, :2], axis=1)
    assert xy.max() == pytest.approx(0.4, rel=1e-3)
    assert xy.min() == pytest.approx(0.1, rel=1e-2)
    assert tess.points[:, 2].ptp() == pytest.approx(0.15, rel=1e-3)


def test_tess_spin_rectangle_half_cylinder():
    m = _model()
    _add_raw(m, "Cyl", "spin_rectangle", [
        ("define", "0.5,0,0.725", {"unit": "m"}),
        ("width", "1", {"unit": "m"}),
        ("height", "1.45", {"unit": "m"}),
        ("angle", "0,180", None),
        ("divide", "32", None),
    ])
    part = next(p for p in m.parts() if p.name == "Cyl")
    assert part.kind == "revolved"
    tess = tess_for_part(part)
    assert tess is not None
    # 180 deg cylinder r=0..1 m, z=0..1.45 m → volume ≈ 0.5 π r² h
    rs = np.linalg.norm(tess.points[:, :2], axis=1)
    assert rs.max() == pytest.approx(1.0, rel=1e-3)
    assert tess.points[:, 2].min() == pytest.approx(0.0, abs=1e-6)
    assert tess.points[:, 2].max() == pytest.approx(1.45, rel=1e-3)


def test_tess_hexa_p1_p8_metres():
    m = _model()
    children = []
    corners = [
        (0, 0, 0), (0.09, -0.06, 0), (1, 0, 0), (0.09, 0.06, 0),
        (0, 0, 1), (0.09, -0.06, 1), (1, 0, 1), (0.09, 0.06, 1),
    ]
    for i, xyz in enumerate(corners, start=1):
        children.append((f"p{i}", f"{xyz[0]},{xyz[1]},{xyz[2]}",
                         {"unit": "m"}))
    _add_raw(m, "Rotor", "hexa", children)
    part = next(p for p in m.parts() if p.name == "Rotor")
    assert part.kind == "hexahedron"
    tess = tess_for_part(part)
    assert tess is not None
    assert tess.points[:, 0].max() == pytest.approx(1.0)
    assert tess.points[:, 2].max() == pytest.approx(1.0)

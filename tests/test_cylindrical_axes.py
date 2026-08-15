"""P0-2: cylindrical/axial domain gridding aligned to STpre COM probe.

Golden values come from live STpre 2025.2 COM round-trips
(tools/probe_cyl_domain.py, 2026-08-15): SetCylindricalDomain +
root-block SetParam(length/limit/ratio) + SetGridParam(minmax/detail) +
ExecuteGrid + SaveCabFile, mesh_block r/t/z tables read back verbatim.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cab_domain
import cab_grid
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX_CAB = ROOT / "tests" / "box.cab"

# 20 mm cube centred on the axis (tests/box.cab body): corners at +-10
BOX_PTS = np.array(
    [[sx * 10.0, sy * 10.0, sz * 10.0]
     for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)],
    dtype=np.float64,
)

# STpre-probed mesh_block r and z tables (minmax, std=5, ratio_ext=1.2,
# domain r 0..50 / theta 0..360 / z 0..50, box part on the axis).
GOLD_R_STD5 = [0.0, 4.7140452, 9.4280904, 14.1421356, 19.1421356,
               25.0482818, 32.0247943, 40.2656547, 50.0]
GOLD_Z_STD5 = [0.0, 5.0, 10.0, 15.0, 20.5717, 26.7804, 33.6991,
               41.4088, 50.0]
GOLD_R_ANNULUS = [20.0, 25.0, 30.4564, 36.4109, 42.9089, 50.0]
GOLD_R_STD2_5 = [0.0, 2.357, 4.714, 7.0711, 9.4281, 11.7851, 14.1421,
                 16.6421, 19.547, 22.9224, 26.8445, 31.4018, 36.6973,
                 42.8503, 50.0]


def _spec(r1, t1, z1, r2, t2, z2, std, *, coord="cylindrical"):
    return cab_grid.GridSpec(
        unit="mm", domain_min=(r1, t1, z1), domain_max=(r2, t2, z2),
        domain_coordinate=coord, vertex_detection="minmax",
        method="rough_and_detail", standard_length=std,
        threshold_length=0.1, geometric_ratio=1.0,
        geometric_ratio_external=1.2)


def _approx(vals, gold, tol=1e-3):
    assert len(vals) == len(gold), (vals, gold)
    for v, g in zip(vals, gold):
        assert abs(v - g) <= tol, (vals, gold)


def test_radial_and_z_axes_match_stpre_golden():
    spec = _spec(0.0, 0.0, 0.0, 50.0, 360.0, 50.0, 5.0)
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    _approx(ax["x"], GOLD_R_STD5)
    _approx(ax["z"], GOLD_Z_STD5)


def test_radial_std_2_5_matches_stpre_golden():
    spec = _spec(0.0, 0.0, 0.0, 50.0, 360.0, 50.0, 2.5)
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    _approx(ax["x"], GOLD_R_STD2_5)


def test_annulus_with_axis_part_fully_external():
    """Part inside the r<20 hole: the whole domain is the external region
    (STpre golden 20,25,30.4564,36.4109,42.9089,50)."""
    spec = _spec(20.0, 0.0, 0.0, 50.0, 360.0, 50.0, 5.0)
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    _approx(ax["x"], GOLD_R_ANNULUS)


def test_theta_counts_match_stpre():
    # probe: 360/5 -> 72 cells, 180/5 -> 36, 360/2.5 -> 144
    for t2, std, cells in ((360.0, 5.0, 72), (180.0, 5.0, 36),
                           (360.0, 2.5, 144)):
        spec = _spec(0.0, 0.0, 0.0, 50.0, t2, 50.0, std)
        _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
        assert len(ax["y"]) == cells + 1
        assert ax["y"][0] == 0.0
        assert abs(ax["y"][-1] - t2) < 1e-9
        d = np.diff(ax["y"])
        assert np.allclose(d, d[0])


def test_theta_span_respects_domain_min():
    spec = _spec(0.0, 30.0, 0.0, 50.0, 150.0, 50.0, 5.0)
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    assert ax["y"][0] == 30.0
    assert abs(ax["y"][-1] - 150.0) < 1e-9
    assert len(ax["y"]) == 120 / 5 + 1


def test_radial_part_extent_contains_axis():
    lo, hi = cab_grid._radial_part_extent({"box": BOX_PTS})
    assert lo == 0.0
    assert abs(hi - 10.0 * np.sqrt(2.0)) < 1e-9
    off = BOX_PTS + np.array([15.0, 0.0, 0.0])
    lo2, hi2 = cab_grid._radial_part_extent({"off": off})
    # corners at (5,+-10) and (25,+-10): r = sqrt(125) / sqrt(725)
    assert abs(lo2 - np.sqrt(125.0)) < 1e-9
    assert abs(hi2 - np.sqrt(725.0)) < 1e-9


def test_axial_axes_collapse_y_to_min_len():
    spec = _spec(0.0, 0.0, 0.0, 50.0, 100.0, 50.0, 5.0, coord="axial")
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    assert ax["y"] == [0.0, 50.0]
    assert ax["x"][0] == 0.0 and ax["x"][-1] == 50.0
    assert ax["z"][0] == 0.0 and ax["z"][-1] == 50.0


def _model():
    a = CabArchive.parse(BOX_CAB.read_bytes())
    a.fill_member_data()
    d = next(m.data for m in a.members
             if m.name.endswith(".xml") and not m.name.startswith("_"))
    return StpreModel(parse_stpre(d))


def test_cylindrical_serialization_roundtrip():
    import xml.etree.ElementTree as ET
    m = _model()
    spec = _spec(0.0, 0.0, 0.0, 50.0, 360.0, 50.0, 5.0)
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    m.set_mesh(ax, unit="mm", domain_min=(0.0, 0.0, 0.0),
               domain_max=(50.0, 360.0, 50.0),
               threshold=(0.1, 0.1, 0.1), ratio=(1.0, 1.0, 1.0),
               standard_length=(5.0, 5.0, 5.0),
               ratio_external=(1.2, 1.2, 1.2),
               coordinate="cylindrical")
    mb = m.mesh_block()
    sys_el = mb.find("system")
    assert (sys_el.text or "").strip() == "1"
    t_el = mb.find("t")
    assert t_el is not None
    assert t_el.attrib["unit"] == "radian"
    assert t_el.attrib["num"] == "73"
    r_el = mb.find("r")
    assert r_el is not None and r_el.attrib["unit"] == "mm"
    assert mb.find("x") is None and mb.find("y") is None
    mx = (mb.find("max").text or "").strip()
    vals = [float(x.strip()) for x in mx.split(",")]
    assert abs(vals[1] - 2.0 * np.pi) < 1e-12
    assert m.mesh_coordinate() == "cylindrical"
    ax2 = m.mesh_axes()
    _approx(ax2["x"], GOLD_R_STD5)
    assert len(ax2["y"]) == 73
    assert abs(ax2["y"][-1] - 360.0) < 1e-9
    bounds = m.root_block_bounds()
    assert abs(bounds[4] - 360.0) < 1e-9  # max y back in degrees


def test_set_mesh_axis_converts_theta_degrees_to_radians():
    m = _model()
    spec = _spec(0.0, 0.0, 0.0, 50.0, 360.0, 50.0, 5.0)
    _rough, ax = cab_grid.build_axes({"box": BOX_PTS}, spec)
    m.set_mesh(ax, unit="mm", domain_min=(0.0, 0.0, 0.0),
               domain_max=(50.0, 360.0, 50.0),
               threshold=(0.1, 0.1, 0.1), ratio=(1.0, 1.0, 1.0),
               standard_length=(5.0, 5.0, 5.0),
               ratio_external=(1.2, 1.2, 1.2),
               coordinate="cylindrical")
    m.set_mesh_axis("y", [(0.0, "B"), (90.0, "N"), (360.0, "B")])
    t_el = m.mesh_block().find("t")
    assert t_el.attrib["num"] == "3"
    gs = [c.text for c in t_el if c.tag == "g"]
    got = [float(g.split(",")[0].strip()) for g in gs]
    assert abs(got[1] - np.pi / 2.0) < 1e-12
    assert abs(got[2] - 2.0 * np.pi) < 1e-12
    entries = m.mesh_axis_entries("y")
    assert abs(entries[1][0] - 90.0) < 1e-9


def test_cylinder_domain_xml_roundtrip():
    m = _model()
    spec = cab_domain.DomainSpec(
        coordinate="cylindrical", unit="mm",
        xyz_min=(10.0, 30.0, 0.0), xyz_max=(50.0, 330.0, 80.0),
        material="air(incompressible/20C)")
    assert cab_domain.apply_domain(m, spec)
    ar = m.analysis_region()
    assert ar.attrib.get("type") == "cylinder"
    assert (ar.find("radius").text or "").strip() == "10,50"
    assert ar.find("radius").attrib.get("unit") == "mm"
    assert (ar.find("angle").text or "").strip() == "30,330"
    assert (ar.find("height").text or "").strip() == "0,80"
    assert ar.find("base") is None and ar.find("size") is None
    back = cab_domain.domain_from_xml(m)
    assert back.coordinate == "cylindrical"
    assert back.xyz_min == pytest.approx((10.0, 30.0, 0.0))
    assert back.xyz_max == pytest.approx((50.0, 330.0, 80.0))


def test_axial_domain_flag_and_cleanup():
    m = _model()
    spec = cab_domain.DomainSpec(
        coordinate="axial", unit="mm",
        xyz_min=(0.0, 0.0, 0.0), xyz_max=(50.0, 100.0, 50.0))
    assert cab_domain.apply_domain(m, spec)
    assert m.analysis_set_value("axissymmetry") == "1"
    assert m.analysis_region().attrib.get("type") == "cube"
    assert cab_domain.domain_from_xml(m).coordinate == "axial"
    spec2 = cab_domain.DomainSpec(
        coordinate="cartesian", unit="mm",
        xyz_min=(0.0, 0.0, 0.0), xyz_max=(50.0, 100.0, 50.0))
    assert cab_domain.apply_domain(m, spec2)
    assert m.analysis_set_value("axissymmetry", "0") == "0"
    assert cab_domain.domain_from_xml(m).coordinate == "cartesian"

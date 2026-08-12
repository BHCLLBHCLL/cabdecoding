"""M38: import/export format matrix smoke (OBJ/STL; XT if pskernel)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import cab_import

ROOT = Path(__file__).resolve().parents[1]
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"


def _unit_cube_mm():
    """Axis-aligned unit cube in mm (8 verts / 12 tris)."""
    pts = np.array([
        [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
        [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10],
    ], dtype=np.float64) / 1000.0  # metres for tess
    tris = np.array([
        [0, 1, 2], [0, 2, 3],
        [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1],
        [1, 5, 6], [1, 6, 2],
        [2, 6, 7], [2, 7, 3],
        [3, 7, 4], [3, 4, 0],
    ], dtype=np.int64)
    return pts, tris


def test_obj_roundtrip_smoke():
    pts, tris = _unit_cube_mm()
    out_dir = ROOT / "tests" / "_m38_tmp"
    out_dir.mkdir(exist_ok=True)
    obj = out_dir / "cube.obj"
    lines = [f"v {p[0]} {p[1]} {p[2]}" for p in pts]
    for t in tris:
        lines.append(f"f {t[0] + 1} {t[1] + 1} {t[2] + 1}")
    obj.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        pts2, tris2 = cab_import.parse_obj_file(obj)
        assert len(pts2) == 8
        assert len(tris2) == 12
        # Export-style: OBJ → STL bytes → parse back
        stl = cab_import._tris_to_stl_bytes(pts2, tris2, "cube")
        assert len(stl) > 84
        pts3, tris3 = cab_import.parse_stl_bytes(stl)
        assert len(pts3) >= 3
        assert len(tris3) == 12
    finally:
        try:
            obj.unlink()
        except OSError:
            pass


def test_stl_roundtrip_smoke():
    pts, tris = _unit_cube_mm()
    raw = cab_import._tris_to_stl_bytes(pts, tris, "cube")
    pts2, tris2 = cab_import.parse_stl_bytes(raw)
    assert len(tris2) == 12
    lo, hi = pts2.min(0), pts2.max(0)
    np.testing.assert_allclose(lo, [0, 0, 0], atol=1e-5)
    np.testing.assert_allclose(hi, [0.01, 0.01, 0.01], atol=1e-5)


_DXF_3DFACE = """0
3DFACE
10
0
20
0
30
0
11
1000
21
0
31
0
12
1000
22
1000
32
0
13
0
23
1000
33
0
0
ENDSEC
"""


def test_dxf_import_3dface():
    out_dir = ROOT / "tests" / "_m38_tmp"
    out_dir.mkdir(exist_ok=True)
    p = out_dir / "face.dxf"
    p.write_text(_DXF_3DFACE, encoding="ascii")
    try:
        bodies, _raw, fmt = cab_import.import_file_with_payload(p)
        assert fmt == "stl"
        assert bodies and len(bodies[0].tess.triangles) >= 1
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def test_mdl_import_obj_compat():
    out_dir = ROOT / "tests" / "_m38_tmp"
    out_dir.mkdir(exist_ok=True)
    p = out_dir / "shape.mdl"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    try:
        bodies, _raw, fmt = cab_import.import_file_with_payload(p)
        assert fmt == "stl"
        assert bodies and bodies[0].tess.triangles.shape[0] == 1
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def _box_model_props():
    from cab_container import CabArchive
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    arch = CabArchive.parse((ROOT / "tests" / "box.cab").read_bytes())
    arch.fill_member_data()
    mm = {m.name: m.data for m in arch.members}
    xml = next(n for n in mm if n.endswith(".xml") and not n.startswith("_"))
    prop = next(n for n in mm if n.endswith("_property.xml"))
    return (StpreModel(parse_stpre(mm[xml])),
            PropertyModel(parse_property(mm[prop])), mm)


def test_s_export_roundtrip_names():
    import s_export
    model, props, _ = _box_model_props()
    text = s_export.build_sdat(model, props)
    assert text.startswith("SDAT")
    names = s_export.parse_s_parts(text)
    assert any("box" in n for n in names)


def test_xemt_export_smoke():
    from xemt_export import build_emt
    model, props, _ = _box_model_props()
    text = build_emt(model, props)
    assert "<EMT>" in text and "Domain" in text


def test_property_xml_roundtrip():
    from cabxml import PropertyModel, parse_property
    _model, _props, mm = _box_model_props()
    prop = next(n for n in mm if n.endswith("_property.xml"))
    pm = PropertyModel(parse_property(mm[prop]))
    pm2 = PropertyModel(parse_property(pm.doc.serialize()))
    assert pm2.find_entry("air(incompressible/20C)") is not None


def test_xt_member_roundtrip():
    _model, _props, mm = _box_model_props()
    raw = next(v for k, v in mm.items() if k.endswith(".x_t"))
    bodies = cab_import.import_xt_bytes(raw, adaptive=False)
    assert bodies and bodies[0].name == "box"


@pytest.mark.skipif(not cab_import.available(),
                    reason="pskernel not installed")
def test_xt_import_smoke_if_available():
    assert BOX_XT.is_file()
    bodies = cab_import.import_xt_file(BOX_XT)
    assert bodies
    assert bodies[0].tess is not None
    assert len(bodies[0].tess.triangles) > 0


def test_unsupported_iges_idf_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        cab_import.import_file("dummy.iges")
    with pytest.raises(ValueError, match="unsupported"):
        cab_import.import_file("dummy.idf")

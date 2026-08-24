"""P3: import-export batch tests (NAS read, IFC profile export)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from pathlib import Path

import cab_ifc
import cab_import
from cab_container import CabArchive
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("demo")))


# ---------------------------------------------------------------- P3-1 NAS

SAMPLE_NAS = """$ simple Nastran plate
GRID    1      0.0     0.0     0.0
GRID    2      1.0     0.0     0.0
GRID    3      1.0     1.0     0.0
GRID    4      0.0     1.0     0.0
GRID    99     9.0     9.0     9.0
PSHELL  1      7       0.5
CTRIA3  1      1       1       2       3
CQUAD4  2      1       1       2       4       3
ENDDATA
"""

SAMPLE_NAS_FREE = """$ free-field, comma separated
GRID,1,0.,0.,0.
GRID,2,1.,0.,0.
GRID,3,1.,1.,0.
CTRIA3,1,1,1,2,3
"""


def test_nas_parse_grid_elements_and_props():
    pts, tris, props = cab_import.parse_nas_bytes(
        SAMPLE_NAS.encode("ascii"))
    # node 99 is unreferenced and dropped
    assert len(pts) == 4
    assert np.allclose(pts[0], (0.0, 0.0, 0.0))
    assert np.allclose(pts[1], (1.0, 0.0, 0.0))
    # CTRIA3 -> 1 tri, CQUAD4 -> 2 tris
    assert len(tris) == 3
    assert set(map(tuple, tris)) == {(0, 1, 2), (0, 1, 3), (0, 3, 2)}
    assert props == {1: 7}


def test_nas_parse_free_field():
    pts, tris, props = cab_import.parse_nas_bytes(
        SAMPLE_NAS_FREE.encode("ascii"))
    assert len(pts) == 3 and len(tris) == 1
    assert props == {}


def test_nas_parse_scientific_notation():
    raw = ("GRID 1 1.0+03 0.0 0.0\n"
           "GRID 2 2.0D+03 0.0 0.0\n"
           "GRID 3 3.0e+03 0.0 0.0\n"
           "CTRIA3 1 1 1 2 3\n").encode("ascii")
    pts, tris, _ = cab_import.parse_nas_bytes(raw)
    assert np.allclose(pts[:, 0], (1000.0, 2000.0, 3000.0))


def test_nas_parse_missing_data_raises():
    with pytest.raises(ValueError, match="Nastran"):
        cab_import.parse_nas_bytes(b"GRID 1 0. 0. 0.\n")


@pytest.mark.skipif(not cab_import.available(),
                    reason="pskernel not available")
def test_nas_import_dispatch(tmp_path):
    p = tmp_path / "plate.nas"
    p.write_text(SAMPLE_NAS, encoding="ascii")
    bodies, raw, fmt = cab_import.import_file_with_payload(p)
    assert fmt == "stl"
    assert len(bodies) == 1
    assert len(bodies[0].tess.triangles) == 3


def test_nas_import_nas_file_direct(tmp_path):
    p = tmp_path / "plate.nas"
    p.write_text(SAMPLE_NAS, encoding="ascii")
    if cab_import.available():
        bodies = cab_import.import_nas_file(p)
        assert len(bodies) == 1


# ------------------------------------------------- P3-2 IFC profile export

SAMPLE_IFC_CIRCLE = '''ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('c.ifc','2026-01-01T00:00:00',(''),(''),'x','x','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCCARTESIANPOINT((0.,0.,0.));
#2=IFCDIRECTION((0.,0.,1.));
#3=IFCDIRECTION((1.,0.,0.));
#4=IFCAXIS2PLACEMENT3D(#1,#2,#3);
#5=IFCLOCALPLACEMENT($,#4);
#6=IFCCARTESIANPOINT((0.,0.));
#7=IFCAXIS2PLACEMENT2D(#6,$);
#8=IFCCIRCLEPROFILEDEF(.CIRCLE.,$,#7,0.5);
#9=IFCEXTRUDEDAREASOLID(#8,#4,#2,3.);
#10=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#9));
#11=IFCPRODUCTDEFINITIONSHAPE($,$,(#10));
#12=IFCCOLUMN('2O2Fr$t4X7Zf8NOew3FLOHV','Col-1',$,#11,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;'''

SAMPLE_IFC_POLYGON = '''ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('p.ifc','2026-01-01T00:00:00',(''),(''),'x','x','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCCARTESIANPOINT((0.,0.,0.));
#2=IFCDIRECTION((0.,0.,1.));
#3=IFCDIRECTION((1.,0.,0.));
#4=IFCAXIS2PLACEMENT3D(#1,#2,#3);
#5=IFCLOCALPLACEMENT($,#4);
#10=IFCCARTESIANPOINT((0.,0.));
#11=IFCCARTESIANPOINT((2.,0.));
#12=IFCCARTESIANPOINT((2.,1.));
#13=IFCCARTESIANPOINT((1.,1.5));
#14=IFCCARTESIANPOINT((0.,1.));
#15=IFCPOLYLINE((#10,#11,#12,#13,#14));
#16=IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,$,#15);
#17=IFCEXTRUDEDAREASOLID(#16,#4,#2,0.5);
#18=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#17));
#19=IFCPRODUCTDEFINITIONSHAPE($,$,(#18));
#20=IFCSLAB('2O2Fr$t4X7Zf8NOew3FLOHV','Slab-Poly',$,#19,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;'''


def test_ifc_export_circle_profile_roundtrip():
    m = _model()
    names = cab_ifc.register_ifc_parts(
        m, cab_ifc.parse_ifc(SAMPLE_IFC_CIRCLE))
    assert names == ["Col-1"]
    out = cab_ifc.model_to_ifc(m)
    assert "IFCCIRCLEPROFILEDEF" in out
    assert "IFCRECTANGLEPROFILEDEF" not in out
    solids = cab_ifc.parse_ifc(out)
    assert len(solids) == 1
    s = solids[0]
    assert s.kind == "cylinder"
    assert s.radius == pytest.approx(500.0)
    assert s.size == pytest.approx((1000.0, 1000.0, 3000.0))
    assert s.base == pytest.approx((0.0, 0.0, 0.0))


def test_ifc_export_polygon_profile_roundtrip():
    m = _model()
    arch = CabArchive()
    names = cab_ifc.register_ifc_parts(
        m, cab_ifc.parse_ifc(SAMPLE_IFC_POLYGON), archive=arch)
    assert names == ["Slab-Poly"]
    out = cab_ifc.model_to_ifc(m)
    assert "IFCARBITRARYCLOSEDPROFILEDEF" in out
    assert "IFCPOLYLINE" in out
    solids = cab_ifc.parse_ifc(out)
    assert len(solids) == 1
    s = solids[0]
    assert s.kind == "polygon"
    assert s.size == pytest.approx((2000.0, 1500.0, 500.0))
    assert s.base == pytest.approx((0.0, 0.0, 0.0))
    # the 5-point footprint survives (closing point may duplicate)
    fp = {(round(x), round(y)) for x, y in s.points}
    assert {(0, 0), (2000, 0), (2000, 1000), (1000, 1500), (0, 1000)} \
        <= fp


def test_ifc_export_profile_type_mix():
    m = _model()
    SAMPLE_RECT = '''ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('r.ifc','2026-01-01T00:00:00',(''),(''),'x','x','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCCARTESIANPOINT((0.,0.,0.));
#2=IFCDIRECTION((0.,0.,1.));
#3=IFCDIRECTION((1.,0.,0.));
#4=IFCAXIS2PLACEMENT3D(#1,#2,#3);
#5=IFCLOCALPLACEMENT($,#4);
#6=IFCCARTESIANPOINT((0.,0.));
#7=IFCAXIS2PLACEMENT2D(#6,$);
#8=IFCRECTANGLEPROFILEDEF(.RECTANGLE.,$,#7,3.,0.2);
#9=IFCEXTRUDEDAREASOLID(#8,#4,#2,4.);
#10=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#9));
#11=IFCPRODUCTDEFINITIONSHAPE($,$,(#10));
#12=IFCWALLSTANDARDCASE('2O2Fr$t4X7Zf8NOew3FLOHV','Wall-1',$,#11,$,$,$,$);
ENDSEC;
END-ISO-10303-21;'''
    cab_ifc.register_ifc_parts(m, cab_ifc.parse_ifc(SAMPLE_RECT))
    cab_ifc.register_ifc_parts(m, cab_ifc.parse_ifc(SAMPLE_IFC_CIRCLE))
    out = cab_ifc.model_to_ifc(m)
    assert out.count("IFCRECTANGLEPROFILEDEF") == 1
    assert out.count("IFCCIRCLEPROFILEDEF") == 1
    assert out.count("IFCEXTRUDEDAREASOLID") == 2


# ------------------------------------------------- P3-3 STEP export branches

import cab_step_export  # noqa: E402


def test_step_export_strategy_branch_selection(monkeypatch):
    """三分支选择: CLI > OCC > none (递降)。"""
    monkeypatch.setattr(cab_step_export, "find_cad_cli",
                        lambda: "FreeCADCmd.exe")
    assert cab_step_export.step_export_strategy() == "cli"
    monkeypatch.setattr(cab_step_export, "find_cad_cli", lambda: None)
    monkeypatch.setattr(cab_step_export.cab_occ, "occ_available",
                        lambda: True)
    assert cab_step_export.step_export_strategy() == "occ"
    monkeypatch.setattr(cab_step_export.cab_occ, "occ_available",
                        lambda: False)
    assert cab_step_export.step_export_strategy() == "none"


def test_find_cad_cli_env_override(monkeypatch, tmp_path):
    fake = tmp_path / "fakecli.exe"
    fake.write_text("")
    monkeypatch.setenv("STPRE_STEP_CLI", str(fake))
    assert cab_step_export.find_cad_cli() == str(fake)


def test_step_export_b_level_declares(monkeypatch):
    """无可达后端 -> B 级定档 StepExportUnavailable (含稳定标记)。"""
    monkeypatch.setattr(cab_step_export, "find_cad_cli", lambda: None)
    monkeypatch.setattr(cab_step_export.cab_occ, "occ_available",
                        lambda: False)
    with pytest.raises(cab_step_export.StepExportUnavailable) as ei:
        cab_step_export.export_step_file(_model(), "model.step")
    msg = str(ei.value)
    assert cab_step_export._B_LEVEL_MARK in msg
    assert "STEP" in msg


def test_step_export_cli_branch_wiring(monkeypatch, tmp_path):
    """分支 (a): x_t 中转 + CAD CLI 调用链接线。"""
    calls = {}

    def fake_run(cli, xt, step):
        calls["cli"] = cli
        calls["xt"] = Path(xt).name
        Path(step).write_text("ISO-10303-21; fake-step", encoding="ascii")

    monkeypatch.setattr(cab_step_export, "find_cad_cli",
                        lambda: "FakeCli.exe")
    monkeypatch.setattr(cab_step_export, "_run_cli_convert", fake_run)
    monkeypatch.setattr(cab_step_export, "_write_xt",
                        lambda archive, tags, p: None)
    out = tmp_path / "out.step"
    cab_step_export.export_step_file(_model(), out)
    assert calls["cli"] == "FakeCli.exe"
    assert calls["xt"] == "model.x_t"
    assert out.read_text(encoding="ascii").startswith("ISO-10303-21;")


def test_metre_matrix_scales_translation_only():
    m = np.eye(4)
    m[:3, :3] = np.array([[0.0, -1.0, 0.0],
                          [1.0, 0.0, 0.0],
                          [0.0, 0.0, 1.0]])
    t4 = cab_step_export._metre_matrix((1000.0, 2000.0, 3000.0), m)
    assert t4[:3, 3] == pytest.approx((1.0, 2.0, 3.0))
    assert t4[:3, :3] == pytest.approx(m[:3, :3])
    assert t4[3, 3] == 1.0

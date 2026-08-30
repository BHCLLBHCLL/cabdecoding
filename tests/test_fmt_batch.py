"""§24 FMT batch: .bdf suffix fix, .xemt import, MDL round-trip reader."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
CAB = ROOT / "tests" / "ex4_e.cab"
XEMT = ROOT / "tests" / "ex4_e.xemt"


# ---------------------------------------------------------- FMT-1: .bdf

def _nas_text() -> str:
    # standard GRID with explicit CP field (real .bdf dialect)
    return "\n".join([
        "$ FMT-1 sample",
        "BEGIN BULK",
        "GRID,1,,-0.05,-0.05,0.0",
        "GRID,2,,0.05,-0.05,0.0",
        "GRID,3,,0.0,0.05,0.0",
        "PSHELL,1,1,0.001",
        "CTRIA3,1,1,1,2,3",
        "ENDDATA",
    ]) + "\n"


def test_bdf_suffix_imports_like_nas(tmp_path: Path):
    import cab_import
    src = tmp_path / "tri.bdf"
    src.write_text(_nas_text(), encoding="ascii")
    bodies, _raw, fmt = cab_import.import_file_with_payload(src)
    assert fmt == "stl"
    assert len(bodies) == 1
    pts = np.asarray(bodies[0].tess.points)
    tris = np.asarray(bodies[0].tess.triangles)
    assert len(tris) == 1
    # standard GRID coordinates survive the CP field (P3 offset bug fix)
    assert np.allclose(np.sort(pts[:, 0]), [-0.05, 0.0, 0.05])


def test_nas_import_still_works(tmp_path: Path):
    import cab_import
    src = tmp_path / "tri.nas"
    src.write_text(_nas_text(), encoding="ascii")
    bodies, _raw, _fmt = cab_import.import_file_with_payload(src)
    assert len(bodies) == 1


def test_nas_cp_less_legacy_dialect_still_works():
    import cab_import
    raw = ("BEGIN BULK\n"
           "GRID,1,0.,0.,0.\n"
           "GRID,2,1.,0.,0.\n"
           "GRID,3,1.,1.,0.\n"
           "CTRIA3,1,1,1,2,3\n"
           "ENDDATA\n").encode("ascii")
    pts, tris, _ = cab_import.parse_nas_bytes(raw)
    assert len(pts) == 3 and len(tris) == 1
    assert np.allclose(pts[1], (1.0, 0.0, 0.0))


# ---------------------------------------------------------- FMT-2: .xemt

def _cab_members():
    from cab_container import CabArchive
    arch = CabArchive.parse(CAB.read_bytes())
    arch.fill_member_data()
    return {m.name: m.data for m in arch.members}


def _project():
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    mm = _cab_members()
    model = StpreModel(parse_stpre(mm["ex4_e.xml"]))
    props = PropertyModel(parse_property(mm["_ex4_e_property.xml"]))
    return model, props


def test_parse_emt_official_sample():
    import xemt_export
    parsed = xemt_export.parse_emt(XEMT.read_bytes())
    assert parsed["version"] == 2023
    assert len(parsed["materials"]) == 7
    assert parsed["materials"][1] == "air(incompressible/20C)"
    assert parsed["fluid"]["name"] == "Domain(cuboid)"
    assert parsed["fluid"]["material"] == "air(incompressible/20C)"
    assert len(parsed["parts"]) == 32
    assert len(parsed["groups"]) == 1
    grp = parsed["groups"][0]
    assert grp["name"] == "cellular_phone" and grp["expand"] == "T"
    assert len(grp["parts"]) == 31
    by_name = {p["name"]: p for p in parsed["parts"]}
    assert by_name["button"]["material"] == "polycarbonate_resin(273K)"


def test_emt_export_parse_apply_roundtrip():
    """Clear every part material, re-apply from the parsed EMT, rebuild the
    EMT and require byte-identity with the original export."""
    import xemt_export
    model, props = _project()
    emt0 = xemt_export.build_emt(model, props)
    parsed = xemt_export.parse_emt(emt0.encode("utf-8"))
    # blank every material, then re-apply from the manifest
    for p in model.parts():
        model.set_part_property(p.name, "")
    summary = xemt_export.apply_emt(model, props, parsed)
    # EMT restates the region as part no=1 (skipped — the fluid entry
    # covers it); the 31 group members are all applied.
    assert summary["applied"] == len(parsed["parts"]) - 1
    assert summary["missing_parts"] == []
    assert summary["unknown_materials"] == []
    emt1 = xemt_export.build_emt(model, props)
    assert emt1 == emt0


def test_apply_emt_reports_missing_and_unknown():
    import xemt_export
    from cabxml import PropertyModel, StpreModel, new_property_bytes, \
        new_stpre_bytes, parse_property, parse_stpre
    model = StpreModel(parse_stpre(new_stpre_bytes("T")))
    model.add_part(name="A", kind="cube", attribute="solid")
    props = PropertyModel(parse_property(new_property_bytes()))
    # scenario 1: material absent from the property library -> reported,
    # nothing applied (unknown takes precedence over missing-part report)
    parsed = {
        "version": 2023,
        "materials": {1: "no_such_material"},
        "fluid": {"no": 1, "name": "Domain(cuboid)", "mat": 1,
                  "material": "no_such_material"},
        "parts": [
            {"no": 2, "name": "A", "mat": 1, "material": "no_such_material"},
            {"no": 3, "name": "ghost", "mat": 1,
             "material": "no_such_material"},
        ],
        "groups": [],
    }
    summary = xemt_export.apply_emt(model, props, parsed)
    assert summary["applied"] == 0
    assert "no_such_material" in summary["unknown_materials"]
    # scenario 2: known materials (ex4_e sample) but parts absent from the
    # model -> every sample part is reported missing
    model2 = StpreModel(parse_stpre(new_stpre_bytes("T")))
    model2.add_part(name="A", kind="cube", attribute="solid")
    _, props_ex4 = _project()
    sample = xemt_export.parse_emt(XEMT.read_bytes())
    summary2 = xemt_export.apply_emt(model2, props_ex4, sample)
    assert summary2["applied"] == 0
    assert "button" in summary2["missing_parts"]
    assert "cellular_phone" not in summary2["missing_parts"]


# ---------------------------------------------------------- FMT-3: MDL

def test_mdl_roundtrip_byte_identical(tmp_path: Path):
    import cab_import
    pts = np.array([[0.0, 0.0, 0.0], [0.01, 0.0, 0.0], [0.0, 0.01, 0.0],
                    [0.0, 0.0, 0.01]], dtype=np.float64)
    tris = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]],
                    dtype=np.int64)
    mdl = cab_import._tris_to_mdl_bytes(pts, tris, "tet")
    src = tmp_path / "tet.mdl"
    src.write_bytes(mdl)
    bodies, _raw, _fmt = cab_import.import_file_with_payload(src)
    assert len(bodies) == 1
    tess = bodies[0].tess
    assert len(tess.triangles) == 4
    # re-export from the re-imported mesh: geometry round-trips (the MDL
    # writer emits OBJ-compatible text — same contract on the way back)
    mdl2 = cab_import._tris_to_mdl_bytes(
        np.asarray(tess.points, dtype=np.float64),
        np.asarray(tess.triangles, dtype=np.int64), "tet")
    assert mdl2 == mdl


def test_mdl_non_obj_payload_declared_unsupported(tmp_path: Path):
    """B-level terminal state: native Cradle MDL parser is not bundled —
    non-OBJ-compatible MDL payloads must fail with the documented error."""
    import cab_import
    src = tmp_path / "native.mdl"
    src.write_bytes(b"MDL\r\nBINARYISH\r\n\x00\x01\x02")
    with pytest.raises(ValueError, match="OBJ-compatible"):
        cab_import.import_file_with_payload(src)


# ------------------------------------------------- FMT-2 GUI wiring
# NOTE: the CabViewer smoke test lives in test_gui.py — cab_gui/vtk must be
# imported at module level (collection time); importing it inside a running
# test function hard-crashes the process (exit 0x7F, no traceback).


# ------------------------------------------------- FMT-4: SAT export

def test_sat_export_b_level_without_cli(monkeypatch, tmp_path):
    """No free ACIS writer exists: without STPRE_SAT_CLI the export raises
    the documented B-level declaration."""
    import cab_step_export
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    monkeypatch.delenv("STPRE_SAT_CLI", raising=False)
    assert cab_step_export.sat_export_strategy() == "none"
    model = StpreModel(parse_stpre(new_stpre_bytes("T")))
    with pytest.raises(cab_step_export.SatExportUnavailable,
                       match="B-level"):
        cab_step_export.export_sat_file(model, tmp_path / "m.sat")


def test_sat_export_cli_branch(tmp_path, monkeypatch):
    """STPRE_SAT_CLI contract: <cli> <in.x_t> <out.sat> — the CLI receives
    a Parasolid transmit and its output lands at the target path."""
    import sys

    import cab_step_export
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre

    fake = tmp_path / "fake_cli.py"
    fake.write_text(
        "import sys\n"
        "assert sys.argv[1].lower().endswith('.x_t')\n"
        "open(sys.argv[2], 'w').write('ACIS SAT debug\n')\n",
        encoding="utf-8")
    monkeypatch.setenv("STPRE_SAT_CLI", f'{sys.executable} "{fake}"')
    # find_sat_cli handles a single executable name; emulate the wrapper by
    # pointing the env at a shim script via shell-free invocation is not
    # supported -> call the branch function with the strategy pre-resolved.
    monkeypatch.setattr(cab_step_export, "find_sat_cli",
                        lambda: sys.executable)
    calls = {}
    real_run = cab_step_export.subprocess.run

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        # the CLI contract is <cli> <in> <out>; emulate our fake writer
        open(cmd[2], "w").write("ACIS SAT debug\n")
        class R:  # noqa: D401
            returncode = 0
        return R()

    monkeypatch.setattr(cab_step_export.subprocess, "run", fake_run)
    model = StpreModel(parse_stpre(new_stpre_bytes("T")))
    from cab_container import CabArchive
    arch = CabArchive.parse(CAB.read_bytes())
    arch.fill_member_data()
    out = cab_step_export.export_sat_file(
        model, tmp_path / "m.sat", archive=arch)
    assert out.is_file() and out.read_text().startswith("ACIS")
    cmd = calls["cmd"]
    assert cmd[0] == sys.executable and cmd[1].endswith(".x_t") \
        and cmd[2].endswith(".sat")


# ------------------------------------------------- FMT-5: CGNS declaration

def test_cgns_declared_non_benchmark():
    """FMT-5 B-level: CGNS is not an STpre preprocessor capability (the
    Pre_eng manual has no CGNS page) — import stays unsupported."""
    import cab_import
    with pytest.raises(ValueError, match="unsupported"):
        cab_import.import_file("model.cgns")

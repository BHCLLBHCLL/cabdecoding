"""M1: x_t import tests (cab_import + cabxml body_files/add_part)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from cab_container import CabArchive
from cabxml import (
    PropertyModel, StpreModel, new_property_bytes, new_stpre_bytes,
    parse_property, parse_stpre,
)

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"

cab_import = pytest.importorskip("cab_import")

try:
    import cab_gui as _cab_gui
    _HAS_GUI_DEPS = _cab_gui._HAS_GUI_DEPS
except Exception:
    _HAS_GUI_DEPS = False


def _box_archive() -> CabArchive:
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    return archive


@pytest.mark.skipif(not cab_import.available(),
                    reason="Cradle pskernel.dll not installed")
def test_import_xt_box():
    bodies = cab_import.import_xt_file(BOX_XT)
    assert len(bodies) == 1
    box = bodies[0]
    assert box.name == "box"
    assert len(box.tess.points) == 8
    assert len(box.tess.triangles) == 12


def test_add_member_and_register_parts(tmp_path):
    archive = _box_archive()
    members_before = len(archive.members)
    xt = BOX_XT.read_bytes()
    member = cab_import.add_xt_member(archive, xt)
    assert len(archive.members) == members_before + 1
    assert member.data == xt
    assert member.name.endswith(".x_t")

    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    assert model.add_body_file(member.name) is True
    assert model.add_body_file(member.name) is False  # idempotent
    assert member.name in model.body_files()

    bodies = [cab_import.ImportedBody(name="imported_cube", tag=1, tess=None)]
    added = cab_import.register_parts(model, bodies)
    assert added == ["imported_cube"]
    assert model.find_part("imported_cube") is not None
    # serialized XML must stay parseable and keep the part
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    assert reparsed.find_part("imported_cube") is not None
    assert reparsed.body_files() == model.body_files()

    # archive rebuild must contain the new member and round-trip
    xml_member.data = model.doc.serialize()
    out = archive.to_bytes(preserve_source_blocks=False)
    again = CabArchive.parse(out)
    again.fill_member_data()
    names = [m.name for m in again.members]
    assert member.name in names
    assert len(again.members) == members_before + 1


@pytest.mark.skipif(not cab_import.available() or not _HAS_GUI_DEPS,
                    reason="pskernel or PyQt5/vtk not available")
def test_gui_load_multiple_xt_members(tmp_path, qapp):
    """CabViewer must tessellate every .x_t member (imported parts survive)."""
    archive = _box_archive()
    member = cab_import.add_xt_member(archive, BOX_XT.read_bytes())
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    model.add_body_file(member.name)
    bodies = cab_import.import_xt_file(BOX_XT)
    cab_import.register_parts(model, bodies)
    xml_member.data = model.doc.serialize()
    cab_path = tmp_path / "multi_xt.cab"
    cab_path.write_bytes(archive.to_bytes(preserve_source_blocks=False))

    viewer = _cab_gui.CabViewer(enable_3d=False)
    assert viewer.load(str(cab_path)) is True
    # both members tessellated: original box + imported cube (same name ->
    # two TessParts with identical geometry)
    assert viewer._cad_meshes is not None
    names = [p.name for p in viewer._cad_meshes]
    assert names.count("box") >= 2
    # tree contains the imported part entry
    assert viewer.model.find_part("box") is not None


def test_new_project_templates_parse():
    model = StpreModel(parse_stpre(new_stpre_bytes("demo")))
    assert model.project_name == "demo"
    assert model.body_files() == []
    assert model.analysis_region() is None
    props = PropertyModel(parse_property(new_property_bytes()))
    assert "air(incompressible/20C)" in props.material_names()


@pytest.mark.skipif(not cab_import.available() or not _HAS_GUI_DEPS,
                    reason="pskernel or PyQt5/vtk not available")
def test_new_project_import_save_reload(tmp_path, qapp):
    """Fresh GUI (no path) must allow import -> save -> reload."""
    viewer = _cab_gui.CabViewer(enable_3d=False)
    assert viewer.model is not None
    assert len(viewer.archive.members) == 2
    assert viewer.model.body_files() == []
    # simulate File -> Import for box.x_t
    raw = BOX_XT.read_bytes()
    bodies = cab_import.import_xt_file(BOX_XT)
    member = cab_import.add_xt_member(viewer.archive, raw)
    assert viewer.model.add_body_file(member.name) is True
    cab_import.register_parts(viewer.model, bodies)
    viewer._cad_meshes = [b.tess for b in bodies]
    viewer.tree_view.populate(viewer.model, viewer.archive.members)
    out = tmp_path / "new_project.cab"
    assert viewer._rebuild_to(str(out)) is True
    viewer2 = _cab_gui.CabViewer(enable_3d=False)
    assert viewer2.load(str(out)) is True
    assert viewer2.model.find_part("box") is not None
    assert len(viewer2._cad_meshes or []) == 1


def _cube_stl_text() -> bytes:
    v = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
         (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)]
    faces = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ]
    out = ["solid cube"]
    for a, b, c in faces:
        out.append("  facet normal 0 0 0")
        out.append("    outer loop")
        for i in (a, b, c):
            out.append(f"      vertex {v[i][0]} {v[i][1]} {v[i][2]}")
        out.append("    endloop")
        out.append("  endfacet")
    out.append("endsolid cube")
    return ("\n".join(out) + "\n").encode()


def test_parse_stl_text():
    import cab_import
    pts, tris = cab_import.parse_stl_bytes(_cube_stl_text())
    assert len(pts) == 8 and len(tris) == 12


def test_import_stl_member_roundtrip(tmp_path, qapp):
    import cab_import
    viewer = _cab_gui.CabViewer(enable_3d=False)
    raw = _cube_stl_text()
    bodies = cab_import.import_stl_bytes(raw, name="cube_stl")
    assert len(bodies) == 1 and len(bodies[0].tess.triangles) == 12
    member = cab_import.add_stl_member(
        viewer.archive, raw, name="cube_stl.stl")
    assert member.name == "cube_stl.stl"
    cab_import.register_parts(viewer.model, bodies, kind="polygon")
    viewer._cad_meshes = [b.tess for b in bodies]
    out = tmp_path / "stl_proj.cab"
    assert viewer._rebuild_to(str(out)) is True
    viewer2 = _cab_gui.CabViewer(enable_3d=False)
    assert viewer2.load(str(out)) is True
    assert viewer2.model.find_part("cube_stl") is not None
    names = [p.name for p in (viewer2._cad_meshes or [])]
    assert "cube_stl" in names


def test_import_file_dispatch_and_occ_missing(tmp_path):
    import cab_import
    # STL routes natively
    p = tmp_path / "part.stl"
    p.write_bytes(_cube_stl_text())
    bodies, raw, fmt = cab_import.import_file_with_payload(p)
    assert fmt == "stl" and len(bodies) == 1
    # STEP/SAT require OpenCascade (no external GUI converter)
    sp = tmp_path / "part.step"
    sp.write_text("ISO-10303-21;", encoding="ascii")
    with pytest.raises(RuntimeError, match="OpenCascade"):
        cab_import.import_file(sp)
    sat = tmp_path / "part.sat"
    sat.write_text("ACIS", encoding="ascii")
    with pytest.raises(RuntimeError, match="OpenCascade"):
        cab_import.import_file(sat)


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app

"""Edit menu completeness + STpre dialog smoke tests."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"

STPRE_EDIT_ITEMS = [
    "Undo", "Redo",
    "Group", "Deletion of Parts", "Parts Conversion",
    "Reconstruct of Part Facet", "Flipping Part Face",
    "Part Face Paneling", "Sweep Part Face", "Alignment",
    "Place Part", "Mirror Copy Parts", "Connected Region",
    "Boolean Operation", "Shape change by Boolean operation",
    "Cutting", "Edit Solid", "Part Simplification",
    "Shape Simplification", "Convert Facets to Solid",
    "FEM Conversion", "Wrapping",
    "Reset Computational Domain", "Edit Wiring on Board",
    "Placement of Image",
]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _viewer(qapp):
    import cab_gui
    from cab_container import CabArchive
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    prop_name = next(n for n in members if n.endswith("_property.xml"))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.archive = archive
    viewer.model = StpreModel(parse_stpre(members[xml_name]))
    viewer.props = PropertyModel(parse_property(members[prop_name]))
    viewer._cad_meshes = []
    return viewer


def test_edit_menu_matches_stpre(qapp):
    viewer = _viewer(qapp)
    edit = None
    for act in viewer.menuBar().actions():
        if "Edit" in act.text():
            edit = act.menu()
            break
    assert edit is not None
    texts = [a.text() for a in edit.actions() if a.text()]
    assert texts == STPRE_EDIT_ITEMS


def test_element_layer_auto_enabled_after_meshing(qapp):
    # R: Meshing turns on Drawing->Element so the structured mesh is
    # immediately visible (mirrors gridding auto-enabling Drawing->Mesh).
    viewer = _viewer(qapp)
    cb = viewer.control.layer_checks.get("element")
    assert cb is not None
    cb.blockSignals(True)
    cb.setChecked(False)
    cb.blockSignals(False)
    viewer._enable_element_layer_after_meshing()
    assert cb.isChecked()

def test_reset_domain_dialog_applies_defaults(qapp):
    import cab_edit_dialogs
    viewer = _viewer(qapp)
    dlg = cab_edit_dialogs.ResetComputationalDomainDialog(viewer.model)
    dlg.chk_update.setChecked(False)
    dlg.chk_grav.setChecked(True)
    dlg.grav_acc.setValue(9.81)
    dlg.grav_dir.setCurrentText("-Z")
    dlg.chk_temp.setChecked(True)
    dlg.temp.setValue(25.0)
    dlg.chk_emis.setChecked(True)
    dlg.emis.setValue(0.8)
    dlg._ok()
    assert dlg.applied
    assert abs(float(viewer.model.project_value(
        "ambient_temperature", "0")) - 25.0) < 1e-6
    assert abs(float(viewer.model.project_value(
        "default_emissivity", "0")) - 0.8) < 1e-6


def test_boolean_dialog_note_updated(qapp):
    """Boolean dialog must advertise PK-first + fallback, not stale CSG-only."""
    import cab_edit_dialogs
    from PyQt5.QtWidgets import QLabel
    viewer = _viewer(qapp)
    dlg = cab_edit_dialogs.BooleanOperationDialog(
        viewer.model, [], parent=None)
    texts = " ".join(w.text() for w in dlg.findChildren(QLabel))
    assert "PK_BODY_boolean_2" in texts
    assert "MVP: tessellation CSG" not in texts
    dlg.close()


def test_mirror_copy_and_align_ops(qapp):
    import cab_edit_ops as ops
    from cab_parts import PrimitivePart, cube_tess, register_primitive

    viewer = _viewer(qapp)
    model = viewer.model
    register_primitive(
        model, name="box_a", kind="cube",
        params={"base": (-10, -10, -10), "size": (20, 20, 20)})
    register_primitive(
        model, name="box_b", kind="cube",
        params={"base": (50, -10, -10), "size": (20, 20, 20)})
    ta = cube_tess((-10, -10, -10), (20, 20, 20))
    tb = cube_tess((50, -10, -10), (20, 20, 20))
    tess = [
        PrimitivePart("box_a", ta.points, ta.triangles),
        PrimitivePart("box_b", tb.points, tb.triangles),
    ]
    created = ops.mirror_copy_parts(model, ["box_a"], "X", 0.0)
    assert created and model.find_part(created[0]) is not None
    assert ops.align_parts(
        model, "box_a", "box_b", "X", "Minimum", tess)


def test_fem_conversion_dialog(qapp, monkeypatch):
    """P1-⑤: FEM Conversion persists element size / leave edges / contact."""
    import cab_edit_dialogs
    from cabxml import _first
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    viewer = _viewer(qapp)
    model = viewer.model
    model.add_part(name="fem_p")
    el0 = model.find_part("fem_p")
    from xml.etree.ElementTree import SubElement
    for tag, val in (("base", "0,0,0"), ("size", "10,10,10")):
        c = _first(el0, tag)
        if c is None:
            c = SubElement(el0, tag)
        c.text = val
    dlg = cab_edit_dialogs.FEMConversionDialog(model)
    dlg.target.setCurrentText("fem_p")
    dlg.elem_size.setValue(2.5)
    dlg.leave.setChecked(True)
    dlg._exec()
    # R12: conversion keeps the source part and adds a real mesh_body FEM
    # part (R9 CreateFEM evidence), storing the intent params on source.
    el = model.find_part("fem_p")
    assert el is not None and el.attrib.get("type") == "body"
    assert (_first(el, "fem_element_size").text or "").strip() == "2.5"
    assert (_first(el, "fem_leave_edges").text or "").strip() == "T"
    assert model.part_fem("fem_p_fem") is not None
    # reload restores the values
    dlg2 = cab_edit_dialogs.FEMConversionDialog(model)
    dlg2.target.setCurrentText("fem_p")
    dlg2._load()
    assert dlg2.elem_size.value() == pytest.approx(2.5)
    assert dlg2.leave.isChecked()
    # P1-5: FEM mesh size estimate from the part tessellation
    import numpy as np
    class _M:
        name = "fem_p"
        points = np.array([[0.0, 0, 0], [0.01, 0, 0], [0, 0.01, 0]])
        triangles = np.array([[0, 1, 2]], int)
    dlg3 = cab_edit_dialogs.FEMConversionDialog(
        model, cad_meshes=[_M()])
    dlg3.target.setCurrentText("fem_p")
    dlg3.elem_size.setValue(0.001)
    dlg3._refresh_estimate()
    assert "elements" in dlg3.estimate.text()
    assert "nodes" in dlg3.estimate.text()
    assert "Warning" not in dlg3.estimate.text()
    dlg3.elem_size.setValue(0.1)
    dlg3._refresh_estimate()
    assert "Warning" in dlg3.estimate.text()
    viewer.close()


def test_group_dialog_create_and_ungroup(qapp):
    import cab_edit_dialogs
    import cab_edit_ops as ops

    viewer = _viewer(qapp)
    model = viewer.model
    model.add_part(name="g_p1")
    model.add_part(name="g_p2")
    dlg = cab_edit_dialogs.GroupDialog(model)
    dlg.rb_name.setChecked(True)
    dlg.group_edit.setText("edit_grp")
    for i in range(dlg.part_list.count()):
        if dlg.part_list.item(i).text() in ("g_p1", "g_p2"):
            dlg.part_list.item(i).setSelected(True)
    dlg._on_action()
    assert dlg.applied
    assert "edit_grp" in ops.group_names(model)
    dlg.rb_ung.setChecked(True)
    dlg._sync_action()
    dlg.group_edit.setText("edit_grp")
    dlg._on_action()
    assert "edit_grp" not in ops.group_names(model)

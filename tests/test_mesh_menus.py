"""M6: [Mesh] menu dialogs — checking parts interferences / editing mesh /
showing element cross-section / checking S-File, plus menu order."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

import cab_grid
import cab_mesh
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _box_model() -> StpreModel:
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    return StpreModel(parse_stpre(xml_member.data))


def _meshed_model() -> StpreModel:
    model = _box_model()
    axes = cab_grid.build_axes(
        {}, cab_grid.GridSpec(domain_min=(-50, -50, -50),
                              domain_max=(50, 50, 50),
                              method="rough_and_detail"))[1]
    model.set_mesh(axes, domain_min=(-50, -50, -50),
                   domain_max=(50, 50, 50), unit="mm")
    return model


@pytest.fixture()
def pieces(qapp):
    import cab_gui
    model = _meshed_model()
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = []
    return model, viewer


def test_mesh_menu_order(qapp):
    """Mesh menu matches the STpre [Mesh] menu order."""
    import cab_gui
    viewer = cab_gui.CabViewer(enable_3d=False)
    mesh_menu = None
    for a in viewer.menuBar().actions():
        if "Mesh" in a.text():
            mesh_menu = a.menu()
            break
    assert mesh_menu is not None
    labels = [a.text() for a in mesh_menu.actions() if a.text()]
    assert labels == [
        "Gridding…", "Meshing", "Checking Parts Interferences",
        "Editing Mesh…", "Showing Element Cross-Section…",
        "Checking S-File…",
        "Gridding/Meshing via STpre API",
    ]
    viewer.close()


def test_interference_dialog(pieces):
    import cab_dialogs
    model, viewer = pieces
    ni = len(model.mesh_axes()["x"]) - 1
    cab_mesh.apply_elements(
        model, "Domain(cuboid)", (1, ni, 1, ni, 1, ni),
        {"a": [(1, 5, 1, 5, 1, 5)], "b": [(4, 9, 4, 9, 4, 9)]})
    dlg = cab_dialogs.InterferenceDialog(model, viewer)
    assert dlg.windowTitle() == "Checking Parts Interferences"
    assert dlg.tree.topLevelItemCount() == 1
    it = dlg.tree.topLevelItem(0)
    assert (it.text(0), it.text(1), it.text(2)) == ("a", "b", "Interference")
    # Separation only filter hides the interference
    dlg.chk_sep_only.setChecked(True)
    assert dlg.tree.topLevelItemCount() == 0
    # Reconstruct clips b; the residual boxes still share a face -> Contact
    dlg.chk_sep_only.setChecked(False)
    dlg._reconstruct()
    assert dlg.tree.topLevelItemCount() == 1
    it = dlg.tree.topLevelItem(0)
    assert (it.text(0), it.text(1), it.text(2)) == ("a", "b", "Contact")
    dlg.close()


def test_edit_mesh_dialog(pieces):
    import cab_dialogs
    model, viewer = pieces
    ni = len(model.mesh_axes()["x"]) - 1
    cab_mesh.apply_elements(
        model, "Domain(cuboid)", (1, ni, 1, ni, 1, ni),
        {"box": [(1, ni, 1, ni, 1, ni)]})
    dlg = cab_dialogs.EditMeshDialog(model, viewer)
    assert dlg.windowTitle() == "Editing Mesh"
    assert dlg.part_combo.currentText() == "box"
    # default selection: the whole first x layer (I side, layer 1)
    cells = dlg._selected_cells()
    assert len(cells) == ni ** 2
    # -> Ineffective on the first x layer removes ni*ni cells
    before = int(cab_mesh.cell_mask_from_boxes(
        ni, ni, ni, model.part_boxes("box")).sum())
    dlg._execute()
    after = int(cab_mesh.cell_mask_from_boxes(
        ni, ni, ni, model.part_boxes("box")).sum())
    assert after == before - ni * ni
    dlg.close()


def test_section_dialog(pieces):
    import cab_dialogs
    model, viewer = pieces
    ni = len(model.mesh_axes()["x"]) - 1
    cab_mesh.apply_elements(
        model, "Domain(cuboid)", (1, ni, 1, ni, 1, ni),
        {"box": [(2, 5, 2, 5, 2, 5)]})
    shown = []
    viewer._show_section = lambda pd, colors: shown.append(pd)
    dlg = cab_dialogs.SectionDialog(model, viewer)
    assert dlg.windowTitle() == "Show Element Cross-Section"
    assert dlg.slider.maximum() == ni
    assert shown, "slider render should call _show_section"
    # switching mode re-renders
    dlg.mode["fluid_only"].setChecked(True)
    assert len(shown) >= 2
    dlg.close()


def test_check_sfile_dialog(pieces):
    import cab_dialogs
    model, viewer = pieces
    dlg = cab_dialogs.SFileCheckDialog(model, viewer)
    assert dlg.windowTitle() == "Checking S File"
    assert dlg.tree.topLevelItemCount() >= 1
    # first part row is checkable; unchecking hides the part
    item = dlg.tree.topLevelItem(0)
    assert item.checkState(0) == 2  # Qt.Checked
    item.setCheckState(0, 0)        # Qt.Unchecked
    dlg._on_toggled(item, 0)
    assert item.text(0) in viewer._hidden_parts
    dlg.close()


def test_gui_mesh_slots_route(qapp, monkeypatch):
    """The four new Mesh menu actions open their dialogs."""
    import cab_gui
    import cab_dialogs
    model = _meshed_model()
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = []
    calls = []
    monkeypatch.setattr(cab_dialogs.InterferenceDialog, "exec_",
                        lambda self: calls.append("interference"))
    monkeypatch.setattr(cab_dialogs.EditMeshDialog, "exec_",
                        lambda self: calls.append("editmesh"))
    monkeypatch.setattr(cab_dialogs.SectionDialog, "exec_",
                        lambda self: calls.append("section"))
    monkeypatch.setattr(cab_dialogs.SFileCheckDialog, "exec_",
                        lambda self: calls.append("sfile"))
    viewer._interference_dialog()
    viewer._edit_mesh_dialog()
    viewer._section_dialog()
    viewer._check_sfile_dialog()
    assert calls == ["interference", "editmesh", "section", "sfile"]
    viewer.close()

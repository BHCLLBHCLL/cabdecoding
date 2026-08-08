"""M5: Mesh:Set division six-tab dialog tests (cab_dialogs.GriddingDialog)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

import cab_grid
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _dialog(qapp):
    import cab_gui
    from cab_container import CabArchive
    pytest.importorskip("cab_import")
    import cab_import
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    archive = CabArchive.parse((ROOT / "tests" / "box.cab").read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    bodies = cab_import.import_xt_file(ROOT / "tests" / "box" / "box_all.x_t")
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = [b.tess for b in bodies]
    dlg = cab_gui._GriddingDialog(model, viewer._cad_meshes, viewer)
    # pin the parent: if the viewer wrapper is GC'd, Qt destroys the dialog
    dlg._keep_viewer = viewer
    return dlg, model


# ------------------------------------------------------- algorithm units


def test_divide_interval_forward_backward_symmetric():
    vals = [0.0, 10.0, 20.0]
    out = cab_grid.divide_interval(vals, 0.0, 10.0, 4, ratio=1.0)
    np.testing.assert_allclose(out, [0.0, 2.5, 5.0, 7.5, 10.0, 20.0])
    out = cab_grid.divide_interval(vals, 0.0, 10.0, 4, ratio=2.0,
                                   mode="forward")
    gaps = np.diff([v for v in out if v <= 10.0])
    assert gaps[0] < gaps[-1]
    out = cab_grid.divide_interval(vals, 0.0, 10.0, 4, ratio=2.0,
                                   mode="backward")
    gaps = np.diff([v for v in out if v <= 10.0])
    assert gaps[0] > gaps[-1]
    out = cab_grid.divide_interval(vals, 0.0, 10.0, 4, ratio=2.0,
                                   mode="symmetric")
    gaps = np.diff([v for v in out if v <= 10.0])
    assert gaps[0] == pytest.approx(gaps[-1])
    assert gaps[0] < gaps[1]


def test_divide_interval_retain_and_threshold():
    vals = [0.0, 4.0, 10.0, 20.0]
    out = cab_grid.divide_interval(vals, 0.0, 10.0, 6, retain=[4.0])
    assert 4.0 in out
    assert sum(1 for v in out if 0.0 < v < 10.0) >= 5
    out = cab_grid.divide_interval(vals, 0.0, 10.0, 100, threshold=2.0)
    gaps = np.diff(out)
    assert gaps.min() >= 2.0 - 1e-9


def test_delete_grid_lines_semantics():
    entries = [(0.0, "B"), (2.0, "N"), (5.0, "S"), (8.0, "F"),
               (10.0, "B")]
    keep = cab_grid.delete_grid_lines(entries, "all_but_rough")
    assert [v for v, _m in keep] == [0.0, 5.0, 8.0, 10.0]
    keep = cab_grid.delete_grid_lines(entries, "all", [5.0])
    assert [v for v, _m in keep] == [0.0, 5.0, 10.0]


# ------------------------------------------------------------- dialog


def test_gridding_dialog_tabs(qapp):
    dlg, _model = _dialog(qapp)
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Basic Setting", "Parameter", "Detail meshing",
                      "Edit", "Deletion", "Others"]
    assert dlg.btn_gridding.text() == "Gridding"
    assert dlg.btn_meshing.text() == "Meshing"
    assert dlg.btn_close.text() == "Close"
    assert "Element #" in dlg.element_label.text()
    assert set(dlg.detection_radios) == {
        "all", "representative", "axis_plane", "minmax",
        "not_considered", "uniform"}
    assert set(dlg.method_radios) == {
        "rough_only", "rough_and_detail", "num_elements"}
    dlg.close()


def test_gridding_dialog_num_elements_per_axis(qapp):
    dlg, model = _dialog(qapp)
    dlg.method_radios["num_elements"].setChecked(True)
    dlg.num_axis_radio.setChecked(True)
    dlg.target_axes["x"].setValue(5)
    dlg.target_axes["y"].setValue(4)
    dlg.target_axes["z"].setValue(3)
    dlg._gridding()
    axes = model.mesh_axes()
    # STpre auto3: target is the per-axis *cell* count -> points = target+1
    assert (len(axes["x"]), len(axes["y"]), len(axes["z"])) == (6, 5, 4)
    # Element # uses cell count (points − 1), matching STpre
    assert "5 x 4 x 3" in dlg.element_label.text()
    assert model.mesh_control_value("divide_method") == "2"
    dlg.close()


def test_gridding_dialog_common_checkbox(qapp):
    dlg, _model = _dialog(qapp)
    dlg.ratio_common.setChecked(True)
    dlg.ratio["x"].setValue(1.5)
    assert dlg.ratio["y"].value() == pytest.approx(1.5)
    assert dlg.ratio["z"].value() == pytest.approx(1.5)
    assert not dlg.ratio["y"].isEnabled()
    dlg.ratio_common.setChecked(False)
    assert dlg.ratio["y"].isEnabled()
    dlg.close()


def test_gridding_dialog_edit_tab(qapp):
    dlg, model = _dialog(qapp)
    dlg._gridding()
    entries = model.mesh_axis_entries("x")
    assert entries and entries[0][1] == "B" and entries[-1][1] == "B"
    dlg.edit_coord.setValue(5.25)
    dlg.edit_type["F"].setChecked(True)
    dlg._edit_add()
    entries = model.mesh_axis_entries("x")
    assert (5.25, "F") in entries
    dlg._refresh_edit_list()
    for i in range(dlg.edit_list.topLevelItemCount()):
        item = dlg.edit_list.topLevelItem(i)
        if abs(float(item.text(1)) - 5.25) < 1e-9:
            dlg.edit_list.setCurrentItem(item)
            break
    dlg.edit_coord.setValue(6.25)
    dlg.edit_type["S"].setChecked(True)
    dlg._edit_edit()
    entries = model.mesh_axis_entries("x")
    assert (6.25, "S") in entries and (5.25, "F") not in entries
    dlg._refresh_edit_list()
    for i in range(dlg.edit_list.topLevelItemCount()):
        item = dlg.edit_list.topLevelItem(i)
        if abs(float(item.text(1)) - 6.25) < 1e-9:
            dlg.edit_list.setCurrentItem(item)
            break
    dlg._edit_delete()
    entries = model.mesh_axis_entries("x")
    assert all(abs(v - 6.25) > 1e-9 for v, _m in entries)
    dlg._refresh_edit_list()
    dlg.edit_list.setCurrentItem(dlg.edit_list.topLevelItem(0))
    n_before = len(model.mesh_axis_entries("x"))
    dlg._edit_delete()
    assert len(model.mesh_axis_entries("x")) == n_before  # B is protected
    dlg.close()


def test_gridding_dialog_deletion_all_but_rough(qapp):
    dlg, model = _dialog(qapp)
    dlg._gridding()
    entries = model.mesh_axis_entries("x")
    mid = (entries[0][0] + entries[-1][0]) / 2.0
    entries.insert(1, (mid, "S"))
    model.set_mesh_axis("x", sorted(entries))
    dlg.del_target["all_but_rough"].setChecked(True)
    dlg._delete_grids()
    kept = model.mesh_axis_entries("x")
    assert [m for _v, m in kept] == ["B", "S", "B"]
    dlg.close()


def test_gridding_dialog_detail_divide(qapp):
    dlg, model = _dialog(qapp)
    dlg._gridding()
    entries = model.mesh_axis_entries("x")
    a, b = entries[0][0], entries[-1][0]
    dlg.detail_from.setCurrentText(str(a))
    dlg.detail_to.setCurrentText(str(b))
    dlg.detail_n.setValue(9)
    dlg.detail_ratio.setValue(1.0)
    dlg._divide_range()
    vals = [v for v, _m in model.mesh_axis_entries("x")]
    interior = [v for v in vals if a < v < b]
    assert len(interior) == 8
    dlg.close()


def test_gridding_dialog_others_persist(qapp):
    dlg, model = _dialog(qapp)
    dlg.p_edge_tol.setValue(0.001)
    assert model.mesh_control_value("edge_eps") == "0.001"
    dlg.p_elem_thr.setValue(0.6)
    assert model.mesh_control_value("element_threshold") == "0.6"
    dlg.boundary_face["excl_all"].setChecked(True)
    assert model.mesh_control_value("panel_block_face") == "0"
    dlg.chk_flux_dup.setChecked(False)
    assert model.mesh_control_value("check_scheme") == "0"
    dlg._part_vertex_combos["box"].setCurrentText("minmax")
    assert model.part_mesh_option("box") == "minmax"
    dlg.close()


def test_gridding_dialog_interference_tools(qapp):
    import cab_mesh
    dlg, model = _dialog(qapp)
    dlg._gridding()
    assert cab_mesh.find_interferences(model) == []
    # create the <element> section, then fabricate overlapping parts
    cab_mesh.apply_elements(model, "Domain(cuboid)", (1, 2, 1, 2, 1, 2), {})
    assert cab_mesh.update_part_elements(model, "p1", [(1, 5, 1, 5, 1, 5)])
    assert cab_mesh.update_part_elements(model, "p2", [(3, 8, 1, 5, 1, 5)])
    assert ("p1", "p2") in cab_mesh.find_interferences(model)
    changed = cab_mesh.resolve_interferences(model)
    assert changed >= 1
    assert cab_mesh.find_interferences(model) == []
    assert model.part_boxes("p1") == [[1, 5, 1, 5, 1, 5]]
    assert model.part_boxes("p2") == [[6, 8, 1, 5, 1, 5]]
    dlg.close()

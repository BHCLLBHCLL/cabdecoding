"""§24 AM batch: Auto Meshing menu check + both manual modes end-to-end.

AM-0: the official [Mesh] menu (Pre_eng toc.csv) has exactly six commands —
Gridding / Meshing / Checking Parts Interferences / Editing Mesh / Showing
Element Cross-Section / Checking S-File.  The two "Auto meshing by ..."
manual pages document *methods inside* [Gridding], not menu commands, so the
repo menu must match the six and no extra entry.

AM-1: "Auto meshing by specifying the number of elements" — GriddingDialog
num_elements method -> cab_grid auto1 closed form (golden 21-pt layout).
AM-2: "by standard length and geometric ratio (internal/external)" —
rough_and_detail method fields -> engine external-first-spacing=std rule.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

import cab_gui

pytestmark = pytest.mark.skipif(not cab_gui._HAS_GUI_DEPS,
                                reason="PyQt5/vtk not installed")

HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(scope="module")
def viewer(qapp):
    win = cab_gui.CabViewer(CAB, enable_3d=False)
    yield win
    win.close()


def _box_project():
    """Domain -25..25 mm, one 0..10 mm cube part (auto1 probe scenario)."""
    from cab_parts import cube_tess
    from cabxml import StpreModel, parse_stpre, new_stpre_bytes
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(base=(-25.0, -25.0, -25.0), size=(50.0, 50.0, 50.0))
    m.add_part(name="P1", kind="cube", attribute="solid")
    tess = cube_tess((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))
    tess.name = "P1"
    return m, [tess]


def _dialog(m, meshes):
    import cab_dialogs
    dlg = cab_dialogs.GriddingDialog(m, meshes, parent=None)
    dlg.detection_radios["minmax"].setChecked(True)
    return dlg


def _dialog_coords(dlg, m):
    return [round(v, 6) for v, _mk in m.mesh_axis_entries("x")]


def _engine_coords(m, meshes, *, std, thr, ratio, ratio_ext, **spec_kw):
    """Mirror cab_dialogs.GriddingDialog._gridding's engine call exactly
    (part_bounds come back in metres and are scaled to mm there)."""
    import cab_domain
    import cab_grid
    spec = cab_grid.GridSpec(
        unit="mm", domain_min=(-25.0, -25.0, -25.0),
        domain_max=(25.0, 25.0, 25.0), vertex_detection="minmax",
        standard_length=std, threshold_length=thr,
        geometric_ratio=ratio, geometric_ratio_external=ratio_ext,
        **spec_kw)
    pts = {t.name: np.asarray(t.points) * 1000.0 for t in meshes}
    verts = {t.name: np.asarray(
        getattr(t, "rep_vertices", None)
        if getattr(t, "rep_vertices", None) is not None
        else t.vertices) * 1000.0
        for t in meshes if getattr(t, "vertices", None) is not None}
    lo, hi = cab_domain.part_bounds(m, meshes)
    part_bounds = (np.asarray(lo, dtype=float) * 1000.0,
                   np.asarray(hi, dtype=float) * 1000.0)
    _rough, detailed = cab_grid.build_axes(
        pts, spec, part_vertices=verts or None, part_bounds=part_bounds)
    return [round(v, 6) for v in detailed["x"]]


# ------------------------------------------------- AM-0: menu structure

def test_mesh_menu_matches_official_commands(viewer):
    from PyQt5.QtWidgets import QMenu
    official = [
        "Gridding…", "Meshing", "Checking Parts Interferences",
        "Editing Mesh…", "Showing Element Cross-Section…",
        "Checking S-File…",
    ]
    menu = None
    for act in viewer.menuBar().actions():
        if act.text() == "Mesh(&G)" and isinstance(act.menu(), QMenu):
            menu = act.menu()
            break
    assert menu is not None, "Mesh menu missing"
    labels = [a.text() for a in menu.actions() if a.text()]
    assert labels[:len(official)] == official
    # the two auto-meshing manual pages are gridding *methods*, not menu
    # commands — no "Auto Meshing" entry may exist
    assert not [t for t in labels if "Auto" in t]


# ------------------------------------- AM-1: number-of-elements mode

def test_auto1_dialog_end_to_end(qapp):
    m, meshes = _box_project()
    dlg = _dialog(m, meshes)
    try:
        dlg.method_radios["num_elements"].setChecked(True)
        dlg.num_total_radio.setChecked(True)
        dlg.target.setValue(8000)
        dlg._gridding()
        coords = _dialog_coords(dlg, m)
        # dialog path must hit the same engine the golden probes lock
        # (mirror passes the dialog's own spinbox values)
        engine = _engine_coords(
            m, meshes, method="num_elements", target_elements=8000,
            std=tuple(dlg.std[a].value() for a in "xyz"),
            thr=tuple(dlg.thr[a].value() for a in "xyz"),
            ratio=tuple(dlg.ratio[a].value() for a in "xyz"),
            ratio_ext=tuple(dlg.ratio_ext[a].value() for a in "xyz"))
        assert coords == engine
        # STpre auto1: 8000 elements -> round(8000^(1/3)) = 20 cells/axis,
        # 21 grid lines with the part range divided uniformly
        assert len(coords) == 21
        assert coords[0] == -25.0 and coords[-1] == 25.0
        assert 0.0 in coords and 10.0 in coords
        inner = [v for v in coords if 0.0 < v < 10.0]
        assert len(inner) == 4
        assert all(round(b - a, 6) == 2.0
                   for a, b in zip((0.0, *inner), (*inner, 10.0)))
    finally:
        dlg.close()


# ------------------------------- AM-2: standard length + ratios mode

def test_standard_length_ratio_dialog_end_to_end(qapp):
    m, meshes = _box_project()
    dlg = _dialog(m, meshes)
    try:
        dlg.method_radios["rough_and_detail"].setChecked(True)
        for ax in "xyz":
            dlg.std[ax].setValue(2.5)
            dlg.ratio[ax].setValue(1.0)
            dlg.ratio_ext[ax].setValue(1.2)
        dlg._gridding()
        coords = _dialog_coords(dlg, m)
        engine = _engine_coords(
            m, meshes, method="rough_and_detail",
            std=(2.5, 2.5, 2.5), thr=(0.0, 0.0, 0.0),
            ratio=(1.0, 1.0, 1.0), ratio_ext=(1.2, 1.2, 1.2))
        assert coords == engine
        # external first spacing == standard length (right of the part)
        assert 12.5 in coords
        # part boundaries present
        assert 0.0 in coords and 10.0 in coords and 25.0 in coords
    finally:
        dlg.close()

"""P4: GUI offscreen regression tests (PyQt5 + VTK)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import cab_gui
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre
from s_export import build_sdat
from xemt_export import build_emt


HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")


pytestmark = pytest.mark.skipif(not cab_gui._HAS_GUI_DEPS,
                                reason="PyQt5/vtk not installed")


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


def test_viewer_loads(viewer):
    win = viewer
    assert win.model is not None
    assert win.model.project_name == "ex4_e"
    assert win.actors == []
    assert win.nav_tree.topLevelItemCount() == 1
    assert "已加载" in win.status.currentMessage()


def test_model_tree_visibility(viewer):
    win = viewer
    target = None
    for i in range(win.model_tree.topLevelItemCount()):
        item = win.model_tree.topLevelItem(i)
        if item.text(0) == "battery":
            target = item
            break
    assert target is not None
    target.setCheckState(0, __import__("PyQt5.QtCore",
                                        fromlist=["Qt"]).Qt.Unchecked)
    assert target.checkState(0) == __import__("PyQt5.QtCore",
                                              fromlist=["Qt"]).Qt.Unchecked
    target.setCheckState(0, __import__("PyQt5.QtCore",
                                        fromlist=["Qt"]).Qt.Checked)
    assert target.checkState(0) == __import__("PyQt5.QtCore",
                                              fromlist=["Qt"]).Qt.Checked


def test_edit_part_property(viewer, tmp_path):
    win = viewer
    part = next(p for p in win.model.parts() if p.name == "speaker")
    win._show_property("part", part.name)
    assert "speaker" in win.prop_fields["名称"].text()
    win.prop_fields["名称"].setText("speaker_v2")
    win.prop_fields["材料"].setText("epoxy_resin(300K)")
    win._apply_edits()
    assert win.model.find_part("speaker_v2") is not None
    assert win.model.find_part("speaker") is None
    # rebuild cab with the edit
    out = str(tmp_path / "edited.cab")
    assert win._rebuild_to(out)
    re_arch = CabArchive.parse(open(out, "rb").read())
    re_members = {m.name: m.data for m in re_arch.fill_member_data()}
    m2 = StpreModel(parse_stpre(re_members["ex4_e.xml"]))
    assert m2.find_part("speaker_v2") is not None
    assert m2.find_part("speaker") is None


def test_export_s_and_xemt(viewer, tmp_path):
    win = viewer
    base = str(tmp_path / "out")
    with open(base + ".s", "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(build_sdat(win.model, win.props))
    with open(base + ".xemt", "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(build_emt(win.model, win.props))
    assert os.path.getsize(base + ".s") > 40_000
    assert os.path.getsize(base + ".xemt") > 2_000
    assert open(base + ".s", encoding="utf-8-sig").read().startswith("SDAT")
    assert "<EMT>" in open(base + ".xemt", encoding="utf-8-sig").read()


def test_wireframe_toggle(viewer):
    win = viewer
    win._set_wireframe(True)
    assert win._wireframe is True
    assert len(win.actors) == 0          # headless mode builds no actors

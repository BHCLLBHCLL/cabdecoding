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
    assert win.tree_view.layout_tree.topLevelItemCount() >= 1
    assert "已加载" in win.status.currentMessage()


def test_layout_panes(viewer):
    win = viewer
    titles = {w.title_label.text()
              for w in win.findChildren(__import__(
                  "cab_panes", fromlist=["PaneFrame"]).PaneFrame)}
    assert "Tree/List View" in titles
    assert "Control" in titles
    assert "Draw Window" in titles
    assert "Message" in titles
    menus = [a.text() for a in win.menuBar().actions()]
    assert any("File" in m for m in menus)
    assert any("Part" in m for m in menus)
    assert any("Wizard" in m for m in menus)
    assert any("Mesh" in m for m in menus)


def test_model_tree_visibility(viewer):
    from PyQt5.QtCore import Qt
    win = viewer
    target = win.tree_view.find_part_item("battery")
    assert target is not None
    target.setCheckState(0, Qt.Unchecked)
    assert target.checkState(0) == Qt.Unchecked
    assert "battery" in win._hidden_parts
    target.setCheckState(0, Qt.Checked)
    assert target.checkState(0) == Qt.Checked
    assert "battery" not in win._hidden_parts


def test_edit_part_property(viewer):
    import tempfile
    from PyQt5.QtWidgets import QComboBox, QLineEdit
    win = viewer
    # reload clean state for name rename test
    win.load(CAB)
    part = next(p for p in win.model.parts() if p.name == "speaker")
    win._show_property("part", part.name)
    name_w = win.control.prop_fields["名称"]
    assert isinstance(name_w, QLineEdit)
    assert "speaker" in name_w.text()
    name_w.setText("speaker_v2")
    mat_w = win.control.prop_fields["材料"]
    if isinstance(mat_w, QComboBox):
        mat_w.setCurrentText("epoxy_resin(300K)")
    else:
        mat_w.setText("epoxy_resin(300K)")
    win._apply_edits()
    assert win.model.find_part("speaker_v2") is not None
    assert win.model.find_part("speaker") is None
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        out = os.path.join(td, "edited.cab")
        assert win._rebuild_to(out)
        re_arch = CabArchive.parse(open(out, "rb").read())
        re_members = {m.name: m.data for m in re_arch.fill_member_data()}
        m2 = StpreModel(parse_stpre(re_members["ex4_e.xml"]))
        assert m2.find_part("speaker_v2") is not None
        assert m2.find_part("speaker") is None


def test_export_s_and_xemt(viewer):
    import tempfile
    win = viewer
    win.load(CAB)
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        base = os.path.join(td, "out")
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
    assert win._drawing_mode == "Line"
    assert len(win.actors) == 0          # headless mode builds no actors


def test_drawing_mode_control(viewer):
    win = viewer
    win.control.set_drawing_mode("Translucent")
    win._set_drawing_mode("Translucent")
    assert win._drawing_mode == "Translucent"
    assert win._translucent is True
    # STpre-style: Part + Element division simultaneous
    assert "element" in win.control.layer_checks
    assert "part" in win.control.layer_checks
    win.control.layer_checks["element"].setChecked(True)
    win.control.layer_checks["part"].setChecked(True)
    assert win.control.layer_on("element") is True
    assert win.control.layer_on("part") is True
    win._set_drawing_mode("Mesh lines")  # compat → Shading + element
    assert win._drawing_mode == "Shading"
    assert win.control.layer_on("element") is True


def test_clipping_plane_apply(viewer):
    """M39-P7: per-mapper clipping (no vtkRenderer RemoveAllClipPlanes)."""
    win = viewer
    import vtk
    import cab_gui

    class Props:
        def __init__(self, items):
            self._items = items

        def GetNumberOfItems(self):
            return len(self._items)

        def GetItemAsObject(self, i):
            return self._items[i]

    class FakeRenderer:
        def __init__(self):
            self._props = []

        def GetViewProps(self):
            return Props(self._props)

    mapper = vtk.vtkPolyDataMapper()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    fake = FakeRenderer()
    fake._props.append(actor)

    class Host:
        renderer = fake
        _clip_planes = [vtk.vtkPlane()]

    cab_gui.CabViewer._apply_clip_planes(Host)
    assert mapper.GetNumberOfClippingPlanes() == 1
    Host._clip_planes = []
    cab_gui.CabViewer._apply_clip_planes(Host)
    assert mapper.GetNumberOfClippingPlanes() == 0


def test_edges_actor_extracts_lines():
    if not cab_gui._HAS_GUI_DEPS:
        pytest.skip("no gui deps")
    import cab_vtk
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    arch = CabArchive.parse(open(CAB, "rb").read())
    members = {m.name: m.data for m in arch.fill_member_data()}
    model = StpreModel(parse_stpre(members["ex4_e.xml"]))
    boxes = cab_vtk.part_boxes(model)
    pd = cab_vtk._make_box_polydata(boxes[0], wireframe=False)
    actor = cab_vtk.edges_actor(pd)
    assert actor.GetMapper().GetInput().GetNumberOfCells() > 0


def test_nyi_logs(viewer):
    win = viewer
    win.message_win.clear()
    win._nyi("Cuboid")
    text = win.message_win.text.toPlainText()
    assert "WARN" in text
    assert "Cuboid" in text

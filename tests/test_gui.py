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
        _layer_actors = {}

        def _clip_exempt_actors(self):
            return set()

    host = Host()
    cab_gui.CabViewer._apply_clip_planes(host)
    assert mapper.GetNumberOfClippingPlanes() == 1
    host._clip_planes = []
    cab_gui.CabViewer._apply_clip_planes(host)
    assert mapper.GetNumberOfClippingPlanes() == 0


def test_layer_detail_rows(viewer):
    """Control Drawing On/Off Detail shows real per-layer state."""
    win = viewer
    rows = win._layer_detail_rows()
    labels = {r[0] for r in rows}
    assert len(rows) >= 14
    assert {"Part", "Point", "RootBlock", "Aspect ratio",
            "Condition (flow, etc)"} <= labels
    by = {r[0]: r for r in rows}
    assert by["Part"][1] == (
        "On" if win.control.layer_on("part") else "Off")
    assert by["Point"][2] == len(win._layer_actors.get("point", []))


def test_layer_detail_dialog_builds(viewer, monkeypatch):
    from PyQt5.QtWidgets import QDialog
    monkeypatch.setattr(QDialog, "exec_", lambda self: 0)
    viewer._view_layer_detail_dialog()


def test_point_layer_owns_point_markers(viewer):
    """Point-layer toggle controls point-kind actors; Part layer skips them."""
    import vtk
    win = viewer

    class FakeRenderWindow:
        def Render(self):
            pass

    class FakeRenderer:
        def GetRenderWindow(self):
            return FakeRenderWindow()

    actor = vtk.vtkActor()
    win._enable_3d = True
    win.renderer = FakeRenderer()
    win.actors = [(actor, "pt1")]
    win._point_part_names = {"pt1"}
    win._layer_actors["point"] = [actor]
    win._on_layer_toggled("part", False)
    assert actor.GetVisibility() == 1
    win._on_layer_toggled("point", False)
    assert actor.GetVisibility() == 0
    win._on_layer_toggled("point", True)
    assert actor.GetVisibility() == 1
    win._enable_3d = False
    win.renderer = None


def test_aspect_ratio_color():
    from cab_gui import aspect_ratio_color
    assert aspect_ratio_color(1.5) == (0.15, 0.7, 0.3)
    assert aspect_ratio_color(3.0) == (0.95, 0.75, 0.15)
    assert aspect_ratio_color(9.0) == (0.9, 0.2, 0.2)


def test_ray_aabb_face():
    from cab_gui import ray_aabb_face
    lo = (0.0, 0.0, 0.0)
    hi = (1.0, 1.0, 1.0)
    assert ray_aabb_face((0.5, 0.5, 10.0), (0.0, 0.0, -1.0),
                         lo, hi) == "Zmax"
    assert ray_aabb_face((10.0, 0.5, 0.5), (-1.0, 0.0, 0.0),
                         lo, hi) == "Xmax"
    assert ray_aabb_face((0.5, 0.5, -1.0), (0.0, 0.0, 1.0),
                         lo, hi) == "Zmin"
    assert ray_aabb_face((10.0, 10.0, 10.0), (1.0, 0.0, 0.0),
                         lo, hi) is None


def test_snap_picked_vertex(viewer):
    from cab_parts import cube_tess
    tess = cube_tess((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))
    tess.name = "pt1"
    viewer._cad_meshes = [tess]
    got = viewer._snap_picked_vertex("pt1", (0.0001, 0.0, 0.0))
    assert got is not None
    assert got[1] in range(8)
    assert got[2] == pytest.approx((0.0, 0.0, 0.0))
    assert viewer._snap_picked_vertex("pt1", (0.1, 0.1, 0.1)) is None


def test_face_condition_types(viewer):
    import xml.etree.ElementTree as ET
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.ensure_domain_faces()
    root = model.doc.root
    val = ET.SubElement(root, "value")
    val.attrib["type"] = "flux"
    nm = ET.SubElement(val, "name")
    nm.text = " v1 "
    cond = ET.SubElement(root, "condition")
    rg = ET.SubElement(cond, "region")
    rg.text = " Xmin "
    vv = ET.SubElement(cond, "value")
    vv.text = " v1 "
    viewer.model = model
    types = viewer._face_condition_types()
    assert types["Xmin"] == ["flux"]
    assert types["Xmax"] == []
    assert viewer._condition_face_color(["flux"]) == (0.25, 0.45, 1.0)
    assert viewer._condition_face_color([]) == (0.62, 0.62, 0.62)


def test_feed_pick_point_distance(viewer):
    """L10: snapped vertices feed the non-modal Distance dialog (P1/P2)."""

    class Spin:
        def __init__(self):
            self.v = 0.0

        def setValue(self, v):
            self.v = float(v)

        def value(self):
            return self.v

    class Dlg:
        def __init__(self):
            self.pick_spins = [Spin() for _ in range(6)]
            self.pick_hint = type("H", (), {
                "setText": lambda self, t: None})()
            self.called = 0
            self.pick_calc = self._calc

        def _calc(self):
            self.called += 1

    dlg = Dlg()
    viewer._pick_dialog = dlg
    viewer._pick_slot = "P1"
    assert viewer._feed_pick_point(("p", 0, (0.001, 0.002, 0.003))) is True
    assert [s.v for s in dlg.pick_spins[:3]] == [1.0, 2.0, 3.0]
    assert viewer._pick_slot == "P2"
    assert viewer._feed_pick_point(("p", 1, (0.004, 0.005, 0.006))) is True
    assert [s.v for s in dlg.pick_spins[3:]] == [4.0, 5.0, 6.0]
    assert viewer._pick_slot is None
    assert dlg.called == 1
    viewer._clear_pick_dialog(dlg)
    assert viewer._pick_dialog is None


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


def test_domain_face_edges_polydata():
    if not cab_gui._HAS_GUI_DEPS:
        pytest.skip("no gui deps")
    import cab_vtk
    pd = cab_vtk.domain_face_edges(
        "Xmin", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    assert pd.GetNumberOfPoints() == 4
    assert pd.GetNumberOfLines() == 4


def test_nyi_logs(viewer):
    win = viewer
    win.message_win.clear()
    win._nyi("Cuboid")
    text = win.message_win.text.toPlainText()
    assert "WARN" in text
    assert "Cuboid" in text

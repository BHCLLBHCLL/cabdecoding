"""Layout of Parts / Conditions — STpre Tree/List View (Xmin…Zmax)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from cab_container import CabArchive
from cab_panes import TreeListView
from cabxml import DOMAIN_FACE_NAMES, StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"

pytestmark = pytest.mark.skipif(
    __import__("cab_gui")._HAS_GUI_DEPS is False,
    reason="PyQt5/vtk not installed",
)


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture()
def box_model():
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml = next(
        m.data for m in archive.members
        if m.name.endswith(".xml") and "property" not in m.name
        and not m.name.startswith("_")
    )
    return StpreModel(parse_stpre(xml)), archive.members


def test_domain_faces_order(box_model):
    model, _ = box_model
    faces = model.domain_faces()
    assert [n for n, _ in faces] == list(DOMAIN_FACE_NAMES)
    assert all(el is not None for _, el in faces)


def test_ensure_domain_faces_creates_missing():
    raw = (b"\xef\xbb\xbf<?xml version=\"1.0\"?>\n"
           b"<stpre>\n</stpre>\n")
    model = StpreModel(parse_stpre(raw))
    names = model.ensure_domain_faces()
    assert names == list(DOMAIN_FACE_NAMES)
    assert all(el is not None for _, el in model.domain_faces())

    # Strip faces then re-ensure
    from cabxml import _children
    ar = model.analysis_region()
    for reg in list(_children(ar, "region")):
        ar.remove(reg)
    assert all(el is None for _, el in model.domain_faces())
    model.ensure_domain_faces()
    assert [n for n, el in model.domain_faces() if el is not None] == list(
        DOMAIN_FACE_NAMES)


def test_layout_has_xmin_zmax(qapp, box_model):
    model, members = box_model
    view = TreeListView()
    view.populate(model, members)
    # Top-level: Parts, Computational_Domain, Region, Others
    tops = [view.layout_tree.topLevelItem(i).text(0)
            for i in range(view.layout_tree.topLevelItemCount())]
    assert tops == ["Parts", "Computational_Domain", "Region", "Others"]

    reg = view.layout_tree.topLevelItem(2)
    face_names = [reg.child(i).text(0) for i in range(reg.childCount())]
    assert face_names[:6] == list(DOMAIN_FACE_NAMES)
    for i in range(6):
        data = reg.child(i).data(0, __import__("PyQt5.QtCore",
                                               fromlist=["Qt"]).Qt.UserRole)
        assert data == ("domain_face", DOMAIN_FACE_NAMES[i])

    parts = view.layout_tree.topLevelItem(0)
    part_names = [parts.child(i).text(0) for i in range(parts.childCount())]
    assert "box" in part_names


def test_conditions_table_domain_boundary(qapp, box_model):
    model, members = box_model
    view = TreeListView()
    view.populate(model, members)
    tree = view.cond_tree
    assert tree.columnCount() == 4
    rows = {
        tree.topLevelItem(i).text(0): (
            tree.topLevelItem(i).text(1),
            tree.topLevelItem(i).text(2),
            tree.topLevelItem(i).text(3),
        )
        for i in range(tree.topLevelItemCount())
    }
    assert "Domain(cuboid)" in rows
    assert rows["Domain(cuboid)"][0] == "Domain"
    assert rows["Domain(cuboid)"][2] == "Initial T"
    for face in DOMAIN_FACE_NAMES:
        assert face in rows
        assert rows[face][0] == "DomainBoundary"
    assert rows["box"][0] == "Obstacle"
    # Undefined stress wall condition
    undef = [k for k in rows if k.startswith("Undefined(Stress")]
    assert undef
    assert rows[undef[0]][2] == "Noslip(smooth)"

"""Layout tree: checkbox clicks must not open edit dialogs."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QTreeWidgetItem


@pytest.fixture
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _tree(qapp):
    from cab_panes import TreeListView
    from cabxml import StpreModel, parse_stpre, new_stpre_bytes
    model = StpreModel(parse_stpre(new_stpre_bytes("t")))
    model.ensure_domain(base=(0, 0, 0), size=(100, 100, 100))
    view = TreeListView()
    view.populate(model, [])
    return view


def _domain_item(view) -> QTreeWidgetItem:
    tree = view.layout_tree
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        for j in range(top.childCount()):
            child = top.child(j)
            data = child.data(0, Qt.UserRole)
            if data and data[0] == "domain":
                return child
    raise AssertionError("Domain item not found")


def test_double_click_on_check_does_not_activate(qapp):
    view = _tree(qapp)
    activated = []
    view.item_activated.connect(lambda k, n: activated.append((k, n)))
    item = _domain_item(view)
    rect = view._check_indicator_rect(item)
    assert rect is not None and rect.isValid()
    view._tree_click_pos = rect.center()
    view._on_double_click(item, 0)
    assert activated == []


def test_double_click_on_label_activates_domain(qapp):
    view = _tree(qapp)
    activated = []
    view.item_activated.connect(lambda k, n: activated.append((k, n)))
    item = _domain_item(view)
    vr = view.layout_tree.visualItemRect(item)
    # Click toward the right side of the label (away from checkbox)
    view._tree_click_pos = QPoint(vr.right() - 8, vr.center().y())
    view._last_check_change = None
    view._on_double_click(item, 0)
    assert len(activated) == 1 and activated[0][0] == "domain"


def test_check_toggle_then_dblclick_suppressed(qapp):
    view = _tree(qapp)
    activated = []
    view.item_activated.connect(lambda k, n: activated.append((k, n)))
    item = _domain_item(view)
    # Simulate checkbox flip immediately before double-click
    view._last_check_change = (item, __import__("time").monotonic())
    vr = view.layout_tree.visualItemRect(item)
    view._tree_click_pos = QPoint(vr.right() - 8, vr.center().y())
    view._on_double_click(item, 0)
    assert activated == []
    view.close()

"""§25 F5 batch: ConvergenceWindow zoom (view window) + CSV/PNG export."""
from __future__ import annotations

import csv

import pytest


@pytest.fixture(scope="module")
def qapp():
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys as _sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([_sys.argv[0]])
    yield app


def _points(n=20):
    return [(i + 1, 1.0 / (10 ** (i * 0.25))) for i in range(n)]


def test_view_window_zoom_and_reset(qapp):
    from cab_panes import ConvergenceWindow
    w = ConvergenceWindow()
    try:
        w.set_points(_points())
        assert w.view_window() is None
        w.wheelEvent(_wheel(+120))
        i0, i1 = w.view_window()
        assert i0 > 0 and i1 < 19  # zoomed in
        span = i1 - i0
        w.wheelEvent(_wheel(+120))
        assert (w.view_window()[1] - w.view_window()[0]) < span
        w.mouseDoubleClickEvent(None)
        assert w.view_window() is None  # reset fits all
        # zoom out from a small window expands and clamps to the range
        w.set_view_window(5, 10)
        for _ in range(8):
            w.wheelEvent(_wheel(-120))
        i0, i1 = w.view_window()
        assert (i0, i1) == (0, 19)
    finally:
        w.deleteLater()


def test_export_csv_visible_window(qapp, tmp_path):
    from cab_panes import ConvergenceWindow
    w = ConvergenceWindow()
    try:
        w.set_points(_points())
        w.set_view_window(2, 6)
        out = tmp_path / "conv.csv"
        n = w.export_csv(str(out))
        assert n == 5
        with open(out, encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == ["cycle", "residual"]
        assert len(rows) == 6  # header + 5 visible points
        assert int(rows[1][0]) == 3  # first visible cycle
    finally:
        w.deleteLater()


def test_export_png(qapp, tmp_path):
    from cab_panes import ConvergenceWindow
    w = ConvergenceWindow()
    try:
        w.set_points(_points())
        out = tmp_path / "conv.png"
        w.grab().save(str(out), "PNG")
        assert out.stat().st_size > 500
    finally:
        w.deleteLater()


def _wheel(delta):
    from PyQt5.QtCore import QPoint, QPointF
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtCore import Qt
    return QWheelEvent(QPointF(10, 10), QPointF(10, 10),
                       QPoint(0, 0), QPoint(0, delta),
                       Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate,
                       False)

"""STpre Draw Window view keys: X/Y/Z(/Shift) + F Fit."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import cab_gui


@pytest.mark.parametrize(
    "plane,negative,pos,up",
    [
        ("yz", False, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ("yz", True, (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ("xz", False, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ("xz", True, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
        ("xy", False, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        ("xy", True, (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    ],
)
def test_plane_view_camera(plane, negative, pos, up):
    assert cab_gui.plane_view_camera(plane, negative=negative) == (pos, up)


@pytest.mark.parametrize(
    "key,shift,expected",
    [
        ("x", False, ("plane", "yz", False)),
        ("X", True, ("plane", "yz", True)),
        ("y", False, ("plane", "xz", False)),
        ("z", False, ("plane", "xy", False)),
        ("f", False, ("fit",)),
        ("f", True, None),
        ("a", False, None),
    ],
)
def test_view_key_action(key, shift, expected):
    assert cab_gui.view_key_action(key, shift=shift) == expected


@pytest.fixture
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_dispatch_view_key_headless(qapp):
    """Dispatch maps keys without requiring a live render window."""
    win = cab_gui.CabViewer(None, enable_3d=False)
    try:
        # No renderer: plane/fit are no-ops but still "handled"
        assert win._dispatch_view_key("x") is True
        assert win._dispatch_view_key("y", shift=True) is True
        assert win._dispatch_view_key("z") is True
        assert win._dispatch_view_key("f") is True
        assert win._dispatch_view_key("q") is False
    finally:
        win.close()


def test_draw_shortcuts_installed(qapp):
    """Shortcut wiring does not need a live VTK render window."""
    from PyQt5.QtWidgets import QWidget

    win = cab_gui.CabViewer(None, enable_3d=False)
    try:
        win.vtk_widget = QWidget()
        win._install_draw_view_shortcuts()
        seqs = {
            a.shortcut().toString()
            for a in win.vtk_widget.actions()
            if not a.shortcut().isEmpty()
        }
        assert "X" in seqs
        assert "Y" in seqs
        assert "Z" in seqs
        assert "F" in seqs
        assert any("Shift" in s and s.endswith("X") for s in seqs)
        assert win._act_xy.shortcut().toString() == "Z"
        assert win._act_xz.shortcut().toString() == "Y"
        assert win._act_yz.shortcut().toString() == "X"
    finally:
        win.close()
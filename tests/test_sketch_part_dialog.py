"""Sketch Part dialog layout / pick / Size-Attribute coverage."""
from __future__ import annotations

import cab_sketch


def test_snap_and_world_uv():
    p = cab_sketch.SketchPlane()
    assert cab_sketch.snap_uv_mm(p, 7.2, 3.1) == (5.0, 5.0)
    u, v = cab_sketch.world_to_uv_mm(p, 0.01, 0.02, 0.0)
    assert abs(u - 10.0) < 1e-9 and abs(v - 20.0) < 1e-9


def test_sketch_part_dialog_gui():
    """GUI checks — skipped when Qt display init fails under pytest."""
    try:
        from PyQt5.QtWidgets import QApplication, QDoubleSpinBox
        import sys
        from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    except Exception:
        return
    app = QApplication.instance() or QApplication(sys.argv)
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    cab_sketch.apply_plane(m, cab_sketch.default_sketch_plane(m))
    dlg = cab_sketch.SketchPartDialog(m, None)
    try:
        assert dlg.windowTitle() == "Part (Sketch Part)"
        # Root cause of the "0,0" glitch: spins parented to the dialog itself
        assert not [
            c for c in dlg.children() if isinstance(c, QDoubleSpinBox)
        ]
        assert dlg.attr_panel is not None
        assert dlg.orientation.currentText().startswith("W-Axis")
        assert dlg.height.value() == 5.0
        dlg.add_picked_vertex(5, 85)
        dlg.add_picked_vertex(15, 3)
        assert dlg.points_table.rowCount() == 2
        pts = dlg.spec()["profile"].points
        assert pts[0] == (5.0, 85.0)
        assert "color" in dlg.spec() and "layer" in dlg.spec()
    finally:
        dlg.close()
        dlg.deleteLater()
        app.processEvents()

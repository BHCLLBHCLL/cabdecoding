"""Post-Gridding Drawing→Mesh face grids with depth-occlusion shell."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _model_with_grid():
    from cabxml import StpreModel, parse_stpre, new_stpre_bytes
    model = StpreModel(parse_stpre(new_stpre_bytes("meshdisp")))
    model.ensure_domain(base=(0, 0, 0), size=(100, 100, 100))
    xs = [float(i) for i in range(0, 101, 5)]  # 21 points
    model.set_mesh(
        {"x": xs, "y": list(xs), "z": list(xs)},
        domain_min=(0, 0, 0), domain_max=(100, 100, 100),
        standard_length=(5, 5, 5),
    )
    return model


def test_mesh_block_display_actors_shell_and_lines():
    import cab_vtk
    model = _model_with_grid()
    actors = cab_vtk.mesh_block_display_actors(model, stride=1)
    assert len(actors) == 2
    shell, lines = actors
    assert shell.GetMapper().GetInput().GetNumberOfPolys() == 6
    assert lines.GetMapper().GetInput().GetNumberOfLines() > 0
    # shell is translucent for see-through + depth write
    assert shell.GetProperty().GetOpacity() < 1.0


def test_gridding_enables_mesh_layer(qapp):
    import cab_gui
    import cab_dialogs
    import numpy as np

    win = cab_gui.CabViewer(None, enable_3d=False)
    try:
        assert win.control.layer_on("mesh") is False
        # Minimal CAD mesh so native gridding has something to bound
        class _T:
            name = "box"
            points = np.array([[0, 0, 0], [0.1, 0.1, 0.1]], float)
            vertices = None
        dlg = cab_dialogs.GriddingDialog(win.model, [_T()], parent=win)
        dlg.detection_radios["minmax"].setChecked(True)
        dlg.method_radios["rough_and_detail"].setChecked(True)
        dlg._gridding()
        assert win.control.layer_on("mesh") is True
        axes = win.model.mesh_axes()
        assert axes and all(len(axes[a]) > 2 for a in "xyz")
        dlg.close()
    finally:
        win.close()

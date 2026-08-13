"""M34: panel face-thin meshing + cylindrical domain type flags."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

import cab_domain
import cab_mesh
from cab_parts import panel_tess
from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def _panel_model():
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    model.add_part(name="P1", kind="panel", attribute="panel")
    tess = panel_tess((0, 0, 5), (10, 10, 0), "+Z")
    tess.name = "P1"
    return model, tess


def test_panel_part_meshing_smoke():
    """Open panel must get face-thin occupancy (not empty / ignored)."""
    _model, tess = _panel_model()
    axes = {ax: [i * 1.0 for i in range(11)] for ax in "xyz"}  # 0..10 mm
    # Solid ray cast alone often yields nothing on a sheet — panel path must.
    analysis, boxes = cab_mesh.classify_cells(
        axes, [tess],
        part_kinds={"P1": "panel"},
        part_attrs={"P1": "panel"})
    assert analysis == (1, 10, 1, 10, 1, 10)
    assert "P1" in boxes
    assert boxes["P1"], "panel should occupy at least one cell box"
    # Thin band around z=5 mm → cells with centres near 4.5 / 5.5
    flat = boxes["P1"]
    k_lo = min(b[4] for b in flat)
    k_hi = max(b[5] for b in flat)
    assert k_lo <= 6 <= k_hi or k_lo <= 5 <= k_hi


def test_panel_attribute_triggers_face_thin():
    assert cab_mesh.is_panel_part("panel", "solid")
    assert cab_mesh.is_panel_part("cube", "panel")
    assert not cab_mesh.is_panel_part("cube", "solid")


def test_cylindrical_domain_type_set():
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    spec = cab_domain.DomainSpec(
        coordinate="cylindrical", unit="mm",
        xyz_min=(0.0, 0.0, 0.0), xyz_max=(100.0, 100.0, 100.0),
        material="air")
    assert cab_domain.apply_domain(model, spec) is True
    ar = model.analysis_region()
    assert ar is not None
    assert ar.attrib.get("type") == "cylinder"
    assert model.mesh_control_value("domain_coordinate") == "cylindrical"
    again = cab_domain.domain_from_xml(
        StpreModel(parse_stpre(model.doc.serialize())))
    assert again is not None
    assert again.coordinate == "cylindrical"


def test_axial_domain_type_set():
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    spec = cab_domain.DomainSpec(
        coordinate="axial", unit="mm",
        xyz_min=(0.0, 0.0, 0.0), xyz_max=(50.0, 50.0, 50.0))
    cab_domain.apply_domain(model, spec)
    ar = model.analysis_region()
    assert ar.attrib.get("type") == "cube"  # axial reuses cube geometry
    assert model.mesh_control_value("domain_coordinate") == "axial"
    again = cab_domain.domain_from_xml(model)
    assert again.coordinate == "axial"


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_gridding_dialog_domain_type_ui(qapp):
    import cab_dialogs
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    cab_domain.apply_domain(
        model,
        cab_domain.DomainSpec(
            coordinate="cartesian", unit="mm",
            xyz_min=(0, 0, 0), xyz_max=(10, 10, 10)))
    dlg = cab_dialogs.GriddingDialog(model, [], None)
    assert set(dlg.domain_type_radios) == {
        "cartesian", "cylindrical", "axial"}
    dlg.domain_type_radios["cylindrical"].setChecked(True)
    # Minimal gridding with uniform detection so axes exist
    dlg.detection_radios["uniform"].setChecked(True)
    dlg.method_radios["rough_only"].setChecked(True)
    dlg._dom_min = [0.0, 0.0, 0.0]
    dlg._dom_max = [10.0, 10.0, 10.0]
    dlg._gridding()
    assert model.analysis_region().attrib.get("type") == "cylinder"
    assert model.mesh_control_value("domain_coordinate") == "cylindrical"
    assert "Select from list" in dlg.btn_select.text()
    dlg.close()


def test_grid_classifier_matches_separable():
    """L7.5: generic 3-D grid ray cast agrees with the separable path."""
    from cab_parts import cube_tess
    tess = cube_tess((2.0, 2.0, 2.0), (6.0, 6.0, 6.0))
    x = np.arange(10) + 0.5
    centers = np.stack(np.meshgrid(x, x, x, indexing="ij"),
                       axis=-1) / 1000.0
    m1 = cab_mesh.classify_part_cells_grid(
        centers, tess.points, tess.triangles)
    m2 = cab_mesh.classify_part_cells(
        x / 1000.0, x / 1000.0, x / 1000.0,
        tess.points, tess.triangles)
    assert (m1 == m2).all()


def test_cylindrical_classification_cylinder():
    """L7.5: R/θ/Z grid maps to Cartesian centres and classifies a cylinder."""
    from cab_parts import cylinder_tess
    tess = cylinder_tess((0.0, 0.0, 0.0), 5.0, 10.0)
    tess.name = "C"
    axes = {
        "x": [i * 1.0 for i in range(11)],      # R 0..10 mm
        "y": [i * 10.0 for i in range(37)],     # theta 0..360 deg
        "z": [i * 1.0 for i in range(11)],      # Z 0..10 mm
    }
    _, boxes = cab_mesh.classify_cells(
        axes, [tess], part_kinds={"C": "cylinder"},
        part_attrs={"C": "solid"}, coordinate="cylindrical")
    assert boxes.get("C")
    cells = set()
    for b in boxes["C"]:
        i1, i2, j1, j2, k1, k2 = b[:6]
        for i in range(i1, i2 + 1):
            for j in range(j1, j2 + 1):
                for k in range(k1, k2 + 1):
                    cells.add((i, j, k))
    js = {j for _, j, _ in cells}
    ks = {k for _, _, k in cells}
    is_ = {i for i, _, _ in cells}
    assert js == set(range(1, 37))       # full theta ring
    assert ks == set(range(1, 11))       # full Z height
    assert min(is_) == 1
    assert max(is_) <= 5                 # radius 5 mm -> R cells 1..5

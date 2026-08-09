"""M6: Initial Wizard + Condition Wizard write-back and cancel restore."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

import cab_domain
from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture()
def pieces(qapp):
    import cab_gui
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    prop_member = next((m for m in archive.members
                        if m.name.endswith("_property.xml")), None)
    model = StpreModel(parse_stpre(xml_member.data))
    props = PropertyModel(parse_property(prop_member.data)) \
        if prop_member else None
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = []
    return archive, model, props, viewer


def test_initial_wizard_steps(pieces):
    import cab_wizards
    archive, model, props, viewer = pieces
    w = cab_wizards.InitialWizard(
        model, props, viewer._cad_meshes, archive=archive, parent=viewer)
    titles = [w._titles[k] for k in w._keys]
    assert titles == [
        "Project", "Computational Domain", "Analysis Type",
        "Initial Value/Gravity", "Purpose of Analysis", "Confirm Settings",
    ]
    assert "step" in w.step_label.text() and "( 1/6 )" in w.step_label.text()
    w.close()


def test_initial_wizard_apply(pieces):
    import cab_wizards
    archive, model, props, viewer = pieces
    w = cab_wizards.InitialWizard(
        model, props, viewer._cad_meshes, archive=archive, parent=viewer)
    w.p_project.name.setText("wizproj")
    w.p_project.comment.setText("wizard test")
    w.p_analysis.heat_solve.setCurrentIndex(0)     # Solve
    w.p_analysis.flow_type.setCurrentIndex(1)      # Turbulent
    w.p_initgrav.gravity_chk.setChecked(True)
    w.p_initgrav.gravity_dir.setCurrentIndex(5)    # Z-
    w.p_initgrav.gravity_acc.setValue(9.81)
    w.p_domain.spins["xmin"].setValue(-10.0)
    w.p_domain.spins["xmax"].setValue(10.0)
    w.p_purpose.purpose["external_forced"].setChecked(True)
    w._on_finish()
    assert model.project_name == "wizproj"
    assert model.project_value("comment") == "wizard test"
    assert model.analysis_set_value("heat") == "1"
    assert model.analysis_set_value("turbulence") == "1"
    assert model.analysis_set_value("purpose") == "external_forced"
    assert model.analysis_set_value("grav_vec") == "0,0,-1"
    spec = cab_domain.domain_from_xml(model)
    assert spec.xyz_min[0] == pytest.approx(-10.0)
    assert spec.xyz_max[0] == pytest.approx(10.0)
    # forced-convection boundary auto-set
    assert model.condition_value("region", "Xmin") == "inlet"
    assert model.condition_value("region", "Xmax") == "outlet"
    assert model.condition_value("region", "Ymin") == "side_wall"
    assert model.condition_value("region", "Zmax") == "side_wall"
    assert model.find_value("inlet") is not None
    assert model.find_value("outlet") is not None
    w.close()


def test_initial_wizard_cancel_restores(pieces):
    import cab_wizards
    archive, model, props, viewer = pieces
    snapshot = model.doc.serialize()
    w = cab_wizards.InitialWizard(
        model, props, viewer._cad_meshes, archive=archive, parent=viewer)
    w.p_project.name.setText("changed")
    w._on_cancel()
    assert model.project_name == "box"
    assert model.doc.serialize() == snapshot
    w.close()


def test_condition_wizard_tree_and_apply(pieces):
    import cab_wizards
    archive, model, props, viewer = pieces
    w = cab_wizards.ConditionWizard(model, props, viewer)
    assert w.windowTitle() == "Condition Wizard"
    # nav groups: Boundary / Analysis Control / Output
    bc = w._items.get("bc")
    assert bc is not None and bc.childCount() == 4
    ctrl = w._items.get("control")
    assert ctrl is not None and ctrl.childCount() == 4
    out = w._items.get("output")
    assert out is not None and out.childCount() == 4
    assert "source" in w._items and "fixed" in w._items
    assert w._keys[0] == "analysis" and w._keys[-1] == "confirm"
    assert "ctrl_steady" in w._keys and "out_field" in w._keys
    # STpre chrome: Cancel hidden; Finish stays in the layout
    assert w.btn_cancel.isHidden()
    assert not w.btn_finish.isHidden()

    w.p_analysis.types["heat"].setChecked(True)
    w.p_analysis.transient.setChecked(True)
    w.p_analysis.turbulent.setChecked(True)
    w.p_basic.gravity_chk.setChecked(True)
    w.p_basic.gravity_dir.setCurrentIndex(5)
    w.p_basic.gravity_acc.setValue(9.81)
    w.p_initial.fluid_temp.setValue(25.0)
    w.p_ctrl_steady.start_cycle.setValue(1)
    w.p_ctrl_steady.last_cycle.setValue(300)
    w.p_ctrl_steady.init_dt.setValue(0.0001)
    w.p_ctrl_steady.courant.setValue(1.0)
    w.p_ctrl_solver.hbal_on.setChecked(True)
    w._on_finish()
    assert model.analysis_set_value("heat") == "1"
    assert model.analysis_set_value("turbulence") == "1"
    assert model.analysis_set_value("calculation") == "transient"
    assert model.analysis_set_value("cycle") == "1,300"
    assert model.analysis_set_value("init_time_step") == "0.0001"
    assert model.project_value("ambient_temperature") == "25"
    assert model.analysis_set_value("grav_vec") == "0,0,-1"
    assert model.analysis_set_value("heat_balance", "").startswith("T")
    w.close()


def test_condition_wizard_bc_dialogs(pieces):
    import cab_wizards
    archive, model, props, viewer = pieces
    w = cab_wizards.ConditionWizard(model, props, viewer)
    w.p_bc_flow._faces = ["Xmin"]
    w.p_bc_flow.region.clear()
    w.p_bc_flow.region.addItem("Xmin")
    w.p_bc_flow._build_opening_widgets()      # creates the field widgets
    w.p_bc_flow._ctype.setCurrentIndex(0)     # Fixed velocity
    w.p_bc_flow._vel["x"].setValue(5.0)
    w.p_bc_flow._temp.setValue(20.0)
    w.p_bc_flow._cname.setText("inlet")
    w.p_bc_flow._commit("Xmin")
    assert model.condition_value("region", "Xmin") == "inlet"
    val = model.find_value("inlet")
    assert val is not None and val.attrib.get("type") == "flux"
    # symmetrical boundary = wall free_slip + adiabatic
    w.p_bc_symm._faces = ["Ymax"]
    w.p_bc_symm.region.clear()
    w.p_bc_symm.region.addItem("Ymax")
    w.p_bc_symm.region.setCurrentRow(0)
    w.p_bc_symm._new()
    assert model.condition_value("region", "Ymax").startswith("Symmetry_")
    assert model.find_value("Symmetry_Ymax") is not None
    assert model.find_value("SymmetryHeat_Ymax") is not None
    w.close()


def test_condition_wizard_cancel_restores(pieces):
    import cab_wizards
    archive, model, props, viewer = pieces
    snapshot = model.doc.serialize()
    w = cab_wizards.ConditionWizard(model, props, viewer)
    w.p_analysis.types["heat"].setChecked(True)
    w._on_cancel()
    assert model.doc.serialize() == snapshot
    w.close()

"""M7: File/Edit/View/Part/Option/Help menu tests."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("cab_gui")
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _viewer(qapp):
    import cab_gui
    from cab_container import CabArchive
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    members = {m.name: m.data for m in archive.members}
    xml_name = next(n for n in members if n.endswith(".xml")
                    and not n.startswith("_"))
    prop_name = next(n for n in members if n.endswith("_property.xml"))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.archive = archive
    viewer.model = StpreModel(parse_stpre(members[xml_name]))
    viewer.props = PropertyModel(parse_property(members[prop_name]))
    return viewer


def test_print_headless_returns_false(qapp):
    viewer = _viewer(qapp)
    assert viewer._print_to_png(str(ROOT / "tests" / "_print_tmp.png")) \
        is False


def test_find_program_missing(qapp):
    viewer = _viewer(qapp)
    assert viewer._find_program(["__no_such_program__.exe"]) is None


def test_launch_program_missing(qapp):
    viewer = _viewer(qapp)
    assert viewer._launch_program(None, []) is False
    assert viewer._launch_program(
        str(ROOT / "tests" / "__no_such.exe"), []) is False


def test_export_temp_s_files(qapp, tmp_path):
    viewer = _viewer(qapp)
    sfile = viewer._export_temp_s_files()
    assert sfile is not None and os.path.isfile(sfile)
    with open(sfile, encoding="utf-8-sig") as fh:
        assert fh.read(8).startswith("SDAT")


def test_undo_redo_snapshot_stack(qapp):
    viewer = _viewer(qapp)
    before = viewer._snapshot()
    viewer.model.add_part(name="undo_probe")
    assert viewer.model.find_part("undo_probe") is not None
    viewer._push_undo(before)
    viewer._undo()
    assert viewer.model.find_part("undo_probe") is None
    viewer._redo()
    assert viewer.model.find_part("undo_probe") is not None


def test_delete_part_removes_element_and_condition(qapp):
    viewer = _viewer(qapp)
    model = viewer.model
    model.add_part(name="victim")
    # give it an element box and a condition binding
    import xml.etree.ElementTree as ET
    el = ET.SubElement(model.doc.root, "element")
    el.tail = "\n"
    p = ET.SubElement(el, "parts")
    p.attrib["name"] = "victim"
    p.tail = "\n   "
    b = ET.SubElement(p, "body")
    b.attrib["num"] = "1"
    b.tail = "\n      "
    l = ET.SubElement(b, "list")
    l.attrib["no"] = "1"
    l.text = " 1,2,1,2,1,2,0,1,1 "
    l.tail = "\n      "
    c = ET.SubElement(model.doc.root, "condition")
    c.tail = "\n   "
    pt = ET.SubElement(c, "parts")
    pt.text = " victim "
    pt.tail = "\n      "
    v = ET.SubElement(c, "value")
    v.text = " Wall1 "
    v.tail = "\n      "
    assert model.delete_part("victim") is True
    assert model.find_part("victim") is None
    assert model.part_boxes("victim") == []
    assert model.condition_value("parts", "victim") is None
    assert model.delete_part("victim") is False


def test_move_parts_to_group(qapp):
    viewer = _viewer(qapp)
    model = viewer.model
    model.add_part(name="p1")
    model.add_part(name="p2")
    moved = model.move_parts_to_group(["p1", "p2"], "grp")
    assert moved == ["p1", "p2"]
    grp = next(g for g in model.groups()
               if next((n for n in g if n.tag == "name"),
                       None) is not None
               and (next((n for n in g if n.tag == "name"),
                         None).text or "").strip() == "grp")
    names = [next((n for n in el if n.tag == "name"),
                  None).text.strip() for el in grp if el.tag == "parts"]
    assert set(names) == {"p1", "p2"}
    # move back to root
    model.move_parts_to_group(["p1"], "")
    assert model.parts()[0].name == "p1" or \
        any(p.name == "p1" and not p.group for p in model.parts())


def test_view_toggles_message_and_status(qapp):
    viewer = _viewer(qapp)
    viewer._toggle_message_window(False)
    assert viewer.msg_pane.isHidden() is True
    viewer._toggle_message_window(True)
    assert viewer.msg_pane.isHidden() is False
    viewer._toggle_status_bar(False)
    assert viewer.statusBar().isHidden() is True
    viewer._toggle_status_bar(True)
    assert viewer.statusBar().isHidden() is False


def test_git_rev_and_version_lines(qapp):
    viewer = _viewer(qapp)
    rev = viewer._git_rev()
    assert isinstance(rev, str)
    assert len(rev) >= 4


def test_primitive_tessellation_counts():
    import cab_parts
    cube = cab_parts.cube_tess((0, 0, 0), (10, 10, 10))
    assert len(cube.points) == 8 and len(cube.triangles) == 12
    cyl = cab_parts.cylinder_tess((0, 0, 0), 5, 10, "+Z", 8)
    assert len(cyl.points) == 16 and len(cyl.triangles) == 28
    sph = cab_parts.sphere_tess((0, 0, 0), 5, 12)
    assert len(sph.points) == 62 and len(sph.triangles) == 120
    pan = cab_parts.panel_tess((0, 0, 0), (10, 10, 0), "+Z")
    assert len(pan.points) == 4 and len(pan.triangles) == 2
    cone = cab_parts.conical_tess((0, 0, 0), (0, 0, 10), 5, 2, 8)
    assert len(cone.points) == 16
    rev = cab_parts.revolved_tess(5, 10, 0, 360, 0, 10, 8)
    assert len(rev.points) > 0 and len(rev.triangles) > 0
    pipe = cab_parts.pipe_tess((0, 0, 0), (0, 0, 20), 2, 8)
    assert len(pipe.points) == 16


def test_register_and_rebuild_primitive(qapp):
    import cab_parts
    viewer = _viewer(qapp)
    model = viewer.model
    ok = cab_parts.register_primitive(
        model, name="mycube", kind="cube",
        params={"base": (0, 0, 0), "size": (10, 20, 30)},
        material="air(incompressible/20C)", attribute="Solid")
    assert ok is True
    prim = cab_parts.primitives_from_model(model)
    assert len(prim) == 1 and prim[0].name == "mycube"
    assert len(prim[0].points) == 8
    # survives serialize/reparse
    from cabxml import StpreModel, parse_stpre
    model2 = StpreModel(parse_stpre(model.doc.serialize()))
    prim2 = cab_parts.primitives_from_model(model2)
    assert len(prim2) == 1 and prim2[0].name == "mycube"


def test_register_all_part_menu_kinds(qapp):
    import cab_parts
    viewer = _viewer(qapp)
    model = viewer.model
    specs = {
        "cube": {"base": (0, 0, 0), "size": (5, 5, 5)},
        "hexahedron": {"base": (0, 0, 0), "size": (5, 5, 5)},
        "cylinder": {"center": (0, 0, 0), "radius": 2, "height": 5,
                     "direction": "+Z", "divisions": 8},
        "conical": {"center1": (0, 0, 0), "center2": (0, 0, 5),
                    "radius1": 3, "radius2": 1, "divisions": 8},
        "sphere": {"center": (0, 0, 0), "radius": 3, "divisions": 8},
        "panel": {"base": (0, 0, 0), "size": (5, 5, 0), "direction": "+Z"},
        "quad_panel": {"base": (0, 0, 0), "size": (5, 5, 0),
                       "direction": "+Z"},
        "revolved": {"radius1": 2, "radius2": 4, "angle1": 0, "angle2": 360,
                     "z1": 0, "z2": 5, "divisions": 8},
            "point": {"center": (1, 2, 3), "marker": 1},
            "enclosure": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "plate_fin": {"base": (0, 0, 0), "size": (10, 10, 5),
                          "fin_count": 3},
            "pin_fin": {"base": (0, 0, 0), "size": (10, 10, 5),
                        "pin_nx": 2, "pin_ny": 2},
            "peltier": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "two_resistor": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "ac_unit": {"base": (0, 0, 0), "size": (10, 10, 5),
                        "ac_type": "Ceiling cassette (4 directions)"},
            "diffuser": {"base": (0, 0, 0), "size": (10, 10, 5),
                         "diffuser_type": "Anemostat"},
            "delphi": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "multi_resistor": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "heat_pipe": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "card_guide": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "slit_punching": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "anemostat": {"base": (0, 0, 0), "size": (10, 10, 5)},
            "fan": {"base": (0, 0, 0), "size": (10, 10, 2), "direction": "+Z",
                    "inner_radius": 1, "thickness": 2, "flow_rate": 0.01},
        "axial_fan": {"center": (0, 0, 0), "outer_radius": 5,
                      "inner_radius": 1, "thickness": 2, "direction": "+Z"},
        "blower_fan": {"base": (0, 0, 0), "size": (10, 10, 5),
                       "rotation_axis": "+Z"},
        "sketch": {"base": (0, 0, 0), "size": (5, 5, 5),
                   "model_type": "extrusion"},
        "pipe": {"start": (0, 0, 0), "end": (0, 0, 10), "radius": 1,
                 "divisions": 8},
    }
    assert set(specs) == set(cab_parts.PRIMITIVE_KINDS)
    for kind, params in specs.items():
        name = f"p_{kind}"
        ok = cab_parts.register_primitive(
            model, name=name, kind=kind, params=params, attribute="Solid")
        assert ok, kind
        tess = cab_parts.tess_for_spec(kind, params)
        assert len(tess.points) > 0 and len(tess.triangles) > 0, kind
    rebuilt = {p.name for p in cab_parts.primitives_from_model(model)}
    for kind in specs:
        if kind == "sketch":
            continue  # sketch parts rebuild through cab_sketch (parametric)
        assert f"p_{kind}" in rebuilt


def test_thermal_characteristics_dialog(qapp):
    """P2-⑧: Thermal Characteristics of Surface sets default + part emissivity."""
    from cab_options import ThermalCharacteristicsDialog
    viewer = _viewer(qapp)
    dlg = ThermalCharacteristicsDialog(viewer.model, viewer)
    dlg.default_emi.setValue(0.75)
    if dlg.table.rowCount() > 0:
        dlg.table.setItem(0, 1, type(dlg.table.item(0, 0))("0.6"))
    dlg._apply_and_accept()
    assert viewer.model.analysis_set_value(
        "default_rad_coefficient") == "0.75"
    from cabxml import _first
    parts = list(viewer.model.parts())
    if parts:
        el = _first(parts[0].elem, "emissivity")
        assert el is not None and el.text.strip() == "0.6"
    viewer.close()


def test_parametric_study_dialog(qapp):
    """P2-⑧: Parametric Study stores enable + parameter matrix."""
    from cab_options import ParametricStudyDialog
    viewer = _viewer(qapp)
    dlg = ParametricStudyDialog(viewer.model, viewer)
    dlg.enable.setChecked(True)
    dlg._add_row("inflow_temp", "20, 25, 30")
    dlg._add_row("velocity", "1.0, 2.0")
    dlg._apply_and_accept()
    assert viewer.model.analysis_set_value("param_study_enable") == "T"
    assert viewer.model.analysis_set_value(
        "param_names") == "inflow_temp|velocity"
    assert viewer.model.analysis_set_value(
        "param_values") == "20, 25, 30|1.0, 2.0"
    viewer.close()


def test_part_menu_items_cover_all_kinds():
    import cab_parts
    kinds = [k for item in cab_parts.PART_MENU_ITEMS if item
             for k in (item[1],)]
    assert kinds == list(cab_parts.PRIMITIVE_KINDS)


def test_create_part_dialog_spec(qapp):
    import cab_parts
    viewer = _viewer(qapp)
    dlg = cab_parts.CreatePartDialog(
        viewer.model, viewer.props, initial_kind="cylinder", parent=viewer)
    assert dlg.windowTitle() == "Part (Cylinder)"
    dlg.name_edit.setText("cyl1")
    dlg.cyl_radius.setValue(3.0)
    dlg.cyl_height.setValue(7.0)
    spec = dlg.spec()
    assert spec["kind"] == "cylinder"
    assert spec["name"] == "cyl1"
    assert spec["params"]["radius"] == 3.0
    assert spec["params"]["height"] == 7.0
    assert "color" in spec and "layer" in spec
    assert dlg.btn_preview is not None and dlg.btn_ok is not None
    dlg.close()
    dlg2 = cab_parts.CreatePartDialog(
        viewer.model, viewer.props, initial_kind="cube", parent=viewer)
    assert dlg2.windowTitle() == "Part (Cuboid)"
    assert dlg2.name_edit.text() == "Cuboid1"
    dlg2.close()
    dlg3 = cab_parts.CreatePartDialog(
        viewer.model, viewer.props, initial_kind="pipe", parent=viewer)
    dlg3.name_edit.setText("pipe1")
    assert dlg3.spec()["kind"] == "pipe"
    dlg3.close()


def test_options_dialog_values_and_persist(qapp):
    import cab_options
    viewer = _viewer(qapp)
    dlg = cab_options.OptionsDialog(viewer, props=viewer.props)
    dlg.facet_angle.setValue(6.0)
    dlg.drawing_mode.setCurrentText("Line")
    vals = dlg.values()
    assert vals["facet_angle"] == 6.0
    assert vals["drawing_mode"] == "Line"
    for key, value in vals.items():
        cab_options.set_setting(key, value)
    assert float(cab_options.get_setting("facet_angle")) == 6.0
    dlg.close()


def test_apply_options_live(qapp):
    viewer = _viewer(qapp)
    viewer._apply_options({
        "drawing_mode": "Line",
        "log_level": "WARN",
        "undo_levels": 7,
        "message_max_blocks": 500,
        "show_status_bar": True,
        "background": "Black",
    })
    assert viewer._drawing_mode == "Line"
    assert viewer._undo_limit == 7
    assert viewer._log_level == "WARN"
    assert viewer.message_win.text.maximumBlockCount() == 500
    if viewer.renderer is not None:
        assert viewer.renderer.GetBackground()[0] == 0.0


def test_coord_spinbox_trims_trailing_zeros(qapp):
    from cab_widgets import CoordSpinBox
    sb = CoordSpinBox()
    assert sb.textFromValue(0.0) == "0"
    assert sb.textFromValue(10.0) == "10"
    assert sb.textFromValue(1.2300) == "1.23"
    assert sb.textFromValue(-2.0) == "-2"
    sb.setDecimals(2)
    assert sb.textFromValue(3.1400) == "3.14"
    assert sb.textFromValue(0.001) == "0"


def test_dialog_modules_use_coord_spinbox(qapp):
    from cab_widgets import CoordSpinBox
    import cab_dialogs
    import cab_parts
    import cab_options
    assert cab_dialogs.QDoubleSpinBox is CoordSpinBox
    assert cab_parts.QDoubleSpinBox is CoordSpinBox
    assert cab_options.QDoubleSpinBox is CoordSpinBox


def test_parametric_case_matrix():
    """P2: Parametric Study case expansion + CSV export helpers."""
    from cab_options import expand_cases, case_matrix_csv
    cases = expand_cases(
        ["w", "h"], ["1,2", "10,20,30"])
    assert cases == [
        {"w": "1", "h": "10"}, {"w": "1", "h": "20"},
        {"w": "1", "h": "30"}, {"w": "2", "h": "10"},
        {"w": "2", "h": "20"}, {"w": "2", "h": "30"},
    ]
    assert expand_cases([], []) == []
    assert expand_cases(["a"], [""]) == [{"a": ""}]
    csv_text = case_matrix_csv(["w", "h"], ["1,2", "10,20,30"])
    lines = csv_text.splitlines()
    assert lines[0] == "w,h"
    assert len(lines) == 7
    assert lines[4] == "2,10"    # header + 3 cases of the first value


def test_parametric_dialog_smoke(qapp):
    """P2: Parametric Study dialog previews case count."""
    from cab_options import ParametricStudyDialog
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes("demo")))
    dlg = ParametricStudyDialog(m)
    dlg._add_row("w", "1,2")
    dlg._refresh_cases()
    assert dlg.case_label.text() == "2 case(s)"
    dlg._add_row("h", "10,20,30")
    dlg._refresh_cases()
    assert dlg.case_label.text() == "6 case(s)"
    dlg.close()

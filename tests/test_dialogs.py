"""M5: STpre-style dialog framework tests (cab_dialogs).

Chrome aligned with the [Edit Computational Domain] screenshot and the
Pre_eng manual; labels verified against STpreParts_Bx64.dll strings.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

import cab_domain
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "tests" / "box.cab"
EX4E = ROOT / "tests" / "ex4_e" / "ex4_e.xml"


def _box_model() -> StpreModel:
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    return StpreModel(parse_stpre(xml_member.data))


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture()
def dlg_pieces(qapp):
    import cab_dialogs
    import cab_gui
    model = _box_model()
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = []
    return cab_dialogs, model, viewer


def test_domain_dialog_stpre_layout(dlg_pieces):
    """STpre [Edit Computational Domain] chrome: header, name+color row,
    Scale / Attribute-Condition columns, Preview/Apply/OK/Cancel."""
    cab_dialogs, model, viewer = dlg_pieces
    dlg = cab_dialogs.DomainDialog(model, None, [], viewer)
    assert dlg.windowTitle() == "Edit Computational Domain"
    assert set(dlg._buttons) == {"Preview", "Apply", "OK", "Cancel"}
    assert dlg.name_edit.text() == "Domain(cuboid)"
    assert dlg.color_btn.rgba() == (0, 255, 255, 255)
    assert dlg.left_box.title() == "Scale"
    # right column: Attribute/Condition with Fluid attribute
    assert dlg.attr_panel.title() == "Attribute/Condition"
    assert dlg.attr_panel.attribute.currentText() == "Fluid"
    assert not dlg.attr_panel.attribute.isEnabled()
    assert dlg.attr_panel.material_name() == "air(incompressible/20C)"
    assert dlg.attr_panel.monitor_chk.isChecked()
    # Calculate Part Region button (was "CAD Data Size")
    assert dlg.btn_cad.text() == "Calculate Part Region"
    dlg.close()


def test_domain_dialog_extend_per_axis(dlg_pieces):
    """[Extend surroundings] grows min/max per axis on apply; Cancel
    restores the original domain."""
    cab_dialogs, model, viewer = dlg_pieces
    before = cab_domain.domain_from_xml(model)
    dlg = cab_dialogs.DomainDialog(model, None, [], viewer)
    dlg.extend_chk.setChecked(True)
    dlg.extend_spins["xmin"].setValue(5.0)
    dlg.extend_spins["zmax"].setValue(7.0)
    dlg._apply(True)                      # preview: applies, stays open
    spec = cab_domain.domain_from_xml(model)
    assert spec.xyz_min[0] == pytest.approx(before.xyz_min[0] - 5.0)
    assert spec.xyz_max[2] == pytest.approx(before.xyz_max[2] + 7.0)
    assert spec.xyz_min[1] == pytest.approx(before.xyz_min[1])
    dlg._revert()
    restored = cab_domain.domain_from_xml(model)
    assert restored.xyz_min == pytest.approx(before.xyz_min)
    assert restored.xyz_max == pytest.approx(before.xyz_max)
    dlg.close()


def test_domain_dialog_monitor_and_color(dlg_pieces):
    """Attribute/Condition panel writes <monitor> and <color>."""
    cab_dialogs, model, viewer = dlg_pieces
    dlg = cab_dialogs.DomainDialog(model, None, [], viewer)
    dlg.attr_panel.monitor_chk.setChecked(False)
    dlg.color_btn.set_rgba((255, 0, 0, 255))
    dlg._apply(True)
    assert model.domain_monitor() is False
    assert model.domain_color() == (255, 0, 0, 255)
    dlg._revert()
    assert model.domain_monitor() is True
    assert model.domain_color() == (0, 255, 255, 255)
    dlg.close()


def test_domain_dialog_rename_updates_regions(dlg_pieces):
    """Renaming the domain fixes the six face_list region refs."""
    cab_dialogs, model, viewer = dlg_pieces
    dlg = cab_dialogs.DomainDialog(model, None, [], viewer)
    dlg.name_edit.setText("Domain(main)")
    dlg._apply(True)
    from cabxml import _children, _first
    ar = model.analysis_region()
    assert model.domain_name() == "Domain(main)"
    for reg in _children(ar, "region"):
        assert _first(reg, "base").text.strip() == "Domain(main)"
        assert _first(reg, "face").text.strip().startswith("Domain(main),")
    dlg._revert()
    assert model.domain_name() == "Domain(cuboid)"
    dlg.close()


def test_material_list_dialog(dlg_pieces):
    """STpre [List of Materials] tree: groups + Set selection."""
    cab_dialogs, model, viewer = dlg_pieces
    from cabxml import PropertyModel, parse_property
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    prop_member = next((m for m in archive.members
                        if m.name.endswith("_property.xml")), None)
    if prop_member is None:
        pytest.skip("box.cab has no property member")
    props = PropertyModel(parse_property(prop_member.data))
    names = props.material_names()
    assert names, "material library must not be empty"
    dlg = cab_dialogs.MaterialListDialog(
        props, viewer, current=names[0], part_name="Cuboid1")
    assert dlg.tree.topLevelItemCount() >= 5
    # solid folders from standard_property_ENG.xml
    tops = [dlg.tree.topLevelItem(i).text(0)
            for i in range(dlg.tree.topLevelItemCount())]
    assert "pure_metal" in tops
    assert "insulator" in tops
    assert dlg.part_edit.text() == "Cuboid1"
    # pick first material under first non-empty group
    picked = None
    for i in range(dlg.tree.topLevelItemCount()):
        g = dlg.tree.topLevelItem(i)
        if g.childCount():
            picked = g.child(0)
            break
    assert picked is not None
    dlg.tree.setCurrentItem(picked)
    dlg._on_tree_click(picked, 0)
    assert dlg.selected_material() == picked.text(0)
    dlg.close()


def test_part_dialog_edit(dlg_pieces):
    """PartDialog on the framework: rename + material + monitor."""
    cab_dialogs, model, viewer = dlg_pieces
    dlg = cab_dialogs.PartDialog(model, None, "box", viewer)
    assert dlg.name_edit.text() == "box"
    assert set(dlg._buttons) == {"Preview", "Apply", "OK", "Cancel"}
    dlg.name_edit.setText("box2")
    dlg.attr_panel.set_material("newmat")
    dlg.attr_panel.monitor_chk.setChecked(False)
    dlg._on_apply()
    assert model.find_part("box") is None
    part = model.find_part("box2")
    assert part is not None
    from cabxml import _first
    assert _first(part, "property").text.strip() == "newmat"
    assert _first(part, "monitor").text.strip() == "F"
    dlg.close()


def test_part_double_click_opens_dialog(qapp, monkeypatch):
    """Double-click a part in the tree opens the part dialog (M5)."""
    import cab_gui
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer.tree_view.populate(model, archive.members)
    opened = []
    monkeypatch.setattr(viewer, "_part_dialog",
                        lambda name: opened.append(name))
    item = viewer.tree_view.find_part_item("box")
    assert item is not None
    viewer.tree_view._on_double_click(item, 0)
    assert opened == ["box"]


def test_framework_base_smoke(qapp):
    """StpreDialogBase: header, optional name row, custom buttons."""
    import cab_dialogs

    class Demo(cab_dialogs.StpreDialogBase):
        def _build_left(self, lay):
            from PyQt5.QtWidgets import QLabel
            lay.addWidget(QLabel("demo", self))

    dlg = Demo("Demo", "Demo Caption", icon="cube",
               attribute_panel=cab_dialogs.AttributePanel(
                   attributes=("Obstacle", "Solid"), heat_source=True,
                   virtual_part=True))
    assert dlg.windowTitle() == "Demo"
    assert dlg.header.caption_label.text() == "Demo Caption"
    assert dlg.attr_panel.heat_chk is not None
    assert dlg.attr_panel.virtual_chk is not None
    assert set(dlg._buttons) == {"Preview", "Apply", "OK", "Cancel"}
    dlg.close()

    bare = Demo("Bare", "Bare", name_row=False, attribute_panel=None,
                buttons=("OK", "Cancel"))
    assert bare.name_edit is None and bare.color_btn is None
    assert bare.attr_panel is None
    assert set(bare._buttons) == {"OK", "Cancel"}
    bare.close()

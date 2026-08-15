"""M2: computational domain tests (cab_domain + GUI dialog)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

import cab_domain
from cab_container import CabArchive
from cabxml import StpreModel, parse_stpre

ROOT = Path(__file__).resolve().parents[1]
EX4E = ROOT / "tests" / "ex4_e" / "ex4_e.xml"
BOX = ROOT / "tests" / "box.cab"
BOX_XT = ROOT / "tests" / "box" / "box_all.x_t"


def _model(path: Path) -> StpreModel:
    return StpreModel(parse_stpre(path.read_bytes()))


def test_domain_read_ex4e():
    model = _model(EX4E)
    spec = cab_domain.domain_from_xml(model)
    assert spec is not None
    assert spec.unit == "mm"
    np.testing.assert_allclose(spec.xyz_min,
                               (-100.0, -100.0, -100.1375493649))
    np.testing.assert_allclose(
        spec.xyz_max,
        (150.0, 298.15528128089, 315.0), atol=1e-6)
    assert spec.material == "air(incompressible/20C)"


def test_domain_apply_roundtrip():
    model = _model(EX4E)
    spec = cab_domain.DomainSpec(
        coordinate="cartesian", unit="mm",
        xyz_min=(0.0, 1.0, 2.0), xyz_max=(50.0, 61.0, 72.0),
        material="air(incompressible/20C)")
    assert cab_domain.apply_domain(model, spec) is True
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    again = cab_domain.domain_from_xml(reparsed)
    assert again is not None
    np.testing.assert_allclose(again.xyz_min, (0.0, 1.0, 2.0))
    np.testing.assert_allclose(again.xyz_max, (50.0, 61.0, 72.0))
    assert again.material == spec.material
    # face_list regions must survive
    ar = reparsed.analysis_region()
    from cabxml import _children
    assert len(_children(ar, "region")) == 6


def test_ensure_domain_creates():
    raw = (b"\xef\xbb\xbf<?xml version=\"1.0\"?>\n"
           b"<stpre>\n</stpre>\n")
    model = StpreModel(parse_stpre(raw))
    assert model.analysis_region() is None
    el = model.ensure_domain(base=(0, 0, 0), size=(10, 20, 30),
                             material="air")
    assert el is not None
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    spec = cab_domain.domain_from_xml(reparsed)
    assert spec is not None
    np.testing.assert_allclose(spec.xyz_max, (10.0, 20.0, 30.0))
    assert spec.material == "air"


def test_part_bounds_box():
    import cab_import
    pytest.importorskip("cab_import")
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    bodies = cab_import.import_xt_file(BOX_XT)
    lo, hi = cab_domain.part_bounds(model, [b.tess for b in bodies])
    np.testing.assert_allclose(lo, (0.0, 0.0, 0.0), atol=1e-12)
    np.testing.assert_allclose(hi, (0.01, 0.01, 0.01), atol=1e-12)


def test_domain_dialog_smoke(qapp):
    import cab_import
    pytest.importorskip("cab_gui")
    import cab_gui
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    if not cab_import.available():
        pytest.skip("pskernel not installed")
    bodies = cab_import.import_xt_file(BOX_XT)
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = [b.tess for b in bodies]
    dlg = cab_gui._DomainDialog(model, None, viewer._cad_meshes, viewer)
    assert dlg.unit.currentText() in ("mm", "m", "cm")
    dlg._cad_data_size()
    assert dlg.spins["xmin"].value() == pytest.approx(0.0, abs=1e-6)
    assert dlg.spins["xmax"].value() == pytest.approx(10.0, abs=1e-4)
    dlg._apply(True)  # preview must not close the dialog
    dlg._revert()
    dlg.close()


def test_domain_tree_double_click_and_reference(qapp, monkeypatch):
    import cab_gui
    pytest.importorskip("cab_gui")
    archive = CabArchive.parse((ROOT / "tests" / "box.cab").read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer.tree_view.populate(model, archive.members)

    def find(kind):
        tree = viewer.tree_view.layout_tree

        def walk(item):
            data = item.data(0, 0x0100)  # Qt.UserRole
            if data and data[0] == kind:
                return item
            for i in range(item.childCount()):
                hit = walk(item.child(i))
                if hit is not None:
                    return hit
            return None

        for i in range(tree.topLevelItemCount()):
            hit = walk(tree.topLevelItem(i))
            if hit is not None:
                return hit
        return None

    # double-click on Domain(cuboid) opens the domain dialog
    opened = []
    monkeypatch.setattr(viewer, "_domain_dialog",
                        lambda: opened.append("domain"))
    domain_item = find("domain")
    assert domain_item is not None
    viewer.tree_view._on_double_click(domain_item, 0)
    assert opened == ["domain"]

    # right-click Reference on domain also opens the dialog
    viewer._on_context_action("refer", "domain", "Domain(cuboid)")
    assert opened == ["domain", "domain"]

    # double-click on mesh block opens the mesh-block dialog
    monkeypatch.setattr(viewer, "_mesh_block_dialog",
                        lambda: opened.append("grid"))
    mb_item = find("mesh_block")
    assert mb_item is not None
    viewer.tree_view._on_double_click(mb_item, 0)
    assert opened == ["domain", "domain", "grid"]


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_domain_dialog_cylindrical_labels(qapp):
    """P0-2: DomainDialog shows R/theta/Z columns for cylindrical domains."""
    pytest.importorskip("cab_gui")
    import cab_gui
    import cab_domain
    archive = CabArchive.parse(BOX.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    xml_member = next(m for m in archive.members if m.name == xml_name)
    model = StpreModel(parse_stpre(xml_member.data))
    spec = cab_domain.DomainSpec(
        coordinate="cylindrical", unit="mm",
        xyz_min=(10.0, 0.0, 0.0), xyz_max=(50.0, 360.0, 80.0))
    cab_domain.apply_domain(model, spec)
    viewer = cab_gui.CabViewer(enable_3d=False)
    viewer.model = model
    viewer._cad_meshes = []
    dlg = cab_gui._DomainDialog(model, None, [], viewer)
    assert [l.text() for l in dlg.col_labels] == ["R", "θ", "Z"]
    assert dlg.spins["xmin"].value() == pytest.approx(10.0)
    assert dlg.spins["ymax"].value() == pytest.approx(360.0)
    # apply round-trips radius/angle/height
    dlg.spins["xmax"].setValue(60.0)
    dlg._apply(True)
    ar = model.analysis_region()
    assert ar.attrib.get("type") == "cylinder"
    assert (ar.find("radius").text or "").strip() == "10,60"
    dlg._revert()
    dlg.close()

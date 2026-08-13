"""L5: Condition Wizard low-hanging fruit (face create/edit, multi-select,
initial-purpose write-backs)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("cab_gui")


def _model():
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain()
    return m


def _value_kind(m, vtype: str, vname: str):
    for v in m.values():
        if v.attrib.get("type") != vtype:
            continue
        n = next((c for c in v if c.tag == "name"), None)
        if n is not None and (n.text or "").strip() == vname:
            k = next((c for c in v if c.tag == "kind"), None)
            return (k.text or "").strip() if k is not None else ""
    return None


def _value_param(m, vtype: str, vname: str, tag: str):
    for v in m.values():
        if v.attrib.get("type") != vtype:
            continue
        n = next((c for c in v if c.tag == "name"), None)
        if n is not None and (n.text or "").strip() == vname:
            p = next((c for c in v if c.tag == tag), None)
            return (p.text or "").strip() if p is not None else None
    return None


def _bound_regions(m, vname: str) -> list[str]:
    out = []
    for c in m.conditions():
        v = next((ch for ch in c if ch.tag == "value"), None)
        if v is None or (v.text or "").strip() != vname:
            continue
        r = next((ch for ch in c if ch.tag == "region"), None)
        if r is not None:
            out.append((r.text or "").strip())
    return out


def test_write_face_region_roundtrip():
    from cab_cwizard_pages import _CwSourcePage
    from cabxml import StpreModel, _first, parse_stpre
    m = _model()
    assert _CwSourcePage._write_face_region(
        m, "FaceA", "Xmin", 0.1, 0.9, 0.2, 0.8)
    ar = m.analysis_region()
    found = None
    for r in list(ar):
        n = _first(r, "name")
        if n is not None and (n.text or "").strip() == "FaceA":
            found = r
    assert found is not None
    assert _first(found, "parent").text.strip() == "Xmin"
    assert float(_first(found, "u0").text.strip()) == pytest.approx(0.1)
    assert float(_first(found, "v1").text.strip()) == pytest.approx(0.8)
    m2 = StpreModel(parse_stpre(m.doc.serialize()))
    ar2 = m2.analysis_region()
    names = [(r, _first(r, "name").text.strip())
             for r in list(ar2)
             if _first(r, "name") is not None]
    assert "FaceA" in {n for _, n in names}


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_source_page_multi_select_regions(qapp):
    from PyQt5.QtCore import QItemSelectionModel
    from PyQt5.QtWidgets import QTableWidgetItem
    from cab_cwizard_pages import _CwSourcePage
    m = _model()
    page = _CwSourcePage(m)
    page.area_table.setRowCount(3)
    for i, name in enumerate(("Xmin", "Xmax", "Ymin")):
        page.area_table.setItem(i, 0, QTableWidgetItem(name))
        page.area_table.setItem(i, 2, QTableWidgetItem("DomainBoundary"))
    sm = page.area_table.selectionModel()
    model = page.area_table.model()
    sm.select(model.index(0, 0), QItemSelectionModel.Select
              | QItemSelectionModel.Rows)
    sm.select(model.index(2, 0), QItemSelectionModel.Select
              | QItemSelectionModel.Rows)
    regions = page._selected_regions(page.area_table, True)
    assert {r[0] for r in regions} == {"Xmin", "Ymin"}
    page.close()


def test_purpose_enclosure_writeback(qapp):
    from cab_iwizard_pages import _IwPurposePage
    m = _model()
    page = _IwPurposePage(m, log_fn=lambda *_: None)
    page.purpose["internal_enclosure"].setChecked(True)
    page.enc_a.setValue(1.3)
    page.enc_b.setValue(0.25)
    page.enc_eps.setValue(0.9)
    page.apply_boundary(m)
    assert _value_kind(m, "heat_transfer", "enc_top") == \
        "enclosure_heat_release"
    assert _value_param(m, "heat_transfer", "enc_top", "a") == "1.3"
    assert _bound_regions(m, "enc_top") == ["Zmax"]
    assert set(_bound_regions(m, "enc_side")) == {
        "Xmin", "Xmax", "Ymin", "Ymax"}


def test_purpose_buildings_power_law_writeback(qapp):
    from cab_iwizard_pages import _IwPurposePage
    m = _model()
    page = _IwPurposePage(m, log_fn=lambda *_: None)
    page.purpose["external_buildings"].setChecked(True)
    page.build_dir.setCurrentText("+X")
    page.build_h.setValue(10.0)
    page.build_exp.setValue(0.25)
    page.build_vel.setValue(2.0)
    page.apply_boundary(m)
    assert _value_kind(m, "flux", "bld_inlet") == "power_law"
    assert _value_param(m, "flux", "bld_inlet", "reference_height") == "10"
    assert _value_param(m, "flux", "bld_inlet", "exponent") == "0.25"
    assert _bound_regions(m, "bld_inlet") == ["Xmin"]
    assert _bound_regions(m, "bld_outlet") == ["Xmax"]


def test_flux_face_duplicate_check():
    """L7.4: duplicate flux conditions on one face are reported."""
    from cab_mesh import find_flux_face_duplicates
    m = _model()
    m.upsert_value("flux", "inlet_a", [("kind", "fixed_vel", None)])
    m.upsert_value("flux", "inlet_b", [("kind", "total_pres", None)])
    m.bind_condition("region", "Xmin", "inlet_a")
    m.bind_condition("region", "Xmin", "inlet_b")
    assert find_flux_face_duplicates(m) == [
        ("Xmin", ["inlet_a", "inlet_b"])]
    m2 = _model()
    m2.upsert_value("flux", "inlet_a", [("kind", "fixed_vel", None)])
    m2.bind_condition("region", "Xmin", "inlet_a")
    assert find_flux_face_duplicates(m2) == []

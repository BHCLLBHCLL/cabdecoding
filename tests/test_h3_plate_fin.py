"""H3: plate-fin deep fields — official STpre schema (exA17-1a.cab
放熱フィン) wired through storage (cabxml._SPECIAL_PARAM_FIELDS), the
SpecialParamsPanel and the geometry proxy.

Corpus schema (exA17-1a): <fin unit=mm>2</fin> <space unit=mm>7.5</space>
<depth unit=mm>0.8</depth> <nfin>5</nfin> <row_axis>+X</row_axis>
<def_axis>+Z</def_axis> — note STpre stores SCALARS here while
card_guide stores space/depth as 2-vectors.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


@pytest.fixture(scope="module")
def qapp():
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([sys.argv[0]])
    yield app


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _plate_fin_model():
    m = _model()
    assert m.add_part(name="放熱フィン", kind="plate_fin",
                      attribute="solid")
    el = m.find_part("放熱フィン")
    assert el is not None
    return m, el


def test_official_schema_roundtrip():
    """set_part_params with exA17-1a values -> part_params returns the
    scalar fields; elements carry mm units like the official file."""
    m, _el = _plate_fin_model()
    assert m.set_part_params("放熱フィン", {
        "fin": 2.0, "space": 7.5, "depth": 0.8, "nfin": 5,
        "row_axis": "+X", "def_axis": "+Z",
    })
    params = m.part_params("放熱フィン")
    assert params == {
        "fin": 2.0, "space": 7.5, "depth": 0.8, "nfin": 5,
        "row_axis": "+X", "def_axis": "+Z",
    }
    el = m.find_part("放熱フィン")
    assert el.findtext("fin").strip() == "2"
    assert el.find("fin").attrib.get("unit") == "mm"
    assert el.findtext("space").strip() == "7.5"
    assert el.findtext("nfin").strip() == "5"
    assert el.findtext("row_axis").strip() == "+X"


def test_partial_write_keeps_other_fields():
    m, _el = _plate_fin_model()
    m.set_part_params("放熱フィン", {"fin": 1.2, "nfin": 8})
    m.set_part_params("放熱フィン", {"space": 6.0})
    params = m.part_params("放熱フィン")
    assert params["fin"] == 1.2 and params["nfin"] == 8
    assert params["space"] == 6.0


def test_unknown_field_rejected():
    m, _el = _plate_fin_model()
    assert not m.set_part_params("放熱フィン", {"bogus": 1.0})


def test_special_params_panel_load_commit(qapp):
    """SpecialParamsPanel shows the six plate-fin rows and round-trips
    the official values."""
    from cab_dialogs import SpecialParamsPanel
    m, _el = _plate_fin_model()
    m.set_part_params("放熱フィン", {
        "fin": 2.0, "space": 7.5, "depth": 0.8, "nfin": 5,
        "row_axis": "+X", "def_axis": "+Z",
    })
    panel = SpecialParamsPanel(m, "放熱フィン")
    panel.load()
    labels = [panel.edits[k] for k in panel.edits]
    assert len(panel.edits) == 6
    fin_spin = panel.edits[("fin", None)]
    assert fin_spin.value() == pytest.approx(2.0)
    nfin = panel.edits[("nfin", None)]
    assert nfin.value() == 5
    row_axis = panel.edits[("row_axis", None)]
    assert row_axis.currentText() == "+X"
    # commit a change and read back
    fin_spin.setValue(3.5)
    assert panel.commit()
    assert m.part_params("放熱フィン")["fin"] == pytest.approx(3.5)


def test_geometry_reads_official_keys():
    """Part tessellation consumes nfin/fin/space/depth (legacy
    fin_count/fin_thickness still honoured)."""
    from cab_parts import tess_for_part
    m, el = _plate_fin_model()
    for tag, text, unit in (("base", "0,0,0", "mm"),
                            ("size", "40,40,16", "mm"),
                            ("fin", "2", "mm"), ("space", "7.5", "mm"),
                            ("depth", "0.8", "mm"), ("nfin", "5", None)):
        from xml.etree import ElementTree as ET
        c = ET.SubElement(el, tag)
        c.text = f" {text} "
        if unit:
            c.attrib["unit"] = unit
    tess = tess_for_part(m.parts()[0])
    assert tess is not None
    # legacy fallback path
    for c in list(el):
        if c.tag in ("fin", "nfin", "space", "depth"):
            el.remove(c)
    from xml.etree import ElementTree as ET
    c = ET.SubElement(el, "fin_count")
    c.text = " 3 "
    tess2 = tess_for_part(m.parts()[0])
    assert tess2 is not None

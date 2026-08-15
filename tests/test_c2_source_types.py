"""C2: Source Condition value-type round-trip (moisture/smoke sources)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


@pytest.mark.parametrize("vtype", ["moisture_source", "smoke_source"])
def test_source_type_roundtrip(vtype):
    model = StpreModel(parse_stpre(new_stpre_bytes("demo")))
    assert model.upsert_value(vtype, f"src_{vtype}", [
        ("source", "1.5", "kg/s"),
    ]) is True
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    val = reparsed.find_value(f"src_{vtype}")
    assert val is not None
    assert val.attrib.get("type") == vtype
    source = next((c.text for c in val if c.tag == "source"), None)
    assert source == "1.5"


def test_source_vol_types_include_new():
    import cab_cwizard_pages as cw
    assert "moisture_source" in cw._SRC_VOL_TYPES
    assert "smoke_source" in cw._SRC_VOL_TYPES
    assert "humidification" in cw._SRC_VOL_TYPES
    assert "plant_canopy" in cw._SRC_VOL_TYPES
    assert "driver" in cw._SRC_VOL_TYPES


@pytest.mark.parametrize("vtype,fields", [
    ("humidification", [("source", "0.2", "kg/s")]),
    ("plant_canopy", [("leaf_area_density", "0.5", "1/m"),
                       ("drag_coefficient", "0.2", "")]),
    ("driver", [("velocity", "1.0", "m/s"),
                ("frequency", "2.0", "Hz")]),
])
def test_source_type_roundtrip_extended(vtype, fields):
    model = StpreModel(parse_stpre(new_stpre_bytes("demo")))
    assert model.upsert_value(vtype, f"src_{vtype}", fields) is True
    reparsed = StpreModel(parse_stpre(model.doc.serialize()))
    val = reparsed.find_value(f"src_{vtype}")
    assert val is not None
    assert val.attrib.get("type") == vtype

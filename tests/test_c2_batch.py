"""§23 C2 batch: humidity boundary conditions — official exA05-2
``<value type="humidity">`` storage and the HUMW_REGION card emission."""
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


def test_humw_region_matches_official_layout():
    """type=2 humidity boundary -> HUMW_REGION transfer/wallhumidity card
    per bound region, verbatim exA05-2 layout (湿度1 / Xmin面)."""
    from s_export import build_sdat
    m = _model()
    assert m.upsert_value("humidity", "湿度1", [
        ("kind", "boundary", None),
        ("type", "2", None),
        ("param1", "0.0244", "m/s"),
        ("param2", "0.66", None),
    ])
    for face in ("Xmin面", "Xmax面"):
        assert m.bind_condition("region", face, "湿度1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("HUMW_REGION")
    block = lines[i:i + 6]
    assert block == [
        "HUMW_REGION",
        "transfer  wallhumidity    0   ! 湿度1",
        f"{2.44e-02:26.14e}",
        f"{6.60e-01:26.14e}",
        "   Xmin面",
        "   /",
    ]
    # one card per bound region, section terminated
    cards = [l for l in lines if l.startswith("transfer  wallhumidity")]
    assert len(cards) == 2
    assert lines.index("HUMW_REGION") < lines.index("FOUT")


def test_humw_region_absent_without_type2():
    """type=1 (region-pair family) does not emit — prefix discriminator
    (lewislaw/diffusion) has no XML evidence; section omitted."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("humidity", "湿度2", [
        ("kind", "boundary", None),
        ("type", "1", None),
        ("param1", "-1.5", "m/s"),
    ])
    m.bind_condition("region", "領域ペア1", "湿度2")
    assert "HUMW_REGION" not in build_sdat(m, _props())


def test_humidity_condition_xml_roundtrip():
    m = _model()
    m.upsert_value("humidity", "湿度1", [
        ("kind", "boundary", None),
        ("type", "2", None),
        ("param1", "0.0244", "m/s"),
        ("param2", "0.66", None),
    ])
    m.bind_condition("region", "Xmin面", "湿度1")
    m2 = StpreModel(parse_stpre(m.doc.serialize()))
    val = m2.find_value("湿度1")
    assert val is not None and val.attrib.get("type") == "humidity"
    kids = {c.tag: (c.text or "").strip() for c in val}
    assert kids == {"name": "湿度1", "kind": "boundary", "type": "2",
                    "param1": "0.0244", "param2": "0.66"}
    assert m2.condition_value("region", "Xmin面") == "湿度1"


def test_humidity_page_commit_and_table(qapp):
    """The Humidity CW page's _commit_humidity creates the official value
    shape and the table lists it with bound regions."""
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwHumidityPage(m)
    try:
        assert page._commit_humidity(
            "湿度1", 2, 0.0244, 0.66, "Xmin面")
        val = m.find_value("湿度1")
        assert val is not None and val.attrib.get("type") == "humidity"
        assert m.condition_value("region", "Xmin面") == "湿度1"
        assert page.hum_table.rowCount() == 1
        assert page.hum_table.item(0, 0).text() == "湿度1"
        assert page.hum_table.item(0, 4).text() == "Xmin面"
        # constant moisture flux: type=1, negative = solid -> fluid
        assert page._commit_humidity("湿度F", 1, -1.5, None, "Xmax面")
        val = m.find_value("湿度F")
        kids = {c.tag: (c.text or "").strip() for c in val}
        assert kids["type"] == "1" and kids["param1"] == "-1.5"
        assert page.hum_table.rowCount() == 2
        # delete removes value + bindings
        page.hum_table.selectRow(0)
        page._hum_delete()
        assert m.find_value("湿度1") is None
        assert m.condition_value("region", "Xmin面") in ("", None)
        assert page.hum_table.rowCount() == 1
    finally:
        page.deleteLater()

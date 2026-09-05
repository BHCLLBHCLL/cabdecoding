"""I2: DRIVER_REGION (velocity / script forms, exB18/exB20a) and
CNRM_MATERIAL (exA14-2/exB12) — emitters plus UI wiring on the LES and
Diffusion pages."""
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


def _lines(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def test_driver_region_velocity_form():
    """exB20a — fully-developed/positive_x/velocity header + 29-wide
    inflow velocity + region + double terminator."""
    m = _model()
    m.ensure_analysis_etc_section("les_driver")
    el = m.root.find("analysis_etc/les_driver")
    el.attrib.update(stage="fully-developed", direction="positive_x",
                     kind="velocity", name="条件9", value="0.08346",
                     region="Driver")
    lines = _lines(m)
    i = lines.index("DRIVER_REGION")
    assert lines[i:i + 6] == [
        "DRIVER_REGION",
        "   fully-developed  positive_x  velocity  ! 条件9",
        f"{0.08346:29.14e}",
        "   Driver",
        "   /",
        "/",
    ]


def test_driver_region_script_form():
    """exB18 — developing/script header + z-direction line + params +
    '#' marker + region + double terminator."""
    m = _model()
    m.ensure_analysis_etc_section("les_driver")
    el = m.root.find("analysis_etc/les_driver")
    el.attrib.update(stage="developing", direction="positive_x",
                     kind="script", name="条件10",
                     direction_line="z-direction", params="1,0",
                     region="ドライバー領域")
    lines = _lines(m)
    i = lines.index("DRIVER_REGION")
    assert lines[i:i + 8] == [
        "DRIVER_REGION",
        "   developing  positive_x  script  ! 条件10",
        "    z-direction",
        "1   0",
        "#",
        "   ドライバー領域",
        "   /",
        "/",
    ]


def test_cnrm_material_rows():
    """exA14-2 (1->2) / exB12 (1->1) — two 12-wide ints, '/'-closed."""
    m = _model()
    m.ensure_analysis_etc_section("cnrm")
    cn = m.root.find("analysis_etc/cnrm")
    import xml.etree.ElementTree as ET
    r = ET.SubElement(cn, "row")
    r.attrib.update(no="1", val="2")
    lines = _lines(m)
    i = lines.index("CNRM_MATERIAL")
    assert lines[i:i + 2] == ["CNRM_MATERIAL", f"{1:12d}{2:12d}"]
    assert lines[i + 2] == "/"
    # header-area position: right before CXYZ
    assert i < lines.index("CXYZ")


def test_les_page_driver_group(qapp):
    from cab_cwizard_pages import _CwLesPage
    m = _model()
    page = _CwLesPage(m)
    page.drv_stage.setCurrentIndex(page.drv_stage.findData("developing"))
    page.drv_kind.setCurrentIndex(page.drv_kind.findData("script"))
    page.drv_name.setText("条件10")
    page.drv_direction_line.setText("z-direction")
    page.drv_params.setText("1,0")
    page.drv_region.setText("ドライバー領域")
    page.apply()
    el = m.root.find("analysis_etc/les_driver")
    assert el is not None and el.attrib["kind"] == "script"
    lines = _lines(m)
    i = lines.index("DRIVER_REGION")
    assert lines[i + 1] == "   developing  positive_x  script  ! 条件10"
    assert lines[i + 3] == "1   0"
    page2 = _CwLesPage(m)
    assert page2.drv_region.text() == "ドライバー領域"


def test_diffusion_page_cnrm_group(qapp):
    from cab_cwizard_pages import _CwDiffusionPage
    m = _model()
    page = _CwDiffusionPage(m)
    page._cnrm_add("1", "2")
    page.apply()
    cn = m.root.find("analysis_etc/cnrm")
    assert cn is not None
    assert cn.find("row").attrib == {"no": "1", "val": "2"}
    page2 = _CwDiffusionPage(m)
    assert page2.cnrm_table.rowCount() == 1
    assert page2.cnrm_table.item(0, 1).text() == "2"


def test_absent_without_storage():
    lines = _lines(_model())
    assert "DRIVER_REGION" not in lines
    assert "CNRM_MATERIAL" not in lines

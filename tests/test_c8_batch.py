"""§23 C8: Design Space — TOPOPT_REGION emission (exA28-1_step2
evidence) and the topology page commit API."""
from __future__ import annotations

import pytest

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


@pytest.fixture(scope="module")
def qapp():
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys as _sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([_sys.argv[0]])
    yield app


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def test_topopt_region_matches_official_layout():
    """topo_obj_func + topo_design_space bound to Design_space parts emit
    the exA28-1_step2 TOPOPT_REGION card verbatim."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("topo_obj_func", "体積目的関数1", [
        ("kind", "volumetric_object_function", None),
        ("obj1_func_type", "1", None),
        ("obj1_constraint_base", "0", None),
        ("obj2_func_type", "0", None),
        ("obj2_set_tolerance", "F", None),
        ("obj2_tolerance", "0", None)])
    m.upsert_value("topo_design_space", "設計空間1", [
        ("vol_constraint_type", "upper", None),
        ("vol_constraint", "0.12", None)])
    m.bind_condition("parts", "Design_space", "体積目的関数1")
    m.bind_condition("parts", "Design_space", "設計空間1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("TOPOPT_REGION")
    assert lines[i:i + 7] == [
        "TOPOPT_REGION",
        "objective_and_constraint    0   ! 体積目的関数1",
        f"{1:15d}{1:12d}",
        f"{0.0:29.14e}" + f"{0.12:26.14e}",
        f"{0.0:29.14e}",
        "   Design_space",
        "   /",
    ]
    # one region line per bound parts (both values bind the same part)
    assert lines[i + 7] == "   Design_space" and lines[i + 8] == "   /"
    assert lines[i + 9] == "/"
    assert lines.index("TOPOPT_REGION") < lines.index("MEIX_VAR")


def test_topopt_region_absent_without_design_space():
    from s_export import build_sdat
    assert "TOPOPT_REGION" not in build_sdat(_model(), _props())


def test_topology_page_design_space_commit(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwTopologyOptiPage(m)
    try:
        assert page._commit_design_space(
            "設計空間1", "Design_space", "upper", 0.12)
        val = m.find_value("設計空間1")
        assert val is not None
        assert val.attrib.get("type") == "topo_design_space"
        kids = {c.tag: (c.text or "").strip() for c in val}
        assert kids["vol_constraint_type"] == "upper"
        assert kids["vol_constraint"] == "0.12"
        assert m.condition_value("parts", "Design_space") == "設計空間1"
    finally:
        page.deleteLater()

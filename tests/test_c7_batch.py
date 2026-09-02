"""§23 C7 batch: 6DOF rigid-body motion (MOVB_CONTROL dynamical entry +
DYNA_MOTION, exA09-4 evidence) and the storage-only repulsion / moving-
object mass transfer conditions."""
from __future__ import annotations

import numpy as np
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


def test_6dof_emits_dynamical_and_dyn_motion():
    """body_move_6dof bound via <parts> emits the exA09-4 MOVB_CONTROL
    dynamical entry + DYNA_MOTION block verbatim."""
    from s_export import build_sdat
    m = _model()
    m.add_part(name="氷", kind="cube", attribute="solid")
    assert m.upsert_value("body_move_6dof", "移動物体1", [
        ("label", "condition1", None),
        ("move_kind", "free", None),
        ("initial_v_x", "0", "m/s"), ("force_x", "0", "N"),
        ("initial_v_y", "0", "m/s"), ("force_y", "0", "N"),
        ("initial_v_z", "0", "m/s"), ("force_z", "0", "N"),
        ("rotate_kind", "free", None),
    ])
    assert m.bind_condition("parts", "氷", "移動物体1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("MOVB_CONTROL")
    assert lines[i:i + 4] == [
        "MOVB_CONTROL",
        "dynamical    0   ! 移動物体1",
        " condition1",
        "   氷",
    ]
    j = lines.index("DYNA_MOTION")
    assert lines[j:j + 10] == [
        "DYNA_MOTION",
        "condition1",
        "translation",
        "    unrestricted",
        "rotation",
        "    unrestricted",
        "external_force",
        " " * 9 + "      ".join(f"{0.0:.14e}" for _ in range(3)),
        "   /",
        "   /",
    ]
    assert lines[j + 10] == "/"


def test_6dof_fixed_kinds():
    """move_kind/rotate_kind != free -> 'fixed' lines."""
    from s_export import build_sdat
    m = _model()
    m.add_part(name="b1", kind="cube", attribute="solid")
    m.upsert_value("body_move_6dof", "MO1", [
        ("label", "cond", None),
        ("move_kind", "fixed", None),
        ("rotate_kind", "fixed", None),
        ("force_x", "1", "N"), ("force_y", "2", "N"),
        ("force_z", "3", "N"),
    ])
    m.bind_condition("parts", "b1", "MO1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    j = lines.index("DYNA_MOTION")
    assert lines[j + 2:j + 6] == ["translation", "    fixed",
                                  "rotation", "    fixed"]
    assert lines[j + 7] == " " * 9 + "      ".join(
        f"{v:.14e}" for v in (1.0, 2.0, 3.0))


def test_moving_body_page_commits(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwMovingBodyPage(m)
    try:
        assert page._commit_6dof("移動物体1", "condition1", "氷")
        val = m.find_value("移動物体1")
        assert val is not None
        assert val.attrib.get("type") == "body_move_6dof"
        kids = {c.tag: (c.text or "").strip() for c in val}
        assert kids["label"] == "condition1"
        assert kids["move_kind"] == "free"
        assert m.condition_value("parts", "氷") == "移動物体1"
        assert page._commit_repulsion("Rep1", "氷", 1.5)
        val = m.find_value("Rep1")
        assert val.attrib.get("type") == "body_repulsion"
        assert page._commit_mo_mass_transfer("MoMT1", "氷", 0.02)
        val = m.find_value("MoMT1")
        assert val.attrib.get("type") == "mo_mass_transfer"
    finally:
        page.deleteLater()


def test_structural_and_cosim_disabled():
    """B-level declarations: MSC CoSim stays in the always-disabled set
    of the Analysis Types page (scFLOW-only semantics); structural
    analysis has no Analysis Types entry at all."""
    import cab_wizards
    assert "msc_cosim" in cab_wizards._CwAnalysisTypesPage._ALWAYS_DISABLED
    flat = [k for _col in cab_wizards._CwAnalysisTypesPage._TYPE_COLS
            for _label, k, _items in _col]
    assert "structural" not in flat and "structure" not in flat

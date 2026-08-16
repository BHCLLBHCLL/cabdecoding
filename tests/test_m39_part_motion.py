"""M39: moving-body (body_move) motion definition — c7.

Covers the cabxml ``part_motion`` / ``set_part_motion`` API, the PartDialog
Moving Body panel write-back and the MOVB_PARTS / MOVB_CONTROL blocks in
the SDAT exporter (official 2023.2 exercise layout).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET

import pytest

from cabxml import (PropertyModel, _first, new_property_bytes,
                    new_stpre_bytes, parse_property, parse_stpre,
                    StpreModel)

ROOT = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _model(*parts) -> StpreModel:
    m = StpreModel(parse_stpre(new_stpre_bytes()))
    m.ensure_domain(base=(0, 0, 0), size=(100, 100, 100), material="air")
    m.ensure_domain_faces()
    for name in parts:
        m.add_part(name=name, kind="cube", attribute="obstacle")
        el = m.find_part(name)
        for tag, text in (("base", "20,20,20"), ("size", "30,30,30")):
            e = ET.SubElement(el, tag)
            e.text = f" {text} "
            e.tail = "\n         "
    return m


# -- cabxml API ---------------------------------------------------------------

def test_motion_write_read_roundtrip():
    m = _model("MovingBox")
    assert m.part_motion("MovingBox") is None
    assert m.set_part_motion("MovingBox",
                             {"kind": "translate", "velocity": (0.1, 0, 0)})
    motion = m.part_motion("MovingBox")
    assert motion is not None
    assert motion["kind"] == "translate"
    assert tuple(motion["velocity"]) == (0.1, 0.0, 0.0)
    assert motion["value_name"] == "MoveBody1"
    # value + condition pair in the XML
    val = m.find_value("MoveBody1")
    assert val is not None and val.attrib.get("type") == "body_move"
    assert any(
        (_first(c, "parts") is not None
         and (_first(c, "parts").text or "").strip() == "MovingBox"
         and (_first(c, "value").text or "").strip() == "MoveBody1")
        for c in m.conditions())
    # serialize round-trip keeps the binding
    again = StpreModel(parse_stpre(m.doc.serialize()))
    m2 = again.part_motion("MovingBox")
    assert m2 is not None and m2["kind"] == "translate"
    assert tuple(m2["velocity"]) == (0.1, 0.0, 0.0)


def test_motion_rotate_and_kind_switch_clears_stale():
    m = _model("MovingBox")
    assert m.set_part_motion("MovingBox", {
        "kind": "rotate", "omega": 1.5,
        "center": (10, 20, 30), "normal": (0, 0.5, 0.86)})
    motion = m.part_motion("MovingBox")
    assert motion["omega"] == 1.5
    assert tuple(motion["center"]) == (10.0, 20.0, 30.0)
    assert tuple(motion["normal"]) == (0.0, 0.5, 0.86)
    assert motion["velocity"] is None
    # switching kind clears the other kind's fields (STpre behaviour)
    assert m.set_part_motion("MovingBox",
                             {"kind": "translate", "velocity": (1, 2, 3)})
    val = m.find_value("MoveBody1")
    assert _first(val, "omega") is None
    assert _first(val, "center") is None
    assert _first(val, "normal") is None
    # unknown kind refused
    assert m.set_part_motion("MovingBox", {"kind": "warp"}) is False
    # unknown part refused
    assert m.set_part_motion("Nope", {"kind": "translate"}) is False


def test_motion_remove():
    m = _model("MovingBox")
    m.set_part_motion("MovingBox",
                      {"kind": "coordinate", "coordinate": (5, 6, 7)})
    assert m.part_motion("MovingBox") is not None
    assert m.set_part_motion("MovingBox", None) is True
    assert m.part_motion("MovingBox") is None
    assert m.find_value("MoveBody1") is None
    assert all((_first(c, "value").text or "").strip() != "MoveBody1"
               for c in m.conditions() if _first(c, "value") is not None)
    # removing again is a no-op failure
    assert m.set_part_motion("MovingBox", None) is False


def test_rename_part_keeps_motion_binding():
    m = _model("MovingBox")
    m.set_part_motion("MovingBox", {"kind": "translate", "velocity": (1, 0, 0)})
    assert m.rename_part("MovingBox", "Wing") is True
    motion = m.part_motion("Wing")
    assert motion is not None and motion["kind"] == "translate"
    assert m.part_motion("MovingBox") is None


# -- PartDialog Moving Body panel ---------------------------------------------

def test_part_dialog_motion_writeback(qapp):
    import cab_dialogs
    m = _model("MovingBox")
    dlg = cab_dialogs.PartDialog(m, None, "MovingBox")
    assert dlg.motion._current_kind() == "none"

    idx = next(i for i, (k, _l) in enumerate(dlg.motion.KINDS)
               if k == "translate")
    dlg.motion.kind.setCurrentIndex(idx)
    for ax, v in zip("xyz", (0.25, 0.0, 0.0)):
        dlg.motion.spins["velocity"][ax].setValue(v)
    dlg._on_apply()
    motion = m.part_motion("MovingBox")
    assert motion is not None
    assert motion["kind"] == "translate"
    assert tuple(motion["velocity"]) == (0.25, 0.0, 0.0)

    # reload into a fresh dialog
    dlg2 = cab_dialogs.PartDialog(m, None, "MovingBox")
    assert dlg2.motion._current_kind() == "translate"
    assert dlg2.motion.spins["velocity"]["x"].value() == pytest.approx(0.25)

    # switching to rotate writes omega/center/normal and clears velocity
    idx = next(i for i, (k, _l) in enumerate(dlg2.motion.KINDS)
               if k == "rotate")
    dlg2.motion.kind.setCurrentIndex(idx)
    dlg2.motion.spins["omega"]["x"].setValue(1.5)
    for ax, v in zip("xyz", (50, 50, 50)):
        dlg2.motion.spins["center"][ax].setValue(v)
    for ax, v in zip("xyz", (0, 0, 1)):
        dlg2.motion.spins["normal"][ax].setValue(v)
    dlg2._on_apply()
    motion = m.part_motion("MovingBox")
    assert motion["kind"] == "rotate"
    assert motion["omega"] == pytest.approx(1.5)
    assert tuple(motion["center"]) == (50.0, 50.0, 50.0)
    assert motion["velocity"] is None

    # back to (none) removes the motion
    dlg2.motion.kind.setCurrentIndex(0)
    dlg2._on_apply()
    assert m.part_motion("MovingBox") is None


# -- SDAT export ----------------------------------------------------------------

def _sdat(m: StpreModel) -> str:
    import s_export
    props = PropertyModel(parse_property(new_property_bytes()))
    return s_export.build_sdat(m, props)


def test_s_export_no_motion_no_movb():
    text = _sdat(_model("MovingBox"))
    assert "MOVB_PARTS" not in text
    assert "MOVB_CONTROL" not in text


def test_s_export_movb_translate():
    m = _model("MovingBox")
    m.set_part_motion("MovingBox",
                      {"kind": "translate", "velocity": (0.1, 0.2, 0.3)})
    text = _sdat(m)
    assert "MOVB_PARTS" in text and "MOVB_CONTROL" in text
    lines = text.splitlines()
    # geometry block: 8 corners in m (mm / 1000), official outline order
    ip = lines.index("MOVB_PARTS")
    assert lines[ip + 1].split() == ["1", "0"]
    assert lines[ip + 2].strip() == "MovingBox"
    assert lines[ip + 5].split()[:3] == ["2.00000000000000e-02",
                                         "2.00000000000000e-02",
                                         "2.00000000000000e-02"]
    assert lines[ip + 12].split() == ["5.00000000000000e-02",
                                      "5.00000000000000e-02",
                                      "5.00000000000000e-02"]
    assert lines[ip + 13].split() == ["1", "2", "4", "3", "5", "6", "8", "7"]
    assert lines[ip + 14].strip() == "/"
    # control block: translation entry with the velocity triple
    ic = lines.index("MOVB_CONTROL")
    assert lines[ic + 1].startswith("translation    0   ! MoveBody1")
    assert lines[ic + 2].split() == ["1.00000000000000e-01",
                                     "2.00000000000000e-01",
                                     "3.00000000000000e-01"]
    assert lines[ic + 3].strip() == "MovingBox"
    assert lines[ic + 4].strip() == "/"
    assert lines[ic + 5].strip() == "/"


def test_s_export_movb_rotate_and_combined():
    m = _model("MovingBox")
    m.set_part_motion("MovingBox", {
        "kind": "rotate", "omega": 1.885,
        "center": (1060, 0, 500), "normal": (0, 0, 1)})
    text = _sdat(m)
    lines = text.splitlines()
    ic = lines.index("MOVB_CONTROL")
    assert lines[ic + 1].startswith("rotation    0   ! MoveBody1")
    params = lines[ic + 2].split()
    assert len(params) == 7
    assert float(params[0]) == pytest.approx(1.885)
    # centre converted mm -> m (official exA09-1 uses metre values)
    assert float(params[1]) == pytest.approx(1.06)
    assert float(params[2]) == pytest.approx(0.0)
    assert float(params[3]) == pytest.approx(0.5)
    assert [float(v) for v in params[4:]] == [0.0, 0.0, 1.0]

    # translate+rotate emits both entries in one MOVB_CONTROL block
    m.set_part_motion("MovingBox", {
        "kind": "translate+rotate", "velocity": (0.01, 0, 0),
        "omega": 2.0, "center": (0, 0, 0), "normal": (0, 0, 1)})
    lines = _sdat(m).splitlines()
    ic = lines.index("MOVB_CONTROL")
    kinds = [lines[ic + 1].split()[0], lines[ic + 5].split()[0]]
    assert kinds == ["translation", "rotation"]
    assert lines[ic + 8].strip() == "/"  # block close after both entries


def test_s_export_movb_coordinate():
    m = _model("MovingBox")
    m.set_part_motion("MovingBox",
                      {"kind": "coordinate", "coordinate": (10, 20, 30)})
    lines = _sdat(m).splitlines()
    ic = lines.index("MOVB_CONTROL")
    assert lines[ic + 1].startswith("coordinate    0   ! MoveBody1")
    vals = [float(v) for v in lines[ic + 2].split()]
    assert vals == pytest.approx([0.01, 0.02, 0.03])

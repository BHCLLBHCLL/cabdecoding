"""W2: named reference CS + Distance Chain as its own Option menu."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def test_named_cs_roundtrip():
    m = StpreModel(parse_stpre(new_stpre_bytes("cs")))
    assert m.coordinate_systems() == []
    assert m.upsert_coordinate_system(
        "CS1", origin=(10.0, 20.0, 30.0),
        axis_x=(1.0, 0.0, 0.0), axis_y=(0.0, 1.0, 0.0),
        axis_z=(0.0, 0.0, 1.0))
    assert m.upsert_coordinate_system("CS2", origin=(0.0, 0.0, 5.0))
    names = [c["name"] for c in m.coordinate_systems()]
    assert names == ["CS1", "CS2"]
    cs1 = m.get_coordinate_system("CS1")
    assert cs1["origin"] == (10.0, 20.0, 30.0)
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.get_coordinate_system("CS1")["origin"] == (10.0, 20.0, 30.0)
    assert again.get_coordinate_system("CS2")["origin"][2] == 5.0
    # replace in place
    assert m.upsert_coordinate_system("CS1", origin=(1.0, 2.0, 3.0))
    assert m.get_coordinate_system("CS1")["origin"] == (1.0, 2.0, 3.0)
    assert m.upsert_coordinate_system("") is False


def test_option_menu_has_distance_chain():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    import cab_gui
    app = QApplication.instance() or QApplication([])
    v = cab_gui.CabViewer(enable_3d=False)
    labels = []
    for act in v.menuBar().actions():
        menu = act.menu()
        if menu is None:
            continue
        if "Option" not in act.text():
            continue
        labels = [a.text() for a in menu.actions() if a.text()]
    assert any("Distance Chain" in t for t in labels)
    assert any(t.startswith("Distance") and "Chain" not in t for t in labels)
    assert any("Reference" in t for t in labels)
    _ = app

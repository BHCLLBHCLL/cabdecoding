"""F3 leftover: the five Air Conditioner Part models of the Pre_eng Part
pages are the ``ac_unit`` part's AC unit type options — lock their
coverage and XML persistence."""
from __future__ import annotations

import pytest

import cab_parts


# Pre_eng: St_pre_Part-Air_Conditioner_Part_<model>.html
AC_MODELS = (
    "Ceiling cassette (4 directions)",
    "Ceiling cassette (2 directions)",
    "Wall-mount unit",
    "Portable unit",
    "Outdoor unit",
)


@pytest.fixture(scope="module")
def qapp():
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys as _sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([_sys.argv[0]])
    yield app


def test_ac_unit_type_options_cover_manual_models(qapp):
    from PyQt5.QtWidgets import QComboBox
    from cabxml import StpreModel, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    dlg = cab_parts.CreatePartDialog(m, None, "ac_unit")
    try:
        combo = next(w for w in dlg.findChildren(QComboBox)
                     if any(w.itemText(i) == AC_MODELS[0]
                            for i in range(w.count())))
        items = [combo.itemText(i) for i in range(combo.count())]
        assert set(AC_MODELS) <= set(items)
    finally:
        dlg.close()
        dlg.deleteLater()


@pytest.mark.parametrize("ac_type", AC_MODELS)
def test_ac_unit_type_persists(ac_type, qapp):
    """register_primitive(ac_unit, ac_type=...) writes the XML child and
    reloads with the same value."""
    from cabxml import StpreModel, _first, new_stpre_bytes, parse_stpre
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    assert cab_parts.register_primitive(
        m, name="ac_probe", kind="ac_unit",
        params={"base": (0, 0, 0), "size": (10, 10, 5), "ac_type": ac_type},
        attribute="Solid")
    info = next(p for p in m.parts() if p.name == "ac_probe")
    el = _first(info.elem, "ac_type")
    assert el is not None and (el.text or "").strip() == ac_type
    reparsed = StpreModel(parse_stpre(m.doc.serialize()))
    el2 = _first(next(p for p in reparsed.parts()
                      if p.name == "ac_probe").elem, "ac_type")
    assert (el2.text or "").strip() == ac_type

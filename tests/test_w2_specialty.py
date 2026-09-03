"""W2: specialty part deep fields (heat_pipe / delphi / two_resistor / card_guide)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("spec")))


def test_heat_pipe_params_roundtrip():
    m = _model()
    m.add_part(name="HP1", kind="heat_pipe", attribute="solid")
    assert m.set_part_params("HP1", {
        "cooling_part": "Hot", "heat_release_part": "Cold",
        "thermal_resistance": 0.12, "max_heat_transport": 80.0,
    })
    p = m.part_params("HP1")
    assert p["cooling_part"] == "Hot"
    assert p["heat_release_part"] == "Cold"
    assert p["thermal_resistance"] == pytest.approx(0.12)
    assert p["max_heat_transport"] == pytest.approx(80.0)
    again = StpreModel(parse_stpre(m.doc.serialize()))
    q = again.part_params("HP1")
    assert q["cooling_part"] == "Hot"
    assert q["max_heat_transport"] == pytest.approx(80.0)


def test_card_guide_params_roundtrip():
    m = _model()
    m.add_part(name="CG1", kind="card_guide", attribute="solid")
    assert m.set_part_params("CG1", {
        "fin": 1.5, "space": [3.0, 4.0], "depth": [2.0, 2.5],
        "nfin": 8, "row_axis": "+X", "def_plane": "+Z",
    })
    p = m.part_params("CG1")
    assert p["nfin"] == 8 and p["fin"] == pytest.approx(1.5)
    assert p["space"] == [3.0, 4.0]
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("CG1")["nfin"] == 8


def test_two_resistor_and_multi_resistor_roundtrip():
    m = _model()
    m.add_part(name="TR1", kind="two_resistor", attribute="solid")
    m.add_part(name="MR1", kind="multi_resistor", attribute="solid")
    assert m.set_part_params("TR1", {
        "rjc": 1.2, "rjb": 4.5, "package_power": 2.0})
    assert m.set_part_params("MR1", {
        "rjc": 0.8, "rjb": 3.1, "package_power": 5.0, "n_resistors": 4})
    tr = m.part_params("TR1")
    mr = m.part_params("MR1")
    assert tr["rjc"] == pytest.approx(1.2)
    assert tr["package_power"] == pytest.approx(2.0)
    assert mr["n_resistors"] == 4
    again = StpreModel(parse_stpre(m.doc.serialize()))
    assert again.part_params("TR1")["rjb"] == pytest.approx(4.5)
    assert again.part_params("MR1")["n_resistors"] == 4


def test_delphi_thermal_nodes_roundtrip():
    m = _model()
    m.add_part(name="D1", kind="delphi", attribute="solid")
    nodes = [("Case", 1.0), ("Board", 2.5)]
    assert m.set_part_params("D1", {"nodes": nodes})
    got = m.part_params("D1")["nodes"]
    assert got[0][0] == "Case" and got[0][1] == pytest.approx(1.0)
    assert got[1][0] == "Board" and got[1][1] == pytest.approx(2.5)
    again = StpreModel(parse_stpre(m.doc.serialize()))
    g2 = again.part_params("D1")["nodes"]
    assert [n for n, _r in g2] == ["Case", "Board"]
    assert m.set_part_params("D1", {"nodes": []})
    assert "nodes" not in (m.part_params("D1") or {})


# ---- A3: peltier / slit_punching / anemostat deep-field locks ----

def test_peltier_deep_fields_roundtrip():
    """Peltier: paramV (drive voltage list), rjc/rjb (thermal resistances),
    package_power, peltier_current, peltier_delta_t round-trip."""
    import cab_parts
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="Peltier1", kind="peltier", attribute="Solid")
    info = next(p for p in m.parts() if p.name == "Peltier1")
    for tag, val in (("paramV", "15.5,17.5,10"), ("rjc", "2.5"),
                     ("rjb", "1.8"), ("package_power", "12"),
                     ("peltier_current", "3.2"),
                     ("peltier_delta_t", "65")):
        from xml.etree.ElementTree import SubElement
        c = SubElement(info.elem, tag)
        c.text = f" {val} "
    reparsed = StpreModel(parse_stpre(m.doc.serialize()))
    info2 = next(p for p in reparsed.parts() if p.name == "Peltier1")
    for tag, expected in (("paramV", "15.5,17.5,10"), ("rjc", "2.5"),
                          ("rjb", "1.8"), ("package_power", "12"),
                          ("peltier_current", "3.2"),
                          ("peltier_delta_t", "65")):
        from cabxml import _first
        el = _first(info2.elem, tag)
        assert el is not None, tag
        assert (el.text or "").strip() == expected, tag


def test_slit_punching_anemostat_roundtrip():
    """Slit punching and anemostat: base/size + direction round-trip."""
    import cab_parts
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    for name, kind in (("Slit1", "slit_punching"), ("Anemo1", "anemostat")):
        m.add_part(name=name, kind=kind, attribute="Solid")
        info = next(p for p in m.parts() if p.name == name)
        from xml.etree.ElementTree import SubElement
        for tag, val in (("base", "10,20,30"), ("size", "40,50,60"),
                         ("direction", "+Z")):
            c = SubElement(info.elem, tag)
            c.text = f" {val} "
    reparsed = StpreModel(parse_stpre(m.doc.serialize()))
    for name in ("Slit1", "Anemo1"):
        info = next(p for p in reparsed.parts() if p.name == name)
        assert info.base.strip() == "10,20,30", name
        assert info.size.strip() == "40,50,60", name

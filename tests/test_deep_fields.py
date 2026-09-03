"""D1/D2 deep-field round-trip: every specialty part's full parameter
surface survives serialize/parse."""
from __future__ import annotations

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


def _rt(m):
    return StpreModel(parse_stpre(m.doc.serialize()))


def _p(m, name):
    return next(p for p in m.parts() if p.name == name)


def test_two_resistor_full_params():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="TR1", kind="two_resistor", attribute="Solid")
    info = _p(m, "TR1")
    from xml.etree.ElementTree import SubElement
    for tag, val in (("rjc", "2.5"), ("rjb", "1.8"),
                     ("package_power", "12"), ("area", "0.01")):
        c = SubElement(info.elem, tag)
        c.text = f" {val} "
    m2 = _rt(m)
    info2 = _p(m2, "TR1")
    from cabxml import _first
    for tag, expected in (("rjc", "2.5"), ("rjb", "1.8"),
                          ("package_power", "12"), ("area", "0.01")):
        el = _first(info2.elem, tag)
        assert el is not None, tag
        assert (el.text or "").strip() == expected


def test_heat_pipe_full_params():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="HP1", kind="heat_pipe", attribute="Solid")
    info = _p(m, "HP1")
    from xml.etree.ElementTree import SubElement
    for tag, val in (("base", "10,20,30"), ("size", "100,10,10"),
                     ("capillary_limit", "50"), ("max_heat", "200")):
        c = SubElement(info.elem, tag)
        c.text = f" {val} "
    m2 = _rt(m)
    info2 = _p(m2, "HP1")
    from cabxml import _first
    for tag, expected in (("base", "10,20,30"), ("size", "100,10,10"),
                          ("capillary_limit", "50"), ("max_heat", "200")):
        el = _first(info2.elem, tag)
        assert el is not None, tag
        assert (el.text or "").strip() == expected


def test_delphi_thermal_nodes_roundtrip():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    m.add_part(name="Delphi1", kind="delphi", attribute="Solid")
    info = _p(m, "Delphi1")
    from xml.etree.ElementTree import SubElement
    for tag, val in (("Top", "45.2"), ("Bottom", "38.1"),
                     ("Leads", "0.5"), ("Sides", "1.2")):
        c = SubElement(info.elem, tag)
        c.text = f" {val} "
    m2 = _rt(m)
    info2 = _p(m2, "Delphi1")
    from cabxml import _first
    for tag, expected in (("Top", "45.2"), ("Bottom", "38.1"),
                          ("Leads", "0.5"), ("Sides", "1.2")):
        el = _first(info2.elem, tag)
        assert el is not None, tag
        assert (el.text or "").strip() == expected


def test_particle_analysis_set_roundtrip():
    m = StpreModel(parse_stpre(new_stpre_bytes("T")))
    for key, val in (("particle", "1"), ("particle_diameter", "1e-5"),
                     ("particle_density", "2500"),
                     ("particle_mode", "With inter-particle interaction")):
        m.set_analysis_set_value(key, val) if key == "particle" else \
            m.set_project_value(key, val)
    m2 = _rt(m)
    assert m2.analysis_set_value("particle") == "1"
    assert m2.project_value("particle_diameter") == "1e-5"
    assert m2.project_value("particle_density") == "2500"
    assert m2.project_value("particle_mode") == \
        "With inter-particle interaction"

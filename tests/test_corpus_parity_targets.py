"""Wave 2: POFC/PLIT official trigger model (Solver_eng pages +
post storage correlation).  Non-terminated single-value cards."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET

from cabxml import PropertyModel, StpreModel, new_property_bytes, \
    new_stpre_bytes, parse_property, parse_stpre


def _model():
    return StpreModel(parse_stpre(new_stpre_bytes("T")))


def _props():
    return PropertyModel(parse_property(new_property_bytes()))


def _lines(m):
    from s_export import build_sdat
    return build_sdat(m, _props()).split("\r\n")


def _post(m, vtype, text):
    from cabxml import _first
    out = m.root.find("output")
    if out is None:
        out = ET.SubElement(m.root, "output")
    p = ET.SubElement(out, "post")
    p.attrib["type"] = vtype
    p.text = f" {text} "


def test_pofc_const_step_nonterminated():
    """exA05-1: post const_step=10 -> POFC '0  10' (12-wide int +
    26-wide float), non-terminated (next command follows)."""
    m = _model()
    _post(m, "const_step", "10")
    lines = _lines(m)
    i = lines.index("POFC")
    assert lines[i + 1] == f"{0:12d}{10.0:26.14e}"
    # no '   /' or '/' immediately after (non-terminated data card)
    assert (lines[i + 2] or "").strip() not in ("/", "   /")


def test_pofc_const_cycle():
    """post const_cycle=200 -> POFC '200  0'."""
    m = _model()
    _post(m, "const_cycle", "200")
    lines = _lines(m)
    i = lines.index("POFC")
    assert lines[i + 1] == f"{200:12d}{0.0:26.14e}"


def test_plit_initial_field():
    """exA05-1: post initial=T -> PLIT '1' (IPF30)."""
    m = _model()
    _post(m, "initial", "T")
    lines = _lines(m)
    i = lines.index("PLIT")
    assert lines[i + 1] == f"{1:12d}"


def test_no_pofc_plit_by_default():
    """Steady default (no post cycle/initial) emits neither (ex4_e
    golden rule: official can omit both)."""
    m = _model()
    lines = _lines(m)
    assert "POFC" not in lines and "PLIT" not in lines


def test_pofc_plicate_post_fields_no_dupe():
    """Initial-field T does not fire POFC; const_step does not fire
    PLIT — distinct triggers."""
    from cabxml import _first
    m = _model()
    _post(m, "initial", "T")
    _post(m, "const_step", "5")
    lines = _lines(m)
    assert lines.count("POFC") == 1
    assert lines.count("PLIT") == 1
    sequences = [l for l in lines if l.startswith("           5")]


def test_ex4e_golden_zero_leak():
    from cab_container import CabArchive
    from s_export import build_sdat
    arch = CabArchive.parse(open("tests/ex4_e.cab", "rb").read())
    members = {mm.name: mm for mm in arch.fill_member_data()}
    m = StpreModel(parse_stpre(members["ex4_e.xml"].data))
    s = build_sdat(m, _props())
    for cmd in ("\r\nPOFC\r\n", "\r\nPLIT\r\n"):
        assert cmd not in s, cmd


def test_toff_from_official_time_off_key():
    """TOFF ⇔ <time_off> (corpus 66/66 zero-exception); 26-wide float,
    non-terminated."""
    m = _model()
    m.set_analysis_set_value("time_off", "600")
    m.set_analysis_set_value("calculation", "transient")
    lines = _lines(m)
    i = lines.index("TOFF")
    assert lines[i + 1] == f"{600.0:26.14e}"
    assert lines.index("CYCT") < i < lines.index("GOGO")


def test_toff_absent_by_default():
    m = _model()
    assert "TOFF" not in _lines(m)


def test_v_ijk_from_element_parts_boxes():
    """exA03-1: element/parts body list first 6 values -> V_IJK card
    ('    ' prefix + 10-wide six values)."""
    from xml.etree import ElementTree as ET
    m = _model()
    elem = ET.SubElement(m.root, "element")
    p = ET.SubElement(elem, "parts")
    p.attrib["name"] = "煙H"
    body = ET.SubElement(p, "body")
    body.attrib["num"] = "1"
    lst = ET.SubElement(body, "list")
    lst.attrib["no"] = "1"
    lst.text = " 38,40,11,15,13,13,0,1,1 "
    lines = _lines(m)
    i = next(k for k, l in enumerate(lines) if l.strip() == "V_IJK")
    assert lines[i - 1] == "   煙H   ! 煙H"
    assert lines[i + 1] == "    " + "".join(f"{v:10d}"
                                            for v in (38, 40, 11, 15,
                                                      13, 13))
    assert lines[i + 2] == "   /"
    assert "REGION" in " ".join(lines[:i + 3])

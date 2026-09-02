"""§23 C3 batch: electrostatic potential boundaries (ES_FIELD_BC,
exA07-3 evidence), free-surface contact angle (SUFS_REGION, exA09-4),
and the storage-only contact-resistance conditions."""
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


# ------------------------------------------- ES_FIELD_BC (evidenced)

def test_es_field_bc_matches_official_layout():
    """e_field values bound to faces emit the exA07-3 card layout
    verbatim, right before FOUT."""
    from s_export import build_sdat
    m = _model()
    for name, pot, face in (("0V", 0.0, "Xmin面"),
                            ("-100V", -100.0, "Xmax面")):
        assert m.upsert_value("e_field", name, [
            ("e_potential", f"{name and pot:g}", "V")])
        assert m.bind_condition("region", face, name)
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("ES_FIELD_BC")
    assert lines[i:i + 6] == [
        "ES_FIELD_BC",
        "epotential    0   ! 0V",
        f"{0.0:29.14e}",
        "   Xmin面",
        "   /",
        "epotential    0   ! -100V",
    ]
    assert f"{-100.0:29.14e}" in lines
    assert lines.index("ES_FIELD_BC") < lines.index("FOUT")


def test_es_field_bc_absent_without_values():
    from s_export import build_sdat
    assert "ES_FIELD_BC" not in build_sdat(_model(), _props())


# ------------------------------------------- SUFS_REGION (evidenced)

def test_sufs_region_contact_angle_matches_official():
    """contact_angle values emit SUFS_REGION contactangle cards with the
    exA09-4 card body; the @UNDEFINEDCAG default stays unemitted."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("contact_angle", "ContactAngle1", [
        ("angle", "60", "deg")])
    m.bind_condition("region", "Zmin面", "ContactAngle1")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("SUFS_REGION")
    assert lines[i:i + 5] == [
        "SUFS_REGION",
        "contactangle   0 ",
        f"{60.0:29.14e}",
        "   Zmin面",
        "   /",
    ]
    assert "@UNDEFINEDCAG" not in s
    assert lines.index("SUFS_REGION") < lines.index("MEIX_VAR")


def test_sufs_region_absent_without_values():
    from s_export import build_sdat
    assert "SUFS_REGION" not in build_sdat(_model(), _props())

"""§23 C1 batch: DEM interaction (LSOL_* sections, exA07-4 evidence),
PCLE_HANDLING (Particle Vanishment / Sedimentation, exA07-3 evidence),
and the particle-condition commit API."""
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


def test_lsol_sections_match_official_layout():
    """analysis_etc <dem> maps to the exA07-4 LSOL_FORCE_MODEL /
    LSOL_OPTION / LSOL_TIME_STEP cards verbatim."""
    from s_export import build_sdat
    m = _model()
    m.set_analysis_etc_child("dem", "dem_motion", "1")
    m.set_analysis_etc_child("dem", "dem_contact_model", "1")
    m.set_analysis_etc_child("dem", "dem_rolling_resistance_model", "1")
    m.set_analysis_etc_child("dem", "dem_adhesion", "0")
    m.set_analysis_etc_child("dem", "dem_it_scheme", "2")
    m.set_analysis_etc_child("dem", "dem_detect_algorithm", "3")
    m.set_analysis_etc_child("dem", "dem_detect_cycle", "1")
    m.set_analysis_etc_child("dem", "dem_detect_n_factor", "1.2")
    m.set_analysis_etc_child("dem", "dem_min_reynolds", "1e-10")
    m.set_analysis_etc_child("dem", "dem_stab_scale", "0")
    m.set_analysis_etc_child("dem", "dem_time_divide", "5")
    m.set_analysis_etc_child("dem", "dem_max_loop", "100")
    m.set_analysis_etc_child("dem", "dem_recoverty_step_scale", "0.1")
    m.set_analysis_etc_child("dem", "dem_recoverty_max", "100")
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("LSOL_FORCE_MODEL")
    block = lines[i:i + 35]
    assert block[:8] == [
        "LSOL_FORCE_MODEL",
        "contact_model",
        "   linear_spring_dashpot",
        "rolling_resistance_model",
        "   simplified_linear",
        "cohesion_model",
        "   none",
        "/",
    ]
    j = lines.index("LSOL_OPTION")
    assert lines[j + 1:j + 13] == [
        "lagrangian_solver",
        f"{1:12d}",
        "time_integration",
        f"{2:12d}",
        "contact_detection_algorithm",
        f"{3:12d}",
        "contact_detection_timing",
        f"{1:12d}",
        "neighboring_factor",
        f"{1.2:29.14e}",
        "min_Reynolds",
        f"{1e-10:29.14e}",
    ]
    k = lines.index("LSOL_TIME_STEP")
    assert lines[k + 1:k + 9] == [
        "time_step",
        " division",
        f"{5:12d}",
        "loop",
        f"{100:12d}",
        "recovery",
        " repeat",
        f"{0.1:26.14e}{100:15d}",
    ]


def test_lsol_absent_without_dem():
    from s_export import build_sdat
    s = build_sdat(_model(), _props())
    assert "LSOL_FORCE_MODEL" not in s
    assert "LSOL_OPTION" not in s
    assert "LSOL_TIME_STEP" not in s


def test_pcle_handling_matches_official_layout():
    """particle_condition destruction/sedimentation emit the exA07-3
    PCLE_HANDLING block verbatim."""
    from s_export import build_sdat
    m = _model()
    m.upsert_value("particle_condition", "粒子条件1", [
        ("kind", "destruction", None), ("applied_face", "0", None)])
    m.upsert_value("particle_condition", "粒子条件2", [
        ("kind", "sedimentation", None), ("applied_face", "0", None)])
    for name in ("粒子条件1", "粒子条件2"):
        m.bind_condition("region", "Xmax面", name)
    s = build_sdat(m, _props())
    lines = s.split("\r\n")
    i = lines.index("PCLE_HANDLING")
    assert lines[i:i + 10] == [
        "PCLE_HANDLING",
        f"{1:8d}:L",
        "destruction",
        f"{0:4d}",
        "   Xmax面",
        "   /",
        "sedimentation",
        f"{0:4d}",
        "   Xmax面",
        "   /",
    ]
    assert lines.index("PCLE_HANDLING") < lines.index("FOUT")


def test_pcle_handling_absent_without_conditions():
    from s_export import build_sdat
    assert "PCLE_HANDLING" not in build_sdat(_model(), _props())


def test_particle_page_dem_and_condition_commits(qapp):
    import cab_cwizard_pages as cw
    m = _model()
    page = cw._CwParticlePage(m)
    try:
        page._commit_dem()
        dem = m.analysis_etc_section("dem")
        kids = {c.tag: (c.text or "").strip() for c in dem}
        assert kids["dem_motion"] == "1"
        assert kids["dem_contact_model"] == "1"
        assert kids["dem_time_divide"] == "5"
        assert kids["dem_recoverty_max"] == "100"
        assert page._commit_particle_condition(
            "Vanish1", "destruction", "Xmax面")
        assert page._commit_particle_condition(
            "Sedim1", "sedimentation", "Xmax面")
        val = m.find_value("Vanish1")
        assert val is not None
        assert val.attrib.get("type") == "particle_condition"
        kids = {c.tag: (c.text or "").strip() for c in val}
        assert kids["kind"] == "destruction"
        assert m.condition_value("region", "Xmax面") in ("Vanish1",
                                                        "Sedim1")
        # a kind with no card evidence still stores
        assert page._commit_particle_condition(
            "ExtForce1", "external_force", "Xmin面")
        assert m.find_value("ExtForce1") is not None
    finally:
        page.deleteLater()

"""C4: Condition Wizard support matrix consistency."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

cw = pytest.importorskip("cab_wizards")


def _all_type_keys():
    page = cw._CwAnalysisTypesPage
    return [row[1] for col in page._TYPE_COLS for row in col]


def test_disabled_keys_are_real_types():
    keys = set(_all_type_keys())
    assert cw._CwAnalysisTypesPage._ALWAYS_DISABLED <= keys
    assert cw._CwAnalysisTypesPage._DISABLED_UNTIL_FS <= keys


def test_matrix_counts():
    keys = _all_type_keys()
    always = cw._CwAnalysisTypesPage._ALWAYS_DISABLED
    until_fs = cw._CwAnalysisTypesPage._DISABLED_UNTIL_FS
    enabled = [k for k in keys if k not in always and k not in until_fs]
    assert len(keys) == 25, f"total types = {len(keys)}"
    assert len(always) == 2
    assert len(until_fs) == 2
    assert len(enabled) == 21, f"enabled = {enabled}"


def test_enabled_types_are_the_supported_subset():
    keys = _all_type_keys()
    always = cw._CwAnalysisTypesPage._ALWAYS_DISABLED
    until_fs = cw._CwAnalysisTypesPage._DISABLED_UNTIL_FS
    enabled = {k for k in keys if k not in always and k not in until_fs}
    assert enabled == {
        "heat", "humidity", "porous_media", "radiation_analysis", "free_surface",
        "sun_light", "diffusion", "particle", "jos_model",
        "current", "electrostatic", "ventilation",
        "reaction", "fusion", "artificial_light", "pcm",
        "plant_canopy", "moving_body", "marangoni",
        "topology_opti", "aircon_model",
    }, enabled

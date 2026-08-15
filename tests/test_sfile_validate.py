"""P3: S-File structural validation (validate_sfile)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import s_export


SAMPLE = """SDAT
STREAM
           1
POST
proj
RO
f
VF
f
OT
f
HPT
f
/
comment
           1
          10          10          10           1           1           0           0           0
           0           4           0           0           0           0           0           0           0
VFEX
           1           1
UNIT
/
CXYZ
0
0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0
0
0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0
0
0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0
PARTS
 1 1 0.5   fluid
 1 9 1 9 1 9
/
GOGO
"""


def test_validate_sfile_ok():
    diags = s_export.validate_sfile(SAMPLE)
    levels = {lv for lv, _ in diags}
    assert "ERROR" not in levels
    msgs = " | ".join(m for _, m in diags)
    assert "axis 0 count 10 consistent" in msgs
    assert "all PARTS boxes within axis range" in msgs
    assert "GOGO termination present" in msgs


def test_validate_sfile_detects_range_overflow():
    bad = SAMPLE.replace(" 1 9 1 9 1 9", " 1 99 1 9 1 9")
    diags = s_export.validate_sfile(bad)
    assert any(lv == "ERROR" for lv, _ in diags)


def test_validate_sfile_detects_count_mismatch():
    bad = SAMPLE.replace(
        "          10          10          10           1",
        "           5          10          10           1")
    diags = s_export.validate_sfile(bad)
    assert any("SDAT=5 CXYZ=10" in m for _, m in diags)


def test_validate_sfile_missing_section():
    bad = SAMPLE.replace("PARTS\n", "\n")
    diags = s_export.validate_sfile(bad)
    assert any("section PARTS missing" in m for _, m in diags)


def test_validate_sfile_detects_non_monotonic_axis():
    bad = SAMPLE.replace("0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0",
                         "0.0 0.1 0.2 0.3 0.5 0.4 0.6 0.7 0.8 0.9 1.0", 1)
    diags = s_export.validate_sfile(bad)
    assert any("non-positive width" in m for _, m in diags)


def test_validate_sfile_detects_inverted_box():
    bad = SAMPLE.replace(" 1 9 1 9 1 9", " 9 1 1 9 1 9")
    diags = s_export.validate_sfile(bad)
    assert any("inverted occupancy box" in m for _, m in diags)

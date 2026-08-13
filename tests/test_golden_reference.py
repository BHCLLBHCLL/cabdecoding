"""L2: golden reference regressions (no STpre / pskernel required)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


ROOT = Path(__file__).resolve().parents[1]
BOX_NEW = ROOT / "tests" / "box" / "box_new.s"
BOX_BM = ROOT / "tests" / "box" / "box_bm.s"
TR03_JSON = ROOT / "data" / "stpre_probe_20260808_tr03.json"


def _sfile_axis_points(path: Path) -> list[list[float]]:
    """Parse the CXYZ section into three per-axis coordinate lists (m)."""
    lines = [ln.strip() for ln in path.read_text(
        encoding="utf-8-sig").splitlines()]
    start = lines.index("CXYZ")
    axes: list[list[float]] = []
    current: list[float] | None = None
    for ln in lines[start + 1:]:
        if ln == "PARTS":
            break
        if ln in ("0", "0.0"):
            current = []
            axes.append(current)
            continue
        if current is None:
            continue
        current.extend(float(x) for x in ln.split())
    return axes


def _parts_box_list(path: Path) -> list[int] | None:
    lines = [ln.strip() for ln in path.read_text(
        encoding="utf-8-sig").splitlines()]
    start = lines.index("PARTS")
    for ln in lines[start + 1:]:
        if ln == "/":
            break
        nums = [int(x) for x in ln.split() if x.lstrip("-").isdigit()]
        if len(nums) == 6:
            return nums
    return None


def test_box_new_matches_stpre_golden_coordinates():
    """box_new.s (cabdecoding) vs box_bm.s (STpre): CXYZ identical."""
    assert BOX_NEW.is_file() and BOX_BM.is_file()
    a = _sfile_axis_points(BOX_NEW)
    b = _sfile_axis_points(BOX_BM)
    assert len(a) == 3 and len(b) == 3
    for i in range(3):
        assert len(a[i]) == 55 and len(b[i]) == 55  # 54 cells -> 55 points
        np.testing.assert_allclose(a[i], b[i], rtol=0.0, atol=1e-15)


def test_box_new_matches_stpre_golden_occupancy():
    """box_new.s vs box_bm.s: identical 6-field part occupancy list."""
    assert _parts_box_list(BOX_NEW) == [20, 39, 20, 39, 20, 39]
    assert _parts_box_list(BOX_BM) == [20, 39, 20, 39, 20, 39]


def test_tr03_probe_reference_counts_pinned():
    """Pin STpre black-box tr03 grid counts (all > rep > plane/minmax/none).

    Native counts currently deviate for curved parts (see
    STPRE_GRID_RULES §5.3 / DEV_SUMMARY §39.3); this test pins the
    *reference data* so algorithm work can converge to it later.
    """
    assert TR03_JSON.is_file()
    data = json.loads(TR03_JSON.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    by_vd: dict[int, tuple[int, int, int]] = {}
    for r in recs:
        if r["input"]["threshold"] != [0.1, 0.1, 0.1]:
            continue  # only the base threshold sweep pins the hierarchy
        vd = r["input"]["vertex_detection"]
        axes = r["output"]["axes"]
        by_vd[vd] = tuple(len(axes[a]) for a in "xyz")
    assert by_vd[0] == (59, 118, 121)    # all
    assert by_vd[1] == (57, 91, 92)      # representative
    assert by_vd[2] == (57, 85, 85)      # axis plane
    assert by_vd[3] == (57, 85, 85)      # minmax
    assert by_vd[4] == (57, 85, 85)      # not considered
    assert by_vd[5] == (91, 141, 141)    # uniform


def test_mesh_control_params_roundtrip():
    """L2: Others-tab mesh params survive serialize -> parse."""
    model = StpreModel(parse_stpre(new_stpre_bytes()))
    vals = {
        "edge_eps": "0.0002",
        "element_threshold": "0.5",
        "face_search": "1.5",
        "panel_block_face": "2",
        "check_scheme": "1",
        "solid_scheme": "0",
        "panel_scheme": "0",
        "divide_scale": "3",
        "edge_contact": "1",
    }
    for tag, text in vals.items():
        assert model.set_mesh_control_value(tag, text)
    again = StpreModel(parse_stpre(model.doc.serialize()))
    for tag, text in vals.items():
        assert again.mesh_control_value(tag) == text

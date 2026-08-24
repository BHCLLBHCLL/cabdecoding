"""L2: golden reference regressions (no STpre / pskernel required)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cabxml import StpreModel, new_stpre_bytes, parse_stpre


ROOT = Path(__file__).resolve().parents[1]
BOX_NEW = ROOT / "tests" / "box" / "box_new.s"
BOX_BM = ROOT / "tests" / "box" / "box_bm.s"
TR03_JSON = ROOT / "data" / "stpre_probe_20260808_tr03.json"
ALL_JSON = ROOT / "data" / "stpre_probe_20260808_all.json"


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


def _sfile_hdr1_line(path: Path) -> str:
    """The 8-column SDAT count row following the '1' comment terminator."""
    lines = [ln.rstrip() for ln in path.read_text(
        encoding="utf-8-sig").splitlines()]
    marker = next(i for i, ln in enumerate(lines) if ln.strip() == "1")
    return lines[marker + 1]


def test_box_new_matches_stpre_golden_coordinates():
    """box_new.s (cabdecoding) vs box_bm.s (STpre): CXYZ identical."""
    assert BOX_NEW.is_file() and BOX_BM.is_file()
    a = _sfile_axis_points(BOX_NEW)
    b = _sfile_axis_points(BOX_BM)
    assert len(a) == 3 and len(b) == 3
    for i in range(3):
        assert len(a[i]) == 55 and len(b[i]) == 55  # 54 cells -> 55 points
        np.testing.assert_allclose(a[i], b[i], rtol=0.0, atol=1e-15)


def test_box_new_matches_stpre_golden_hdr1():
    """P5: hdr1 row (ni,nj,nk + tail) identical to the STpre golden."""
    assert _sfile_hdr1_line(BOX_NEW) == _sfile_hdr1_line(BOX_BM)
    assert _sfile_hdr1_line(BOX_BM).split() == [
        "54", "54", "54", "1", "1", "0", "0", "0"]


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


def _cellset(boxes: list) -> set[tuple[int, int, int]]:
    out = set()
    for b in boxes:
        i1, i2, j1, j2, k1, k2 = b[:6]
        for i in range(i1, i2 + 1):
            for j in range(j1, j2 + 1):
                for k in range(k1, k2 + 1):
                    out.add((i, j, k))
    return out


def test_stpre_box_occupancy_golden():
    """Native occupancy cell sets equal STpre part_boxes (20 box cases)."""
    import cab_mesh
    from cab_parts import cube_tess
    assert ALL_JSON.is_file()
    data = json.loads(ALL_JSON.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])
    tess = cube_tess((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))
    tess.name = "box"
    checked = 0
    for r in recs:
        inp = r.get("input", {})
        out = r.get("output", {})
        if inp.get("part_transform") or inp.get("extra_part") \
                or inp.get("stl_part"):
            continue
        pb = out.get("part_boxes", {})
        if "box" not in pb:
            continue
        axes = out.get("axes")
        if not axes or len(axes.get("x", [])) < 2:
            continue
        _, native = cab_mesh.classify_cells(
            axes, [tess], part_kinds={"box": "cube"},
            part_attrs={"box": "solid"})
        st = _cellset(pb["box"])
        nt = _cellset(native.get("box", []))
        assert st == nt, f"occupancy mismatch for {r.get('name')}"
        checked += 1
    assert checked >= 20


def test_tr03_native_grid_counts_match_golden():
    """R1 acceptance: native build_axes reproduces STpre tr03 counts e2e.

    all (59,118,121) and representative (57,91,92) via the decoded
    recipes: display-mesh node projection clipped to the domain box +
    part AABB extremes (all); in-domain B-rep vertices + AABB extremes
    (rep); interval split ``n = floor(L/std + 2/3_f32)`` (STpre uses the
    float32-rounded 2/3 constant).  Requires pskernel; skipped when the
    Parasolid runtime is unavailable.
    """
    pytest.importorskip("ps_facet2_nodes")
    import ps_facet2_nodes as ps
    import cab_grid
    import cab_vtk

    transform = ("1,0,0,0,0,1,0,0,0,0,1,0,"
                 "-0.0225,-0.0475,-0.0475,1")

    def world(p):
        return cab_vtk._apply_transform(
            np.asarray(p, float) / 1000.0, transform) * 1000.0

    data = json.loads(TR03_JSON.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else data.get("records", [])

    try:
        sess = ps._get_session()
        xt = (ROOT / "tests" / "tr03" / "_tr03_all.x_t").read_bytes()
        tags = sess.expand_to_bodies(sess.receive_xt(xt))
        imp = next((t for t in tags
                    if sess.body_name(t) == "Impeller"), None)
        if imp is None:
            pytest.skip("Impeller body not found in tr03 x_t")
        part = sess.facet_body_stpre(imp) or sess.facet_body(imp)
        verts = sess.body_vertices(imp)
    except OSError:
        pytest.skip("pskernel runtime unavailable")

    tess = {"Impeller": world(np.asarray(part.points) * 1000.0)}
    vertices = {"Impeller": world(np.asarray(verts) * 1000.0)}
    lo = tess["Impeller"].min(axis=0)
    hi = tess["Impeller"].max(axis=0)

    for vd, det, want in ((0, "all", (59, 118, 121)),
                          (1, "representative", (57, 91, 92))):
        rec = next(r for r in recs
                   if r["input"]["threshold"] == [0.1, 0.1, 0.1]
                   and r["input"]["vertex_detection"] == vd)
        inp = rec["input"]
        spec = cab_grid.GridSpec(
            unit="mm",
            domain_min=tuple(inp["domain_min"]),
            domain_max=tuple(inp["domain_max"]),
            vertex_detection=det, method="rough_and_detail",
            standard_length=tuple(inp["standard_length"]),
            threshold_length=tuple(inp["threshold"]),
            geometric_ratio=tuple(inp["ratio_in"]),
            geometric_ratio_external=tuple(inp["ratio_out"]))
        _, detailed = cab_grid.build_axes(
            tess, spec, part_vertices=vertices, part_bounds=(lo, hi))
        got = tuple(len(detailed[a]) for a in "xyz")
        assert got == want, f"vd={vd}: native {got} != golden {want}"

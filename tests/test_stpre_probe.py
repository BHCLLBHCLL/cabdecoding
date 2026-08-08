"""stpre_probe.py harness tests (no COM / no STpre launch)."""
from __future__ import annotations

import stpre_probe


def test_default_cases_matrix():
    cases = stpre_probe.default_cases()
    assert len(cases) == 35
    names = {c.name for c in cases}
    for required in ("base_minmax_detail", "vd_uniform", "method_coarse",
                     "auto1_8000", "auto3_20", "part_rot_z30_all",
                     "part_translate_x_mm_2_5", "stl_L_all",
                     "domain_noncube_offset"):
        assert required in names


def test_special_matrices():
    assert len(stpre_probe.auto1_sweep_cases()) == 13
    assert len(stpre_probe.tr03_vd_cases()) == 9
    assert len(stpre_probe.ex4e_vd_cases()) == 9
    assert len(stpre_probe.stl_registration_cases()) == 2
    names = {c.name for c in stpre_probe.tr03_vd_cases()}
    assert "tr03_imp_thr_2_0" in names


def test_grid_and_block_params():
    case = stpre_probe.ProbeCase(
        name="t", method="auto1", target_elements=8000,
        vertex_detection=3, ratio_out=(1.2, 1.2, 1.2),
        standard_length=(1.0, 1.0, 1.0), threshold=(0.1, 0.1, 0.1),
        ratio_in=(1.0, 1.0, 1.0), edge_contact=1)
    gp = dict((p[0], p[1:4]) for p in case.grid_params())
    assert gp["division_method"] == ("auto1", "", "")
    assert gp["division_type"] == ("minmax", "", "")
    assert gp["division_num"] == (8000, 0, 0)
    assert gp["outer_ratio"] == (1.2, 1.2, 1.2)
    assert gp["edge_contact"] == (1, "", "")
    bp = dict((p[0], p[1:4]) for p in case.block_params())
    assert bp["length"] == (1.0, 1.0, 1.0)
    assert bp["limit"] == (0.1, 0.1, 0.1)


def test_l_shape_stl_bytes_parses():
    import cab_import
    raw = stpre_probe._l_shape_stl_bytes()
    assert raw.startswith(b"solid lshape")
    pts, tris = cab_import.parse_stl_bytes(raw)
    assert pts.shape[1] == 3
    assert len(tris) == 24            # 12 triangles per box
    assert pts.max(0)[0] == 10.0      # L footprint spans 0..10 in x
    assert pts.max(0)[1] == 10.0


def test_axis_metrics():
    m = stpre_probe._axis_metrics([0.0, 1.0, 2.0, 5.0])
    assert m["count"] == 4
    assert m["spacing_min"] == 1.0
    assert m["spacing_max"] == 3.0

# M36: STpre display-mesh recipe (P0-1 all vertex detection exact count).
#
# Round-30 decode (STPRE_GRID_RULES.md 2.3.3): STpre's display mesh is
# PK_TOPOL_facet_2 fed with six tolerances derived from the body bbox
# diagonal D and the facet_kind angle branch (2 -> 10 deg).  Validated
# against the STpre-saved STL (tools/facet_validate.py): tr03 body 1
# facets to exactly 2206 triangles with the seven golden x-lines
# {-22.5, -20, +-6.667, 0, 20, 22.5} mm.
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ps_facet2_nodes as M


def test_stpre_recipe_math():
    r = M.stpre_recipe(0.141683, angle_deg=10.0)
    assert abs(r['curve_chord_ang'] - 0.174532925199) < 1e-9
    assert r['surface_plane_ang'] == r['curve_chord_ang']
    assert abs(r['max_facet_width'] - 0.141683 * 0.2) < 1e-12
    assert abs(r['curve_chord_max'] - 0.141683 * 0.1) < 1e-12
    assert abs(r['curve_chord_tol'] - 0.141683 * 0.001) < 1e-15
    assert abs(r['surface_plane_tol'] - 0.141683 * 0.001) < 1e-15
    # zero diagonal clamps each length to 1e-8; angle keeps rad floor
    r0 = M.stpre_recipe(0.0)
    assert r0['max_facet_width'] == 1e-8
    assert r0['curve_chord_max'] == 1e-8
    # negative angle clamps to 1e-6 deg (1.745e-8 rad)
    assert abs(M.stpre_recipe(1.0, angle_deg=-5)['curve_chord_ang']
               - 1e-6 * 0.017453292519943295) < 1e-16


def test_stpre_recipe_tr03_golden():
    # Integration: the recipe facets tr03 body 1 to the STpre golden mesh.
    if not M.available():
        return
    xt = Path(__file__).parent / 'tr03' / '_tr03_all.x_t'
    if not xt.is_file():
        return
    sess = M._get_session()
    tags = sess.expand_to_bodies(sess.receive_xt(xt.read_bytes()))
    assert len(tags) >= 2, 'tr03 fixture should hold at least 2 bodies'
    part = sess.facet_body_stpre(tags[1])
    assert part is not None
    assert len(part.triangles) == 2206, 'golden STpre display mesh = 2206 tris'
    pts = part.points + np.array([-0.0225, -0.0475, -0.0475])
    xl = np.unique(np.round(pts[:, 0], 6))
    golden_x = [-0.0225, -0.02, -0.006667, 0.0, 0.006667, 0.02, 0.0225]
    for g in golden_x:
        assert np.any(np.abs(xl - g) < 1e-6), 'missing golden x-line ' + str(g)


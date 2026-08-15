# Validate the decoded STpre display-mesh recipe against the STpre-saved STL
# (tools/probe_work/imp_stpre.stl, produced by STpre SaveStlFile on the tr03
# project) and the fixture x_t (tests/tr03/_tr03_all.x_t).
#
# Recipe (STPRE_GRID_RULES.md 2.3.3): PK_TOPOL_facet_2 with six tolerances
# derived from the body bbox diagonal D (facet_kind=2 -> 10 deg branch):
#   max_facet_width  = D*0.2   curve_chord_tol = D*0.001
#   curve_chord_max  = D*0.1   curve_chord_ang  = 10 deg
#   surface_plane_tol= D*0.001 surface_plane_ang= 10 deg
#
# Expected: body 1 of the tr03 x_t (45x95x95 mm, translated -22.5,-47.5,
# -47.5 mm) facets to exactly 2206 triangles whose x-coordinates are the
# seven golden lines {-22.5, -20, +-6.667, 0, 20, 22.5} mm.
import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ps_facet2_nodes as M

XT = Path("tools/probe_work/probe_tr03_all.x_t")
GOLDEN_STL = Path("tools/probe_work/imp_stpre.stl")
TRAN = np.array([-0.0225, -0.0475, -0.0475])
GOLDEN_X = [-0.0225, -0.02, -0.006667, 0.0, 0.006667, 0.02, 0.0225]
BODY_INDEX = 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--angle", type=float, default=10.0)
    ap.add_argument("--no-stl", action="store_true",
                    help="compare only against the golden x-lines")
    args = ap.parse_args()
    if not XT.is_file():
        print(f"missing {XT} (extract from tr03_imp_vd_0_in.cab first)")
        return 2
    sess = M._get_session()
    tags = sess.expand_to_bodies(sess.receive_xt(XT.read_bytes()))
    part = sess.facet_body_stpre(tags[BODY_INDEX], angle_deg=args.angle)
    if part is None:
        print("recipe facet failed")
        return 3
    pts = part.points + TRAN
    xl = np.unique(np.round(pts[:, 0], 6))
    shared = len(set(xl) & set(GOLDEN_X))
    print(f"recipe body{BODY_INDEX}: {len(part.points)} pts, "
          f"{len(part.triangles)} tris")
    print(f"x-lines ({len(xl)}): {[round(float(x), 6) for x in xl]}")
    print(f"golden x-lines: {GOLDEN_X}")
    print(f"x-line match: {shared}/{len(GOLDEN_X)}")
    ok = shared == len(GOLDEN_X)
    if not args.no_stl and GOLDEN_STL.is_file():
        raw = GOLDEN_STL.read_bytes().decode("ascii")
        verts = [tuple(float(x) for x in m.groups())
                 for m in re.finditer(
                     r"vertex\s+([-+\d.eE]+)\s+([-+\d.eE]+)"
                     r"\s+([-+\d.eE]+)", raw)]
        gold = np.array(verts)
        n_tri = len(verts) // 3
        # 1e-8 m tolerance matching: STpre's ASCII writer emits the same
        # mesh with <= 1.2e-10 m last-digit noise on a few arc vertices.
        same = (len(part.triangles) == n_tri)
        for i, ax in enumerate("xyz"):
            ou = np.sort(np.unique(np.round(pts[:, i], 9)))
            gu = np.sort(np.unique(np.round(gold[:, i], 9)))
            hit = 0
            for gv in gu:
                if np.any(np.abs(ou - gv) <= 1e-8):
                    hit += 1
            print(f"{'xyz'[i]}: ours {len(ou)} uniq, golden {len(gu)}, "
                  f"within 1e-8 {hit}")
            same = same and hit == len(gu)
        print(f"triangles: ours {len(part.triangles)} vs golden {n_tri}")
        ok = ok and same
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

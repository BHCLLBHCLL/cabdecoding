# P0 round 73: for each extra projected value, distance to nearest GOLD
# value; and cluster structure: would dropping "within d of a kept value"
# with iterative re-selection reproduce gold exactly?
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_0"]
dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))
gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i]+0.1 < v < dom[1][i]-0.1])
        for i, ax in enumerate("xyz")}

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points) * 1000.0)

def proj_vals(vals, i_ax):
    v = np.sort(np.asarray(vals, float))
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lo+0.1) & (v < hi-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    cand = proj_vals(P[:, i_ax], i_ax)
    extras = np.asarray([v for v in cand if not np.any(np.abs(g-v) < 0.1)])
    d = [float(np.min(np.abs(g-e))) for e in extras]
    print(f"\n{ax}: extras={len(extras)}")
    print("  dist-to-nearest-gold:",
          [f"{x:.3f}" for x in sorted(d)])
    # kept gold values whose nearest gold neighbour is close (structure)
    gs = np.sort(g)
    gaps = np.diff(gs)
    print(f"  gold min gap={gaps.min():.3f}  #gold pairs<0.5mm="
          f"{int((gaps<0.5).sum())}")
    # iterative drop: repeatedly remove cand values that are the closest
    # pair partner within d and NOT in gold -- count how many must go
    print("  extras:", [round(v,3) for v in extras][:30])

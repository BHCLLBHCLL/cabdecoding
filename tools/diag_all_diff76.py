# P0 round 76: HYPOTHESIS - S-line vertex candidates are clipped to the
# computational domain box: only display-mesh nodes INSIDE dom (with
# boundary tolerance) project.  Test per-axis and with merge d=0.11.
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
N = len(P)

lo = np.asarray(dom[0]); hi = np.asarray(dom[1])
inside = np.all((P >= lo - 1e-6) & (P <= hi + 1e-6), axis=1)
print(f"nodes={N} inside-dom={int(inside.sum())} outside={int((~inside).sum())}")

def proj_vals(vals, i_ax):
    v = np.sort(np.asarray(vals, float))
    lox, hix = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lox+0.1) & (v < hix-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

def cluster(vals, d):
    out = [vals[0]]
    for v in vals[1:]:
        if v - out[-1] > d:
            out.append(v)
    return np.asarray(out)

for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    cand = proj_vals(P[inside, i_ax], i_ax)
    ex = sum(1 for v in cand if not np.any(np.abs(g-v) < 0.1))
    ms = sum(1 for v in g if not np.any(np.abs(cand-v) < 0.1))
    print(f"{ax}: inside-only cand={len(cand)} gold={len(g)} "
          f"extras={ex} miss={ms}")
    if ex == 0 and ms == 0:
        # try merging pairs within d until count == gold
        for d in (0.05, 0.08, 0.11, 0.13, 0.15, 0.2):
            m = cluster(cand.tolist(), d)
            print(f"    merge d={d}: {len(m)}")
    else:
        exv = [v for v in cand if not np.any(np.abs(g-v) < 0.1)]
        print("    extras:", [round(v,3) for v in exv][:30])

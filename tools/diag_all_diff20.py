# P0 diagnostic round 20: cluster float64 facet projections with gap<thr,
# pick a representative (min/max/mean/first/last), compare to the exact
# golden anchor set.  Decisive test for the merge rule.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

def clusters_of(vals, thr):
    cl, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] < thr:
            cur.append(v)
        else:
            cl.append(cur)
            cur = [v]
    cl.append(cur)
    return cl

REP = {
    "min":  lambda c: c[0],
    "max":  lambda c: c[-1],
    "mean": lambda c: float(np.mean(c)),
    "mid":  lambda c: 0.5*(c[0]+c[-1]),
}

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    # gold anchors = gold lines exactly matching a facet value
    vals = np.unique(P[:, i_ax])
    d = np.min(np.abs(vals[None, :] - gold[:, None]), axis=1)
    anchors = set(np.round(gold[d < 1e-9], 9))
    print(f"\n=== {ax}: gold={len(gold)} anchors={len(anchors)}")
    in_dom = vals[(vals >= gold[0]-0.05) & (vals <= gold[-1]+0.05)]
    for thr in (0.02, 0.05, 0.08, 0.1, 0.11, 0.12, 0.15, 0.2):
        cl = clusters_of(in_dom, thr)
        for name, f in REP.items():
            reps = [f(c) for c in cl]
            hit = sum(1 for r in reps
                      if any(abs(r - a) < 1e-6 for a in anchors))
            miss = len(anchors) - hit
            extra = len(reps) - hit
            print(f"  thr={thr:4.2f} rep={name:4s}: n={len(reps):3d} "
                  f"hit={hit}/{len(anchors)} miss={miss} extra={extra}")

# P0 diagnostic round 28: reconcile projection-vs-golden matching.
# x: 30 in-domain projections all kept? y: kept=156 > gold=118 impossible.
# Print exact match matrices for x and y.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as pf
import cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
dom_lo = np.asarray(rec0["input"]["domain_min"], float)
dom_hi = np.asarray(rec0["input"]["domain_max"], float)

sess = pf._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
whole = sess.facet_body_stpre(imp)
Pw = world(np.asarray(whole.points)*1000.0)

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(Pw[:, i_ax])
    in_dom = vals[(vals >= dom_lo[i_ax]) & (vals <= dom_hi[i_ax])]
    # distance of each projection to nearest gold line
    d = np.min(np.abs(in_dom[:, None] - gold[None, :]), axis=1)
    n_hit = int((d < 1e-6).sum())
    # how many distinct gold lines were hit
    hit_idx = np.argmin(np.abs(in_dom[:, None] - gold[None, :]), axis=1)
    hit_gold = len(set(hit_idx[d < 1e-6].tolist()))
    # reverse: gold lines near a projection
    dg = np.min(np.abs(gold[:, None] - vals[None, :]), axis=1)
    print(f"{ax}: projections(in-dom)={len(in_dom)} hit={n_hit} "
          f"distinct-gold-hit={hit_gold}/{len(gold)} "
          f"gold-near-proj(<1e-6)={int((dg < 1e-6).sum())}")
    # show d histogram buckets
    for b in (0, 1e-9, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.05, 0.1):
        print(f"   d<{b:g}: {int((d < b).sum())}")

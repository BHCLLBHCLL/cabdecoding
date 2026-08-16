# P0 diagnostic round 10: rough = merged edge-node projections (Impeller only),
# then interval-by-interval fit of golden subdivision count n vs span.
import json, sys, math
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
dom_lo = np.asarray(rec0["input"]["domain_min"], float)
dom_hi = np.asarray(rec0["input"]["domain_max"], float)
thr = 0.1

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
em = np.asarray(part.edge_mask, bool) if part.edge_mask is not None else np.ones(len(P), bool)
print(f"nodes={len(P)} edge nodes={em.sum()}")
allp = [np.unique(np.round(P[:, i], 6)) for i in range(3)]
edgp = [np.unique(np.round(P[em][:, i], 6)) for i in range(3)]
for i, ax in enumerate("xyz"):
    print(f"{ax}: all-unique={len(allp[i])} edge-unique={len(edgp[i])}")

def merge(vals, thr):
    out = []
    for v in np.sort(vals):
        if out and v - out[-1][-1] <= thr + 1e-12:
            out[-1].append(v)
        else:
            out.append([v])
    return out

for i, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    print(f"\n=== {ax} ===")
    for tag, src in (("edge", edgp[i]),):
        clusters = merge(src[src >= dom_lo[i] - thr], thr)
        reps = [c[0] for c in clusters]  # rep = min for now
        reps = [r for r in reps if r <= dom_hi[i] + thr]
        # how many cluster reps appear in gold (within 0.05)?
        hits = sum(1 for r in reps if np.any(np.abs(gold - r) < 0.05))
        # how many gold lines are explained (near any cluster member)?
        memhit = sum(1 for v in gold if any(abs(v - m) < 0.05 for c in clusters for m in c))
        print(f"{tag}: clusters={len(clusters)} rep-min-in-gold={hits} "
              f"gold-near-any-member={memhit}/{len(gold)}")
    # interval fit using edge clusters (rep=min), interior golden line count
    clusters = merge(edgp[i][(edgp[i] >= dom_lo[i] - thr) & (edgp[i] <= dom_hi[i] + thr)], thr)
    reps = [min(c[0], dom_hi[i]) for c in clusters]
    reps = sorted(set([max(r, dom_lo[i]) for r in reps] + [dom_lo[i], dom_hi[i]]))
    rows = []
    for a, b in zip(reps[:-1], reps[1:]):
        inside = gold[(gold > a + 0.05) & (gold < b - 0.05)]
        n = len(inside) + 1
        if n > 1 and b - a > 0.15:
            # check uniformity of the inside spacings incl. ends
            seq = np.concatenate([[a], inside, [b]])
            d = np.diff(seq)
            rows.append((a, b, b - a, n, d.max() - d.min()))
    print("span,n,uniformity-dev:")
    for a, b, s, n, dev in rows:
        flag = "" if dev < 1e-3 else f"  NONUNIFORM dev={dev:.4f}"
        ceil_pred = math.ceil(s - 1e-9)
        mark = "" if n == ceil_pred else f"  ceil={ceil_pred} MISMATCH"
        print(f"  [{a:9.4f},{b:9.4f}] span={s:8.4f} n={n}{flag}{mark}")

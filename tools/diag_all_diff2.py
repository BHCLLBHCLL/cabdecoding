# P0 diagnostic round 2 (Impeller only):
# 1) which merge tolerance on tess projections yields golden counts (118/121)?
# 2) cumulative-chain merge vs pairwise;
# 3) sharp-edge vertex subset hypothesis;
# 4) subdivision n rule (segment [-20,0] -> 21 parts => spacing 20/21).
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
T = np.asarray(part.triangles)

rec = next(r for r in g["records"]
           if r["input"]["threshold"] == [0.1,0.1,0.1]
           and r["input"]["vertex_detection"] == 0)
print("input:", {k: rec["input"][k] for k in
      ("domain_min","domain_max","standard_length","threshold","ratio_in","ratio_out")})

def dedupe(vals, tol, chain=False):
    v = np.sort(np.asarray(vals, float))
    out = [v[0]]
    for x in v[1:]:
        if chain:
            if x - out[-1] <= tol:
                continue
        else:
            if x - out[-1] <= tol:
                out[-1] = out[-1]  # keep first; adjacent pairwise
                if x - out[-1] <= tol:
                    continue
        out.append(x)
    return np.asarray(out)

# brute pairwise (independent of my buggy variants): sorted unique with min-gap >= tol (keep first)
def dedupe_first(vals, tol):
    v = np.sort(np.unique(np.asarray(vals, float)))
    out = [v[0]]
    for x in v[1:]:
        if x - out[-1] >= tol:
            out.append(x)
    return np.asarray(out)

dmin = np.asarray(rec["input"]["domain_min"], float)
dmax = np.asarray(rec["input"]["domain_max"], float)
for i, ax in enumerate("xyz"):
    gold = np.asarray(rec["output"]["axes"][ax], float)
    proj = P[:, i]
    proj = proj[(proj >= dmin[i]-1e-9) & (proj <= dmax[i]+1e-9)]
    print(f"\n=== {ax}: golden {len(gold)}, raw unique proj {len(np.unique(np.round(proj,6)))}")
    for tol in (0.05, 0.1, 0.13, 0.15, 0.2, 0.25, 0.3, 0.5):
        d = dedupe_first(proj, tol)
        mark = " <== MATCH" if len(d) == len(gold) else ""
        print(f"  tol={tol}: {len(d)}{mark}")
    # subdivision check on golden: find equal-spacing runs
    dg = np.diff(gold)
    # group consecutive equal spacings (0.5% window)
    runs = []
    start = 0
    for k in range(1, len(dg)):
        if abs(dg[k]-dg[k-1]) > 0.005*max(abs(dg[k]), 1e-9):
            runs.append((start, k))
            start = k
    runs.append((start, len(dg)))
    print("  golden equal-spacing runs (start_idx, end_idx, spacing, n_cells):")
    for s, e in runs:
        if e-s >= 2:
            print(f"    [{gold[s]:.4f} .. {gold[e]:.4f}] spacing={dg[s]:.5f} cells={e-s}")

# P0 diagnostic round 41: cluster-level (0.1 tol) matching of native
# edge-node rough anchors vs golden S lines.  Classify each mismatch as
# cluster-representative diff (ok) vs true extra/missing.  For true
# missing: check whether B-rep vertex projections explain them.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk, cab_grid

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))

imp = next((t for t in tags if sess.body_name(t) == "Impeller"), None)
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
E = P[part.edge_mask] if part.edge_mask is not None and part.edge_mask.any() else P
V = world(np.asarray(sess.body_vertices(imp))*1000.0)
dmin = np.asarray(g["records"][0]["input"]["domain_min"], float)
dmax = np.asarray(g["records"][0]["input"]["domain_max"], float)

mk = marks["tr03_imp_vd_0"]
print("=== all-mode anchors, cluster matching (tol=0.1) ===")
for i_ax, ax in enumerate("xyz"):
    gold_s = np.asarray(mk["s_lines"][ax], float)
    # raw edge-node projections clipped to domain, cluster-merged like _clip_dedupe
    raw = E[:, i_ax]
    raw = raw[(raw >= dmin[i_ax]) & (raw <= dmax[i_ax])]
    rough = np.sort(cab_grid._clip_dedupe(
        [float(raw.min()), float(raw.max())] + [float(v) for v in raw],
        dmin[i_ax], dmax[i_ax], tol=0.1)) if hasattr(cab_grid, "_clip_dedupe") else np.unique(raw)
    rough = np.asarray(rough, float)
    # bidirectional cluster match
    r_extra = [v for v in rough if not np.any(np.abs(gold_s - v) < 0.1)]
    s_miss = [v for v in gold_s if not np.any(np.abs(rough - v) < 0.1)]
    # cluster-rep diffs: rough line with gold S within (0.02, 0.1)
    rep_diff = [v for v in rough
                if 0.001 < np.min(np.abs(gold_s - v)) < 0.1]
    print(f"{ax}: rough={len(rough)} goldS={len(gold_s)} true-extra={len(r_extra)} "
          f"true-missing={len(s_miss)} rep-diff={len(rep_diff)}")
    if r_extra:
        print(f"  true-extra: {np.round(r_extra, 3)}")
    if s_miss:
        # check B-rep vertex explanation
        vexp = []
        for v in s_miss:
            dv = np.min(np.abs(V[:, i_ax] - v)) if len(V) else 9e9
            de = np.min(np.abs(E[:, i_ax] - v))
            vexp.append(f"{v:.3f}(V:{dv:.4f},E:{de:.4f})")
        print(f"  true-missing: {vexp}")

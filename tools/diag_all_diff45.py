# P0 diagnostic round 45: cross-validate the edge-node-projection anchor
# hypothesis on ex4e battery (second dataset).  Cluster-match native
# edge-node projections vs battery vd_0 golden S lines per axis.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk, cab_grid

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,0,0.0080776406404414,-0.00010967038962146,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"tools"/"probe_work"/"ex4e_marks.json").read_text(encoding="utf-8"))
mk = marks["ex4e_battery_vd0"]
dom = {"x": (-10.0, 60.0), "y": (-10.0, 60.0), "z": (-10.0, 15.0)}

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"ex4e"/"_ex4e_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
bat = next(t for t in tags if sess.body_name(t) == "battery")
part = sess.facet_body_stpre(bat, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
E = P[part.edge_mask] if part.edge_mask is not None else P
print(f"battery tess: {len(P)} nodes, {int(part.edge_mask.sum())} edge nodes")

for i_ax, ax in enumerate("xyz"):
    gold_s = np.asarray(mk["s_lines"][ax], float)
    d0, d1 = dom[ax]
    raw = E[:, i_ax]
    raw_c = raw[(raw >= d0) & (raw <= d1)]
    rough = np.sort(cab_grid._clip_dedupe(
        [float(raw_c.min()), float(raw_c.max())] + [float(v) for v in raw_c],
        d0, d1, tol=0.1))
    rough = np.asarray(rough, float)
    r_extra = [v for v in rough if not np.any(np.abs(gold_s - v) < 0.1)]
    s_miss = [v for v in gold_s if not np.any(np.abs(rough - v) < 0.1)]
    print(f"{ax}: rough={len(rough)} goldS={len(gold_s)} "
          f"true-extra={len(r_extra)} true-missing={len(s_miss)}")
    if r_extra:
        print(f"  extra: {np.round(r_extra, 3)}")
    if s_miss:
        print(f"  miss:  {np.round(s_miss, 3)}")

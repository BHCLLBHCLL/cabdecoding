# P0 diagnostic round 46: investigate battery's 3 missing y S-lines
# (8.7018, 8.837, 9.9798).  Check all-node projections, B-rep vertices,
# and nearest edge-node distances.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,0,0.0080776406404414,-0.00010967038962146,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"tools"/"probe_work"/"ex4e_marks.json").read_text(encoding="utf-8"))
mk = marks["ex4e_battery_vd0"]

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"ex4e"/"_ex4e_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
bat = next(t for t in tags if sess.body_name(t) == "battery")
part = sess.facet_body_stpre(bat, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
E = P[part.edge_mask]
V = world(np.asarray(sess.body_vertices(bat))*1000.0)
print(f"nodes={len(P)} edge={len(E)} vertices={len(V)}")

for i_ax, ax in enumerate("xyz"):
    gold_s = np.asarray(mk["s_lines"][ax], float)
    # which S lines are NOT matched by edge nodes (0.1)?
    de = np.min(np.abs(E[:, i_ax][:, None] - gold_s[None, :]), axis=0) \
        if len(E) else np.full(len(gold_s), 9e9)
    da = np.min(np.abs(P[:, i_ax][:, None] - gold_s[None, :]), axis=0)
    dv = np.min(np.abs(V[:, i_ax][:, None] - gold_s[None, :]), axis=0) \
        if len(V) else np.full(len(gold_s), 9e9)
    print(f"-- {ax}: S-lines with nearest-edge-dist > 0.1 --")
    for v, e, a, vv in zip(gold_s, de, da, dv):
        if e > 0.1:
            print(f"  S={v:.4f}  edge_d={e:.4f}  all_d={a:.4f}  vert_d={vv:.4f}")
    # also: node-level - are there nodes whose projection matches NO S line?
    ds = np.min(np.abs(E[:, i_ax][:, None] - gold_s[None, :]), axis=1)
    print(f"   edge nodes not matching any S (<0.1): {int((ds > 0.1).sum())}/{len(E)}")

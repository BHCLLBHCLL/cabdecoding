"""Greedy threshold merge of tess y/z projections: find tol that matches STpre rough counts."""
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t) == "Impeller": imp = t
if imp is None: imp = tags[0]
tess = sess.facet_body(imp)
pts = cab_vtk._apply_transform(np.asarray(tess.points), TRANSFORM) * 1000.0

def greedy_merge(vals, tol):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out

# golden internal region counts: y internal [-20, 47.5] has 74 intervals (75 pts),
# z internal [-20, 47.5] has ~101 pts (from 121 total - 20 external).
for ax in ("y", "z"):
    i = {"y":1, "z":2}[ax]
    u = np.unique(np.round(pts[:,i], 9))
    print(f"{ax}: distinct tess world values = {len(u)}")
    for tol in (0.1, 0.12, 0.13, 0.15, 0.2, 0.25):
        merged = greedy_merge(u, tol)
        internal = [v for v in merged if -20 <= v <= 47.5]
        print(f"   tol={tol}: merged={len(merged)} internal={len(internal)}")

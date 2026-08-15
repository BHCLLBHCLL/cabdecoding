"""Hypothesis: golden 'all' axis = rep axis + tess vertices beyond threshold."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec_all = next(r for r in g["records"] if r["input"]["vertex_detection"]==0 and r["input"]["threshold"]==[0.1,0.1,0.1])
rec_rep = next(r for r in g["records"] if r["input"]["vertex_detection"]==1 and r["input"]["threshold"]==[0.1,0.1,0.1])

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t) == "Impeller": imp = t
if imp is None: imp = tags[0]
verts_w = cab_vtk._apply_transform(sess.body_vertices(imp), TRANSFORM) * 1000.0
tess_w = cab_vtk._apply_transform(np.asarray(sess.facet_body(imp).points), TRANSFORM) * 1000.0

for ax in "xyz":
    i = "xyz".index(ax)
    A = np.array(rec_all["output"]["axes"][ax])
    R = np.array(rec_rep["output"]["axes"][ax])
    # how many all-points are within 1e-3 of a rep point?
    near_rep = sum(1 for v in A if np.any(np.abs(R - v) < 1e-3))
    # how many all-points are within 1e-3 of a tess vertex?
    tv = np.unique(np.round(tess_w[:,i], 9))
    near_tess = sum(1 for v in A if np.any(np.abs(tv - v) < 1e-3))
    # how many all-points are within 1e-3 of a b-rep vertex?
    bv = np.unique(np.round(verts_w[:,i], 9))
    near_brep = sum(1 for v in A if np.any(np.abs(bv - v) < 1e-3))
    # all-points NOT near rep (the "added" points)
    added = [v for v in A if not np.any(np.abs(R - v) < 1e-3)]
    print(f"{ax}: all={len(A)} rep={len(R)}; all-near-rep={near_rep}; all-near-tess={near_tess}; all-near-brep={near_brep}")
    if added:
        print(f"   added pts ({len(added)}): {np.round(added[:24],4).tolist()}")

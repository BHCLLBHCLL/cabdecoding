"""Check tess point coordinate projections for tr03 Impeller."""
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t) == "Impeller": imp = t
if imp is None: imp = tags[0]
verts = sess.body_vertices(imp) * 1000.0
tess = sess.facet_body(imp)
pts = np.asarray(tess.points) * 1000.0
print("tess points", pts.shape)
for ax in "xyz":
    i = "xyz".index(ax)
    u = np.unique(np.round(pts[:,i], 6))
    print(f"{ax}: {len(u)} distinct tess coords")
    print("   ", np.round(u[:40],4).tolist())
    if len(u) > 40: print("    ...", np.round(u[-10:],4).tolist())
print("B-rep vertices distinct:")
for ax in "xyz":
    i = "xyz".index(ax)
    u = np.unique(np.round(verts[:,i],6))
    print(f"  {ax}: {len(u)} -> {np.round(u,4).tolist()}")

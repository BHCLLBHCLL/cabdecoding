"""Check which WORLD-space vertices appear in golden 'all'/'rep' axis."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"

def world(pts_mm):
    return cab_vtk._apply_transform(np.asarray(pts_mm, float)/1000.0, TRANSFORM) * 1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t) == "Impeller": imp = t
if imp is None: imp = tags[0]
verts_w = world(sess.body_vertices(imp) * 1000.0)
tess_w = world(np.asarray(sess.facet_body(imp).points) * 1000.0)

for r in g["records"]:
    if r["input"]["threshold"] != [0.1,0.1,0.1]: continue
    vd = r["input"]["vertex_detection"]
    if vd not in (0,1): continue
    name = {0:"all",1:"rep"}[vd]
    print(f"=== vd{vd} {name} ===")
    for ax in "xyz":
        i = "xyz".index(ax)
        golden = np.array(r["output"]["axes"][ax])
        bv = np.unique(np.round(verts_w[:,i],6))
        tv = np.unique(np.round(tess_w[:,i],6))
        b_in = sum(1 for v in bv if np.any(np.abs(golden-v) < 1e-3))
        t_in = sum(1 for v in tv if np.any(np.abs(golden-v) < 1e-3))
        print(f"  {ax}: golden {len(golden)}; b-rep verts {len(bv)} in golden {b_in}; tess verts {len(tv)} in golden {t_in}")

"""Check which vertices appear in golden 'all' axis (B-rep vs tess)."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec = next(r for r in g["records"] if r["name"] == "tr03_imp_vd_0")

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t) == "Impeller": imp = t
if imp is None: imp = tags[0]
verts = sess.body_vertices(imp) * 1000.0
tess = np.asarray(sess.facet_body(imp).points) * 1000.0

for ax in "xyz":
    i = "xyz".index(ax)
    golden = np.array(rec["output"]["axes"][ax])
    bv = np.unique(np.round(verts[:,i], 6))
    tv = np.unique(np.round(tess[:,i], 6))
    # how many b-rep vertices are within 1e-3 of a golden point?
    b_in = sum(1 for v in bv if np.any(np.abs(golden - v) < 1e-3))
    t_in = sum(1 for v in tv if np.any(np.abs(golden - v) < 1e-3))
    print(f"{ax}: b-rep verts {len(bv)} in golden: {b_in}; tess verts {len(tv)} in golden: {t_in}")
    # how many golden points are close to a b-rep / tess vertex?
    g_b = sum(1 for v in golden if np.any(np.abs(bv - v) < 1e-3))
    g_t = sum(1 for v in golden if np.any(np.abs(tv - v) < 1e-3))
    print(f"    golden pts {len(golden)}; near b-rep {g_b}; near tess {g_t}")
    # list b-rep vertices NOT in golden
    b_missing = [v for v in bv if not np.any(np.abs(golden - v) < 1e-3)]
    if b_missing:
        print(f"    b-rep verts MISSING from golden: {np.round(b_missing,4).tolist()}")

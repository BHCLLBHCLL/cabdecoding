"""Check rep mode counts with transform + B-rep vertices."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p,float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t)=="Impeller": imp=t
if imp is None: imp=tags[0]
verts_w = world(sess.body_vertices(imp)*1000.0)
tess_w = world(np.asarray(sess.facet_body(imp).points)*1000.0)

for rec in g["records"]:
    if rec["input"]["threshold"] != [0.1,0.1,0.1]: continue
    vd = rec["input"]["vertex_detection"]
    if vd not in (1,3): continue
    name = {1:"rep",3:"minmax"}[vd]
    inp = rec["input"]
    det = {1:"representative",3:"minmax"}[vd]
    spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection=det, method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    lo = tess_w.min(0); hi = tess_w.max(0)
    _, detailed = cab_grid.build_axes({"Impeller": tess_w}, spec, part_vertices={"Impeller": verts_w}, part_bounds=(lo,hi))
    nat = tuple(len(detailed[a]) for a in "xyz")
    gold = tuple(len(rec["output"]["axes"][a]) for a in "xyz")
    print(f"{name}: native {nat} vs golden {gold}")

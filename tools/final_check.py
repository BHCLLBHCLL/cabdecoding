"""Final check: correct transform (no round-trip), all modes, vs golden counts."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
# Match cab_dialogs._mm: apply transform to METRES, then x1000 (no round-trip).
def to_world_mm(pts_m):
    return cab_vtk._apply_transform(np.asarray(pts_m, float), TRANSFORM) * 1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t)=="Impeller": imp=t
if imp is None: imp=tags[0]
verts_m = sess.body_vertices(imp)          # metres
tess_m = np.asarray(sess.facet_body(imp).points)  # metres
verts_w = to_world_mm(verts_m)
tess_w = to_world_mm(tess_m)

for rec in g["records"]:
    if rec["input"]["threshold"] != [0.1,0.1,0.1]: continue
    vd = rec["input"]["vertex_detection"]
    det = {0:"all",1:"representative",2:"axis_plane",3:"minmax",4:"not_considered",5:"uniform"}[vd]
    inp = rec["input"]
    spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection=det, method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    lo = tess_w.min(0); hi = tess_w.max(0)
    _, detailed = cab_grid.build_axes({"Impeller": tess_w}, spec, part_vertices={"Impeller": verts_w}, part_bounds=(lo,hi))
    nat = tuple(len(detailed[a]) for a in "xyz")
    gold = tuple(len(rec["output"]["axes"][a]) for a in "xyz")
    print(f"vd{vd} {det:14s}: native {nat} vs golden {gold}")

# P0 round 84: dump inputs, rough sets and gold S-lines for all+rep.
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next((t for t in tags if sess.body_name(t) == "Impeller"), None)
t = imp
part = sess.facet_body_stpre(t) or sess.facet_body(t)
P = world(np.asarray(part.points)*1000.0)
v = sess.body_vertices(t)
V = world(np.asarray(v)*1000.0) if v is not None and len(v) else None

print("B-rep vertices:", 0 if V is None else len(V))
if V is not None:
    print("  range:", np.round(V.min(0), 3), np.round(V.max(0), 3))
print("tess points:", len(P))

tess = {"Impeller": P}
verts = {"Impeller": V} if V is not None else {}
lo = P.min(0); hi = P.max(0)

for rec in g["records"]:
    if rec["input"]["threshold"] != [0.1, 0.1, 0.1]:
        continue
    vd = rec["input"]["vertex_detection"]
    if vd not in (0, 1):
        continue
    name = {0: "all", 1: "rep"}[vd]
    det = {0: "all", 1: "representative"}[vd]
    inp = rec["input"]
    print(f"\n=== {name} ===")
    print("  std:", inp["standard_length"], "ratio_in:", inp["ratio_in"],
          "ratio_out:", inp["ratio_out"], "domain:", inp["domain_min"],
          inp["domain_max"])
    spec = cab_grid.GridSpec(unit="mm",
        domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection=det, method="rough_and_detail",
        standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]),
        geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    rough = cab_grid.rough_grids(tess, spec, part_vertices=verts,
                                 part_detections=None)
    gold = rec["output"]["axes"]
    for ax in "xyz":
        r = np.asarray(rough[ax])
        gd = np.asarray(gold[ax])
        # gold S-lines = gold lines not adjacent-uniform; just show counts
        print(f"  {ax}: rough({len(r)}) =",
              [round(x, 3) for x in r][:20],
              "..." if len(r) > 20 else "")
        print(f"      gold({len(gd)}) first/last:",
              [round(x, 3) for x in gd[:6]], "...",
              [round(x, 3) for x in gd[-6:]])
        # uniform-step detection inside gold
        d = np.diff(gd)
        umax = np.bincount(np.round(d, 3).astype(str).apply(hash) if False
                           else np.unique(np.round(d, 3), return_counts=True)[1].max())
        vals, cnts = np.unique(np.round(d, 3), return_counts=True)
        top = np.argsort(cnts)[::-1][:4]
        print("      gold steps:", [(round(vals[k], 3), int(cnts[k])) for k in top])

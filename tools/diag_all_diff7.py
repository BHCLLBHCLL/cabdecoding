# P0 diagnostic round 7: microscope on y window [-9.2, -5.3] and z window
# [-3.5, 1.5]: raw projections vs our rough/detailed vs golden.
import json, sys, math
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
lo, hi = P.min(0), P.max(0)
v = sess.body_vertices(imp)
verts_w = world(np.asarray(v)*1000.0)

rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
inp = rec0["input"]
_orig = cab_grid.stpre_rules._trunc_round
cab_grid.stpre_rules._trunc_round = lambda x: max(1, math.ceil(x - 1e-9))
try:
    spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]),
        domain_max=tuple(inp["domain_max"]), vertex_detection="all",
        method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    rough, detailed = cab_grid.build_axes({"Impeller": P}, spec,
                                          part_vertices={"Impeller": verts_w},
                                          part_bounds=(lo, hi))
finally:
    cab_grid.stpre_rules._trunc_round = _orig

def show(i, ax, w0, w1):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    nat = np.asarray(detailed[ax], float)
    rgh = np.asarray(rough[ax], float)
    proj = np.unique(np.round(P[:, i], 6))
    print(f"\n=== {ax} window [{w0},{w1}] ===")
    print("proj:    ", [f"{x:.4f}" for x in proj if w0 <= x <= w1])
    print("rough:   ", [f"{x:.4f}" for x in rgh if w0 <= x <= w1])
    print("detailed:", [f"{x:.4f}" for x in nat if w0 <= x <= w1])
    print("golden:  ", [f"{x:.4f}" for x in gold if w0 <= x <= w1])

show(1, "y", -9.2, -5.3)
show(1, "y", -1.5, 5.0)
show(2, "z", -3.5, 1.5)
show(2, "z", 1.5, 8.5)

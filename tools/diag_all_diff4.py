# P0 diagnostic round 4: edge-vertex subset hypothesis for STpre "all".
# Uses fin_edge table (nodes on model edges) + ceil subdivision.
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
part = sess.facet_body_stpre(imp, want_fin_edge=True)
assert part is not None
print(f"tess: {len(part.points)} pts, {len(part.triangles)} tris, "
      f"edge_mask: {part.edge_mask is not None and int(part.edge_mask.sum())} "
      f"of {len(part.points)} nodes on model edges")

P = world(np.asarray(part.points) * 1000.0)
T = np.asarray(part.triangles)
mask = part.edge_mask
# sanity: corner-ish stats
print("x values of edge nodes:", sorted(set(np.round(P[mask][:, 0], 4)))[:12])

tess_all = P
tess_edge = P[mask]
lo, hi = tess_all.min(0), tess_all.max(0)
v = sess.body_vertices(imp)
verts_w = world(np.asarray(v)*1000.0)

base_recs = {r["input"]["vertex_detection"]: r for r in g["records"]
             if r["input"]["threshold"] == [0.1, 0.1, 0.1]}

_orig = cab_grid.stpre_rules._trunc_round
cab_grid.stpre_rules._trunc_round = lambda x: max(1, math.ceil(x - 1e-9))
try:
    rec = base_recs[0]
    inp = rec["input"]
    spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]),
        domain_max=tuple(inp["domain_max"]), vertex_detection="all",
        method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    for label, pts in (("all-vertices", tess_all), ("edge-vertices", tess_edge)):
        _, detailed = cab_grid.build_axes({"Impeller": pts}, spec,
                                          part_vertices={"Impeller": verts_w},
                                          part_bounds=(lo, hi))
        res = []
        for ax in "xyz":
            gold = np.asarray(rec["output"]["axes"][ax], float)
            nat = np.asarray(detailed[ax], float)
            if len(gold) == len(nat) and np.max(np.abs(np.sort(nat)-np.sort(gold))) <= 2e-4:
                res.append(f"{ax}:OK({len(nat)})")
            else:
                res.append(f"{ax}:{len(nat)}vs{len(gold)}")
        print(f"all-mode {label}: {res}")
finally:
    cab_grid.stpre_rules._trunc_round = _orig

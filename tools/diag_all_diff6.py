# P0 diagnostic round 6: classify per-line sources (feature vs subdiv) for
# y/z; find which native lines golden drops and what golden adds.
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

rough_set = {ax: set(np.round(np.asarray(rough[ax]), 6)) for ax in "xyz"}
for i, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    nat = np.asarray(detailed[ax], float)
    gold_set = set(np.round(gold, 4))
    nat_set = set(np.round(nat, 4))
    print(f"\n=== {ax}: native {len(nat)} golden {len(gold)} ===")
    proj = np.round(P[:, i], 6)
    dropped = []
    for nv in sorted(nat_set - gold_set):
        is_rough = round(nv, 6) in rough_set[ax]
        near_proj = bool(np.any(np.abs(proj - nv) < 1e-3))
        dropped.append((nv, "rough" if is_rough else "subdiv",
                        "proj" if near_proj else "-"))
    print(f"native-only ({len(dropped)}):")
    for nv, src, pr in dropped[:40]:
        print(f"   {nv:10.4f}  {src} {pr}")
    added = sorted(gold_set - nat_set)
    print(f"golden-only ({len(added)}): {[float(x) for x in added][:12]}")
    # golden line positions not near any projection
    no_proj = [float(x) for x in sorted(gold_set)
               if not np.any(np.abs(proj - x) < 1e-3)]
    print(f"golden lines NOT near any projection ({len(no_proj)}): "
          f"{no_proj[:15]}")

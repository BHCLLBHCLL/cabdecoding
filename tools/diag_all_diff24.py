# P0 diagnostic round 24: use kernel fin_edge nodes (TessPart.edge_mask)
# as the "all" mode anchor projections, then run the full rough+refine
# pipeline.  Compare native vs golden per axis, incl. rep z gap.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk, cab_grid

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))

tess, edge_nodes, verts = {}, {}, {}
imp = next((t for t in tags if sess.body_name(t) == "Impeller"), None)
for t in ([imp] if imp is not None else tags):
    name = sess.body_name(t) or f"body{t}"
    part = sess.facet_body_stpre(t, want_fin_edge=True)
    if part is None or len(part.points) == 0:
        continue
    P = world(np.asarray(part.points)*1000.0)
    tess[name] = P
    if part.edge_mask is not None and part.edge_mask.any():
        edge_nodes[name] = P[part.edge_mask]
        print(f"{name}: {len(P)} nodes, {int(part.edge_mask.sum())} edge nodes")
    else:
        print(f"{name}: {len(P)} nodes, NO edge mask")
    v = sess.body_vertices(t)
    if v is not None and len(v):
        verts[name] = world(np.asarray(v)*1000.0)

lo = np.min([a.min(0) for a in tess.values()], axis=0)
hi = np.max([a.max(0) for a in tess.values()], axis=0)

for rec in g["records"]:
    if rec["input"]["threshold"] != [0.1, 0.1, 0.1]:
        continue
    vd = rec["input"]["vertex_detection"]
    if vd not in (0, 1):
        continue
    name = {0: "all", 1: "rep"}[vd]
    det = {0: "all", 1: "representative"}[vd]
    inp = rec["input"]
    spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection=det, method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    if vd == 0:
        # all: minmax from full tess, anchors from edge nodes only
        pts = edge_nodes if edge_nodes else tess
        _, detailed = cab_grid.build_axes(pts, spec, part_vertices=verts, part_bounds=(lo, hi))
    else:
        _, detailed = cab_grid.build_axes(tess, spec, part_vertices=verts, part_bounds=(lo, hi))
    nat = tuple(len(detailed[a]) for a in "xyz")
    gold = tuple(len(rec["output"]["axes"][a]) for a in "xyz")
    print(f"{name}: native {nat} vs golden {gold}" + ("  MATCH" if nat == gold else "  DIFF"))
    if nat != gold:
        for ax in "xyz":
            nv = np.asarray(detailed[ax]); gv = np.asarray(rec["output"]["axes"][ax], float)
            print(f"  {ax}: n={len(nv)} gold={len(gv)}")
            only_n = np.setdiff1d(np.round(nv,4), np.round(gv,4))
            only_g = np.setdiff1d(np.round(gv,4), np.round(nv,4))
            print(f"    native-only ({len(only_n)}): {np.round(only_n,3)[:12]}")
            print(f"    golden-only ({len(only_g)}): {np.round(only_g,3)[:12]}")

# P0 diagnostic round 40: decompose all-mode gap into anchor layer (S)
# vs subdivision layer (N/B) using data/stpre_tr03_marks.json marks.
# Compare native rough lines (edge-node anchors) vs golden S lines, and
# native detailed-only lines vs golden N lines.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk, cab_grid

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
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
    v = sess.body_vertices(t)
    if v is not None and len(v):
        verts[name] = world(np.asarray(v)*1000.0)

lo = np.min([a.min(0) for a in tess.values()], axis=0)
hi = np.max([a.max(0) for a in tess.values()], axis=0)

rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
inp = rec0["input"]
spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
    vertex_detection="all", method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
    threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
    geometric_ratio_external=tuple(inp["ratio_out"]))

rough, detailed = cab_grid.build_axes(edge_nodes, spec, part_vertices=verts,
                                      part_bounds=(lo, hi))

mk = marks["tr03_imp_vd_0"]
for i_ax, ax in enumerate("xyz"):
    pairs = mk["axes"][i_ax] if isinstance(mk["axes"], list) and isinstance(mk["axes"][i_ax], list) else mk["axes"][ax]
    gold_s = np.array([v for v, m in pairs if m == "S"], float)
    gold_n = np.array([v for v, m in pairs if m == "N"], float)
    gold_b = np.array([v for v, m in pairs if m == "B"], float)
    nr = np.asarray(rough[ax], float)
    nd = np.asarray(detailed[ax], float)
    nsub = np.setdiff1d(np.round(nd, 4), np.round(nr, 4))
    print(f"== {ax} ==")
    print(f"gold: S={len(gold_s)} N={len(gold_n)} B={len(gold_b)} | native rough={len(nr)} sub={len(nsub)}")
    # anchor-layer diff
    r_only = np.setdiff1d(np.round(nr, 3), np.round(gold_s, 3))
    s_only = np.setdiff1d(np.round(gold_s, 3), np.round(nr, 3))
    print(f"  anchor: rough-only ({len(r_only)}): {np.round(r_only,2)[:16]}")
    print(f"          goldS-only ({len(s_only)}): {np.round(s_only,2)[:16]}")
    # subdivision-layer diff
    n_only = np.setdiff1d(np.round(nsub, 3), np.round(gold_n, 3))
    gn_only = np.setdiff1d(np.round(gold_n, 3), np.round(nsub, 3))
    print(f"  subdiv: nat-only ({len(n_only)}): {np.round(n_only,2)[:16]}")
    print(f"          goldN-only ({len(gn_only)}): {np.round(gn_only,2)[:16]}")

# P0 diagnostic round 9: full-axis side-by-side (mine vs golden) + body bboxes.
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
print("bodies:", [(t, sess.body_name(t)) for t in tags])

tess, verts = {}, {}
for t in tags:
    name = sess.body_name(t) or f"body{t}"
    part = sess.facet_body_stpre(t)
    if part is None or len(part.points) == 0:
        continue
    W = world(np.asarray(part.points)*1000.0)
    tess[name] = W
    v = sess.body_vertices(t)
    if v is not None and len(v):
        verts[name] = world(np.asarray(v)*1000.0)
    print(f"  {name}: pts={len(W)} bbox=({W.min(0).round(3)}, {W.max(0).round(3)})")

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
    lo = np.min([a.min(0) for a in tess.values()], axis=0)
    hi = np.max([a.max(0) for a in tess.values()], axis=0)
    rough, detailed = cab_grid.build_axes(tess, spec, part_vertices=verts,
                                          part_bounds=(lo, hi))
finally:
    cab_grid.stpre_rules._trunc_round = _orig

for i, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    rgh = np.asarray(rough[ax], float)
    det = np.asarray(detailed[ax], float)
    proj = np.unique(np.round(np.concatenate([a[:, i] for a in tess.values()]), 6))
    print(f"\n=== {ax}: proj={len(proj)} rough={len(rgh)} det={len(det)} gold={len(gold)} ===")
    print("gold head 12:", " ".join(f"{x:.4f}" for x in gold[:12]))
    print("det  head 12:", " ".join(f"{x:.4f}" for x in det[:12]))
    print("gold tail 12:", " ".join(f"{x:.4f}" for x in gold[-12:]))
    print("det  tail 12:", " ".join(f"{x:.4f}" for x in det[-12:]))
    # rough-vs-gold membership (within 0.05)
    in_gold = np.array([np.any(np.abs(gold - v) < 0.05) for v in rgh])
    print(f"rough lines matched in gold: {in_gold.sum()}/{len(rgh)}")
    unmatched = rgh[~in_gold]
    if len(unmatched):
        print("  rough NOT in gold:", " ".join(f"{x:.4f}" for x in unmatched[:20]))
    # gold lines that are not near any rough (=> subdivision lines)
    sub = np.array([not np.any(np.abs(rgh - v) < 0.05) for v in gold])
    print(f"gold lines not near rough: {sub.sum()}")

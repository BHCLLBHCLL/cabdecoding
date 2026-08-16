# P0 round 80: full-axis line-level diff native vs gold (all mode).
import json, sys
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
imp = next((t for t in tags if sess.body_name(t) == "Impeller"), None)
tess = {}
verts = {}
for t in ([imp] if imp is not None else tags):
    name = sess.body_name(t) or f"body{t}"
    part = sess.facet_body_stpre(t) or sess.facet_body(t)
    if part is None or len(part.points) == 0:
        continue
    tess[name] = world(np.asarray(part.points)*1000.0)
    v = sess.body_vertices(t)
    if v is not None and len(v):
        verts[name] = world(np.asarray(v)*1000.0)

rec = next(r for r in g["records"]
           if r["input"]["threshold"] == [0.1, 0.1, 0.1]
           and r["input"]["vertex_detection"] == 0)
inp = rec["input"]
spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]),
    domain_max=tuple(inp["domain_max"]), vertex_detection="all",
    method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
    threshold_length=tuple(inp["threshold"]),
    geometric_ratio=tuple(inp["ratio_in"]),
    geometric_ratio_external=tuple(inp["ratio_out"]))
lo = np.min([a.min(0) for a in tess.values()], axis=0)
hi = np.max([a.max(0) for a in tess.values()], axis=0)
_, detailed = cab_grid.build_axes(tess, spec, part_vertices=verts,
                                  part_bounds=(lo, hi))
for i, ax in enumerate("xyz"):
    nat = np.asarray(detailed[ax], float)
    gold = np.asarray(rec["output"]["axes"][ax], float)
    miss = [v for v in gold if not np.any(np.abs(nat - v) < 0.05)]
    extra = [v for v in nat if not np.any(np.abs(gold - v) < 0.05)]
    print(f"\n{ax}: native={len(nat)} gold={len(gold)} "
          f"miss={len(miss)} extra={len(extra)}")
    print("  miss :", [round(v, 3) for v in miss])
    print("  extra:", [round(v, 3) for v in extra])
    # local context of misses in gold
    for v in miss:
        j = int(np.argmin(np.abs(gold - v)))
        ctx = gold[max(0, j-2):j+3]
        print(f"    gold ctx {v:9.3f}: {[round(c,3) for c in ctx]}")

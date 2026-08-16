# P0 diagnostic: compare golden axis VALUES vs native axis VALUES per axis
# for tr03 all/rep modes; show which lines we have extra / miss, and test
# candidate hypotheses (AABB of other bodies, merge tolerances).
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
print("bodies:", [(t, sess.body_name(t)) for t in tags])

tess = {}
verts = {}
bboxes = {}
for t in tags:
    name = sess.body_name(t) or f"body{t}"
    part = sess.facet_body_stpre(t)
    if part is None or len(part.points) == 0:
        continue
    w = world(np.asarray(part.points)*1000.0)
    tess[name] = w
    bboxes[name] = (w.min(0), w.max(0))
    v = sess.body_vertices(t)
    if v is not None and len(v):
        verts[name] = world(np.asarray(v)*1000.0)

imp_tess = tess["Impeller"]
rec = next(r for r in g["records"]
           if r["input"]["threshold"] == [0.1,0.1,0.1]
           and r["input"]["vertex_detection"] == 0)
inp = rec["input"]
spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
    vertex_detection="all", method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
    threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
    geometric_ratio_external=tuple(inp["ratio_out"]))
lo = np.min([a.min(0) for a in tess.values()], axis=0)
hi = np.max([a.max(0) for a in tess.values()], axis=0)
_, detailed = cab_grid.build_axes(tess, spec, part_vertices=verts, part_bounds=(lo, hi))

for i, ax in enumerate("xyz"):
    gold = np.asarray(rec["output"]["axes"][ax], float)
    nat = np.asarray(detailed[ax], float)
    print(f"\n=== {ax}: golden {len(gold)} lines, native {len(nat)} ===")
    # nearest-golden match for every native line
    used = np.zeros(len(gold), bool)
    for nv in nat:
        d = np.abs(gold - nv)
        j = int(np.argmin(d))
        used[j] = True
    extra = [float(v) for v in nat if np.min(np.abs(gold - v)) > 1e-6]
    missing = [float(gold[j]) for j in range(len(gold)) if not used[j]]
    print(f"native-only ({len(extra)}): {[round(v,4) for v in extra][:20]}")
    print(f"golden-only ({len(missing)}): {[round(v,4) for v in missing][:20]}")
    # matched line max deviation
    devs = [float(np.min(np.abs(gold - v))) for v in nat if np.min(np.abs(gold - v)) <= 1e-6]
    if devs:
        print(f"matched count {len(devs)}")
    # gaps analysis on golden: unique spacings
    dg = np.diff(gold)
    print(f"golden spacing min/med/max: {dg.min():.4f}/{np.median(dg):.4f}/{dg.max():.4f}")

# hypothesis: golden all = Impeller tess verts + other bodies AABB min/max
other = [n for n in tess if n != "Impeller"]
print("\nother bodies:", other, {n: bboxes[n] for n in other})

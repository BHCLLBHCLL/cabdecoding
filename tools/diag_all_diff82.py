# P0 round 82: discriminator hunt for mixed interval counts:
# print every rough interval with q=L/std in [1.0,2.6) together with
# position, part-bounds side, and gold n; mark n vs ceil/round.
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
for t in ([imp] if imp is not None else tags):
    part = sess.facet_body_stpre(t) or sess.facet_body(t)
    if part is None or len(part.points) == 0:
        continue
    tess[sess.body_name(t) or f"body{t}"] = world(np.asarray(part.points)*1000.0)

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
rough = cab_grid.rough_grids(tess, spec)

for i, ax in enumerate("xyz"):
    gold = np.asarray(rec["output"]["axes"][ax], float)
    r = np.asarray(rough[ax], float)
    std = float(inp["standard_length"][i])
    print(f"\n=== {ax} (part {lo[i]:.1f}..{hi[i]:.1f}, dom "
          f"{r[0]:.1f}..{r[-1]:.1f}) ===")
    for a, b in zip(r[:-1], r[1:]):
        L = b - a
        q = L / std
        if not (0.95 <= q <= 2.6):
            continue
        inside = gold[(gold > a + 0.05) & (gold < b - 0.05)]
        n = len(inside) + 1
        ce = int(np.ceil(q - 1e-9))
        rd = int(q + 0.5)
        mid = (a + b) / 2
        where = "IN" if lo[i] <= mid <= hi[i] else "OUT"
        tag = "ceil" if n == ce and ce != rd else \
              ("round" if n == rd and ce != rd else "both" if ce == rd else "???")
        gaps = np.diff(np.concatenate([[a], inside, [b]]))
        print(f"  [{a:8.3f},{b:8.3f}] L={L:6.3f} q={q:5.3f} n={n} "
              f"({tag:5s}) {where} steps={[round(x,3) for x in gaps]}")

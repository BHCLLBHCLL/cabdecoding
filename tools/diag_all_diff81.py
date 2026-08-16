# P0 round 81: fit the interval-count rule.  For each interval between
# adjacent ROUGH lines (rough grid from clipped projections + AABB +
# boundary), find how many gold lines fall strictly inside and print
# (L, L/std, n_inside+1=intervals) per axis.
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
rough, _ = cab_grid.build_axes(tess, spec, part_vertices=None,
                               part_bounds=(lo, hi), want_rough=True) \
    if "want_rough" in cab_grid.build_axes.__code__.co_varnames else \
    cab_grid.rough_grids(tess, spec), None
rough = cab_grid.rough_grids(tess, spec)

rows = []
for i, ax in enumerate("xyz"):
    gold = np.asarray(rec["output"]["axes"][ax], float)
    r = np.asarray(rough[ax], float)
    std = float(inp["standard_length"][i])
    for a, b in zip(r[:-1], r[1:]):
        inside = gold[(gold > a + 0.05) & (gold < b - 0.05)]
        n = len(inside) + 1
        rows.append((ax, b - a, (b - a) / std, n, std))
# aggregate: group by ceil vs round prediction
from collections import defaultdict
tab = defaultdict(list)
for ax, L, q, n, std in rows:
    c = int(np.ceil(q - 1e-9)) if q > 0 else 1
    rd = int(q + 0.5)
    key = (min(c, rd), max(c, rd)) if c != rd else (c,)
    tab[(c, rd)].append((ax, round(L, 3), round(q, 3), n))
for (c, rd), lst in sorted(tab.items()):
    print(f"ceil={c} round={rd}: {len(lst)} intervals")
    agree_c = sum(1 for *_x, n in lst if n == c)
    agree_r = sum(1 for *_x, n in lst if n == rd)
    print(f"   n==ceil: {agree_c}   n==round: {agree_r}")
    for ax, L, q, n in lst[:14]:
        print(f"   {ax} L={L:8.3f} L/std={q:7.3f} n={n}")

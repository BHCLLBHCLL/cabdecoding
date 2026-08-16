# P0 round 83: per-line diff of detailed axes (all + rep) vs gold.
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))

tess, verts = {}, {}
imp = next((t for t in tags if sess.body_name(t) == "Impeller"), None)
for t in ([imp] if imp is not None else tags):
    name = sess.body_name(t) or f"body{t}"
    part = sess.facet_body_stpre(t) or sess.facet_body(t)
    if part is None or len(part.points) == 0:
        continue
    tess[name] = world(np.asarray(part.points)*1000.0)
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
    spec = cab_grid.GridSpec(unit="mm",
        domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection=det, method="rough_and_detail",
        standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]),
        geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    rough, detailed = cab_grid.build_axes(tess, spec, part_vertices=verts,
                                          part_bounds=(lo, hi))
    print(f"=== {name} ===")
    for i, ax in enumerate("xyz"):
        m = np.asarray(detailed[ax], float)
        gold = np.asarray(rec["output"]["axes"][ax], float)
        ex = m[~np.isclose(m[None, :], gold[:, None], atol=0.05).any(0)] \
            if len(m) else []
        ms = gold[~np.isclose(gold[None, :], m[:, None], atol=0.05).any(0)] \
            if len(gold) else []
        print(f"{ax}: nat={len(m)} gold={len(gold)} "
              f"extra={len(ex)} miss={len(ms)}")
        if len(ex):
            print("  extra:", [round(x, 3) for x in ex][:15])
        if len(ms):
            print("  miss :", [round(x, 3) for x in ms][:15])
        if ax == "x" and name == "all":
            print("  nat full:", [round(x, 2) for x in m])
            print("  gold fll:", [round(x, 2) for x in gold])

# P0 round 85: exact S-line values; native vs gold interval split counts.
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
imp = next((t for t in tags if sess.body_name(t) == "Impeller"), None)
part = sess.facet_body_stpre(imp) or sess.facet_body(imp)
P = world(np.asarray(part.points)*1000.0)
tess = {"Impeller": P}

for rec in g["records"]:
    if rec["input"]["threshold"] != [0.1, 0.1, 0.1]:
        continue
    vd = rec["input"]["vertex_detection"]
    if vd != 0:
        continue
    inp = rec["input"]
    spec = cab_grid.GridSpec(unit="mm",
        domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection="all", method="rough_and_detail",
        standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]),
        geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    rough = cab_grid.rough_grids(tess, spec)
    gold = np.asarray(rec["output"]["axes"]["x"], float)
    r = rough["x"]
    print("rough x exact:", [repr(x) for x in r])
    print("gold x around S-lines:")
    for s in r[1:-1]:
        near = gold[np.abs(gold - s) < 0.2]
        print(f"  S {s!r}: gold near -> {[repr(x) for x in near]}")
    # per-interval split counts native vs gold
    print("intervals:")
    for a, b in zip(r[:-1], r[1:]):
        L = b - a
        n_nat = max(1, int(L / 1.0 + 2.0 / 3.0))
        gin = gold[(gold > a + 0.05) & (gold < b - 0.05)]
        print(f"  [{a:.6f},{b:.6f}] L={L:.6f} q={L:.4f} "
              f"n_nat={n_nat} gold_inside={len(gin)}")
    # raw node x values near -6.67 / 0 / 6.67
    inside = np.all((P >= np.array([-20, -20, -20]) - 1e-6)
                    & (P <= np.array([70, 120, 120]) + 1e-6), axis=1)
    xs = np.sort(P[inside, 0])
    for center in (-6.6667, 0.0, 6.6667):
        near = xs[np.abs(xs - center) < 0.15]
        print(f"tess nodes near x={center}: {[repr(x) for x in near[:8]]}")

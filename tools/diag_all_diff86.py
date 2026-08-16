# P0 round 86: rep-mode S-line set analysis (native B-rep verts vs gold).
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

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
v = sess.body_vertices(imp)
V = world(np.asarray(v)*1000.0)

dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))

recs = {r["input"]["vertex_detection"]: r for r in g["records"]
        if r["input"]["threshold"] == [0.1, 0.1, 0.1]}
rec1 = recs[1]

for i, ax in enumerate("xyz"):
    gold_det = np.asarray(rec1["output"]["axes"][ax], float)
    # S-lines: cluster boundaries of non-uniform steps; approximate by
    # finding gold lines also present in ALL gold (S-lines survive modes)
    # Simpler: gold S = merged(B-rep verts) per diag79 recipe
    vals = list(V[:, i]) + [V[:, i].min(), V[:, i].max()]
    v2 = np.sort(np.asarray(vals, float))
    lo, hi = dom[0][i], dom[1][i]
    v2 = v2[(v2 > lo + 0.1) & (v2 < hi - 0.1)]
    out = []
    for x in v2:
        if not out or abs(x - out[-1]) > 1e-3:
            out.append(float(x))
    m = [out[0]] if out else []
    for x in out[1:]:
        if x - m[-1] > 0.1:
            m.append(x)
    m = np.asarray(m)
    print(f"--- {ax}: B-rep merged S = {len(m)}")
    print("   ", [round(x, 3) for x in m])
    # uniform-step reconstruction: which gold lines are NOT explained by
    # equal splits of the S set + domain bounds?
    print(f"    gold det count = {len(gold_det)}")

# vertex-level info: which B-rep verts survive clipping
inside = np.all((V >= np.array(dom[0]) - 1e-6)
                & (V <= np.array(dom[1]) + 1e-6), axis=1)
print("\nB-rep verts:", len(V), "inside domain:", int(inside.sum()))
for i, ax in enumerate("xyz"):
    vals = V[inside, i]
    print(f"{ax}: inside-projections unique(1e-3):",
          len(np.unique(np.round(vals, 3))))

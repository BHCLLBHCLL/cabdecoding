# P0 diagnostic round 13: simulate greedy node registration in facet node
# order (collector 0x1ab90 semantics): anchors first, then per-node coords,
# keep if farther than thr from every existing line. Compare vs golden S.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
dom_lo = np.asarray(rec0["input"]["domain_min"], float)
dom_hi = np.asarray(rec0["input"]["domain_max"], float)

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)

# STL triangle-order node sequence as alternative order
stl_path = ROOT/"tools"/"probe_work"/"imp_stpre.stl"
raw = stl_path.read_bytes().decode("ascii", "ignore").split()
tris, i = [], 0
while i < len(raw):
    if raw[i] == "vertex":
        tris.append((float(raw[i+1]), float(raw[i+2]), float(raw[i+3])))
        i += 4
    else:
        i += 1
ST = np.asarray(tris)*1000.0

def greedy(coords, anchors, thr):
    lines = sorted(anchors)
    for c in coords:
        if np.min(np.abs(np.asarray(lines) - c)) >= thr:
            lines.append(c)
            lines.sort()
    return np.asarray(lines)

TOL = 0.02
for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    # golden S set = gold lines near an STL value
    stl_vals = np.unique(np.round(ST[:, i_ax], 6))
    S = np.array([v for v in gold if np.any(np.abs(stl_vals - v) < TOL)])
    print(f"\n=== {ax}: golden S={len(S)} ===")
    for thr in (0.1, 0.11, 0.15, 0.2):
        for name, seq in (("decode", P[:, i_ax]), ("stl", ST[:, i_ax])):
            sim = greedy(seq, [dom_lo[i_ax], dom_hi[i_ax]], thr)
            sim = sim[(sim >= dom_lo[i_ax] - 1e-9) & (sim <= dom_hi[i_ax] + 1e-9)]
            # match: how many sim lines coincide with a golden S line
            hit = sum(1 for v in sim if np.any(np.abs(S - v) < TOL))
            miss_S = sum(1 for v in S if not np.any(np.abs(sim - v) < TOL))
            extra = len(sim) - hit
            print(f"  thr={thr} {name}: sim={len(sim)} hitS={hit}/{len(S)} "
                  f"missingS={miss_S} extra={extra}")

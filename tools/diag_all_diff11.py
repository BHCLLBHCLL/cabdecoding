# P0 diagnostic round 11: authoritative comparison using STpre's own STL
# (tools/probe_work/imp_stpre.stl, the display mesh SaveStlFile exported).
# 1) STL projections vs golden axes -> classify golden lines as S(rough)/fine.
# 2) my facet_body_stpre vs STL -> verify the "recipe exact" claim.
import json, sys, math
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

# --- load STL (ascii or binary, metres, world) ---
stl_path = ROOT/"tools"/"probe_work"/"imp_stpre.stl"
raw = stl_path.read_bytes()
if raw[:5] == b"solid":
    txt = raw.decode("ascii", "ignore").split()
    V = np.array([float(txt[i]) for i in range(0, len(txt)) if False])  # placeholder
    vals, i = [], 0
    toks = txt
    while i < len(toks):
        if toks[i] == "vertex":
            vals.append((float(toks[i+1]), float(toks[i+2]), float(toks[i+3])))
            i += 4
        else:
            i += 1
    S = np.asarray(vals)*1000.0  # m -> mm
else:
    n = int.from_bytes(raw[80:84], "little")
    S = np.zeros((n*3, 3))
    for k in range(n):
        off = 84 + k*50 + 12
        for v in range(3):
            S[k*3+v] = np.frombuffer(raw[off+v*12:off+v*12+12], "<f4")
    S = S.astype(float)*1000.0
Su = np.unique(np.round(S, 6), axis=0)
print(f"STL: {len(S)} verts, {len(Su)} unique (world mm)")

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

# --- my facet ---
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
print(f"my facet: {len(P)} nodes (world mm)")

TOL = 0.02
for i, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    stlp = np.unique(np.round(Su[:, i], 6))
    myp = np.unique(np.round(P[:, i], 6))
    s_hit = np.array([np.any(np.abs(stlp - v) < TOL) for v in gold])
    m_hit = np.array([np.any(np.abs(myp - v) < TOL) for v in gold])
    print(f"\n=== {ax} gold={len(gold)} S(stl)={s_hit.sum()} near-my={m_hit.sum()}")
    # golden rough (=S) lines, and interval decomposition using them
    Sb = gold[s_hit]
    dS = np.diff(Sb)
    print("S-lines:", " ".join(f"{x:.4f}" for x in Sb))
    print("S gaps:  ", " ".join(f"{x:.3f}" for x in dS))
    # every gold line between consecutive S lines: count + uniformity
    rows = []
    for a, b in zip(Sb[:-1], Sb[1:]):
        inside = gold[(gold > a + TOL) & (gold < b - TOL)]
        if len(inside) or b - a > 0.05:
            seq = np.concatenate([[a], inside, [b]])
            d = np.diff(seq)
            rows.append((a, b, b - a, len(inside) + 1, d))
    print("span,n,spacing-uniform:")
    for a, b, s, n, d in rows:
        ceil_pred = max(1, math.ceil(s - 1e-9))
        mark = "OK" if n == ceil_pred else f"ceil={ceil_pred} MISM"
        print(f"  [{a:9.4f},{b:9.4f}] span={s:8.4f} n={n:2d} dev={d.max()-d.min():.4f} {mark}")
    # STL S-lines missing from gold
    inside_dom = stlp[(stlp >= gold[0] - 0.05) & (stlp <= gold[-1] + 0.05)]
    miss = [v for v in inside_dom if not np.any(np.abs(gold - v) < TOL)]
    print(f"STL lines in-domain not in gold: {len(miss)}")

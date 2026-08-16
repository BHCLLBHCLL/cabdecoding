# P0 round 78: recipe = clip nodes to dom  U  per-edge axis min/max
# (edge extremes), project, merge d=threshold(0.1).  Verify == gold.
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_0"]
dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))
gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i]+0.1 < v < dom[1][i]-0.1])
        for i, ax in enumerate("xyz")}

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points) * 1000.0)
tri = part.triangles
em = np.asarray(part.edge_mask, bool)
N = len(P)

lo = np.asarray(dom[0]); hi = np.asarray(dom[1])
inside = np.all((P >= lo - 1e-6) & (P <= hi + 1e-6), axis=1)

# polylines (connected components of edge nodes)
adj = {}
for a, b, c in tri:
    for u, v in ((a, b), (b, c), (c, a)):
        adj.setdefault(int(u), set()).add(int(v))
        adj.setdefault(int(v), set()).add(int(u))
ens = set(int(i) for i in np.where(em)[0])
eadj = {u: (adj.get(u, set()) & ens) for u in ens}
polylines = []
visited = set()
for s in sorted(ens):
    if s in visited:
        continue
    seq = [s]
    visited.add(s)
    cur, prev = s, -1
    while True:
        nxt = [x for x in eadj[cur] if x != prev]
        pick = None
        for x in nxt:
            if x not in visited:
                pick = x
                break
        if pick is None:
            break
        prev, cur = cur, pick
        visited.add(cur)
        seq.append(cur)
    if len(seq) >= 2:
        polylines.append(seq)
print(f"polylines={len(polylines)}")

def proj_and_merge(values, i_ax, d):
    v = np.sort(np.asarray(values, float))
    lox, hix = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lox+0.1) & (v < hix-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    merged = [out[0]] if out else []
    for x in out[1:]:
        if x - merged[-1] > d:
            merged.append(x)
    return np.asarray(out), np.asarray(merged)

for variant in ("clip-only", "clip+edge-extremes"):
    print(f"\n--- {variant} ---")
    for i_ax, ax in enumerate("xyz"):
        vals = list(P[inside, i_ax])
        if variant == "clip+edge-extremes":
            for seq in polylines:
                pts = P[seq]
                vals.append(pts[:, i_ax].min())
                vals.append(pts[:, i_ax].max())
        cand, m = proj_and_merge(vals, i_ax, 0.1)
        g = gold[ax]
        ex = sum(1 for v in m if not np.any(np.abs(g-v) < 0.1))
        ms = sum(1 for v in g if not np.any(np.abs(m-v) < 0.1))
        dev = max((np.min(np.abs(g-v)) for v in m), default=0)
        print(f"{ax}: raw={len(cand)} merged={len(m)} gold={len(g)} "
              f"extras={ex} miss={ms} maxdev={dev:.4f}")
        if ex:
            print("   extras:", [round(v,3) for v in m
                                 if not np.any(np.abs(g-v) < 0.1)][:20])
        if ms:
            print("   miss:", [round(v,3) for v in g
                               if not np.any(np.abs(m-v) < 0.1)][:20])

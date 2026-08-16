# P0 round 70: on the correct display mesh, attribute every extra
# gold-missing projected value to its source nodes: which polyline,
# endpoint vs middle, on-edge vs interior, local edge-degree.
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

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points) * 1000.0)
tri = part.triangles
em = np.asarray(part.edge_mask, bool)

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
pl_of = {}
for k, seq in enumerate(polylines):
    for i in seq:
        pl_of[i] = k
ends = {seq[0] for seq in polylines} | {seq[-1] for seq in polylines}
print(f"polylines={len(polylines)} pts={sum(len(s) for s in polylines)}")

gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i]+0.1 < v < dom[1][i]-0.1])
        for i, ax in enumerate("xyz")}

def proj_vals(vals, i_ax):
    v = np.sort(np.asarray(vals, float))
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lo+0.1) & (v < hi-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

def analyze(i_ax, ax):
    g = gold[ax]
    cand = proj_vals(P[:, i_ax], i_ax)
    extras = [v for v in cand if not np.any(np.abs(g-v) < 0.1)]
    print(f"\n=== {ax}: extras={len(extras)}")
    n_extra_only_mid = n_extra_only_end = n_extra_mixed = 0
    for v in extras:
        nodes = [i for i in range(len(P)) if abs(P[i, i_ax]-v) < 1e-3]
        # does ANY of these nodes project into gold for the other axes?
        info = []
        for i in nodes:
            on_e = bool(em[i])
            pl = pl_of.get(i, -1)
            is_end = i in ends
            # other-axis membership
            yz = "".join(
                "G" if np.any(np.abs(gold[a2]-P[i, j]) < 0.1) else "x"
                for j, a2 in enumerate("xyz") if j != i_ax)
            info.append((i, on_e, pl, is_end, yz))
        all_end = all(t[3] for t in info if t[1])
        all_mid = all(not t[3] for t in info if t[1])
        if all_end:
            n_extra_only_end += 1
        elif all_mid:
            n_extra_only_mid += 1
        else:
            n_extra_mixed += 1
        if len(extras) <= 30:
            print(f"  v={v:8.3f} nodes={info}")
    print(f"  summary: only-end={n_extra_only_end} only-mid="
          f"{n_extra_only_mid} mixed={n_extra_mixed}")

for i_ax, ax in enumerate("xyz"):
    analyze(i_ax, ax)

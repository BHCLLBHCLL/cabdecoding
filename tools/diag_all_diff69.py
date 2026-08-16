# P0 round 69: use facet_body_stpre(want_fin_edge=True) - correct D
# (bbox diagonal) and consistent mesh+edge_mask; retest
#   S-lines = interior projections U ThinOut(edge polylines, eps).
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
assert part is not None and part.edge_mask is not None
P = world(np.asarray(part.points) * 1000.0)
tri = part.triangles
em = np.asarray(part.edge_mask, bool)
D = float(np.linalg.norm(P.max(0) - P.min(0)))   # diagonal, mm
print(f"nodes={len(P)} tris={len(tri)} on-edge={int(em.sum())} "
      f"interior={int((~em).sum())} D={D:.2f}")

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

interior = np.where(~em)[0]
for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    c = proj_vals(P[interior, i_ax], i_ax)
    ex = [v for v in c if not np.any(np.abs(g-v) < 0.1)]
    ms = [v for v in g if not np.any(np.abs(c-v) < 0.1)]
    print(f"{ax}: interior cand={len(c)} gold={len(g)} "
          f"extras={len(ex)} miss={len(ms)}")

# adjacency from triangles
adj = {}
for a, b, c in tri:
    for u, v in ((a, b), (b, c), (c, a)):
        adj.setdefault(int(u), set()).add(int(v))
        adj.setdefault(int(v), set()).add(int(u))

# edge polylines: connected components of the mesh restricted to edge nodes
ens = set(int(i) for i in np.where(em)[0])
eadj = {u: (adj.get(u, set()) & ens) for u in ens}
polylines = []
visited = set()
for s in ens:
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
lens = [len(p) for p in polylines]
print(f"polylines={len(polylines)} len min/med/max="
      f"{min(lens)}/{int(np.median(lens))}/{max(lens)} pts={sum(lens)}")

print()
for tol in (0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02):
    eps = max(1e-8, tol) * D
    kept = set(interior.tolist())
    for seq in polylines:
        keep = [seq[0]]
        for i in seq[1:]:
            if np.linalg.norm(P[i] - P[keep[-1]]) >= eps:
                keep.append(i)
        kept.update(keep)
    idx = np.array(sorted(kept))
    line = f"tol={tol:<7} eps={eps:6.3f} "
    for i_ax, ax in enumerate("xyz"):
        cand = proj_vals(P[idx, i_ax], i_ax)
        ex = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
        ms = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
        line += f"{ax}:{len(cand)}/{len(gold[ax])} +{ex}/-{ms}  "
    print(line)

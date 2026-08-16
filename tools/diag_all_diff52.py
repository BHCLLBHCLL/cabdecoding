# P0 round 52: test the S-line recipe
#   S = {interior tess nodes} + {edge-polyline nodes surviving greedy
#       ThinOut(eps)}  with  eps = max(1e-8, tol) * bbox_max_extent
# against golden S lines (data/stpre_tr03_marks.json, vd_0).
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

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp, want_fin_edge=True)
assert part is not None and part.edge_mask is not None
P = world(np.asarray(part.points)*1000.0)
tris = part.triangles
E = part.edge_mask
ext = P.max(0) - P.min(0)
D = float(ext.max())
print(f"nodes={len(P)} edge={int(E.sum())} bbox_extent={ext.round(3)} D={D:.2f}")

# mesh edges shared by exactly 2 triangles; model-edge segments = both ends
# in edge_mask
cnt = {}
for a, b, c in tris:
    for u, v in ((a, b), (b, c), (c, a)):
        k = (u, v) if u < v else (v, u)
        cnt[k] = cnt.get(k, 0) + 1
adj = {}
for (u, v), n in cnt.items():
    if n == 2 and E[u] and E[v]:
        adj.setdefault(int(u), set()).add(int(v))
        adj.setdefault(int(v), set()).add(int(u))
print(f"edge-graph nodes={len(adj)}")

# walk chains: start at endpoints (deg 1) or arbitrary unvisited (closed)
visited = set()
polys = []
starts = sorted(n for n in adj if len(adj[n]) == 1)
for s in starts:
    if s in visited:
        continue
    chain = [s]
    visited.add(s)
    cur, prev = s, -1
    while True:
        nxt = [x for x in adj[cur] if x != prev and x not in visited]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        visited.add(cur)
        chain.append(cur)
    polys.append(chain)
for s in sorted(adj):
    if s in visited:
        continue
    chain = [s]
    visited.add(s)
    cur, prev = s, -1
    while True:
        nxt = [x for x in adj[cur] if x != prev and x not in visited]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        visited.add(cur)
        chain.append(cur)
    polys.append(chain)
print(f"polylines={len(polys)} lens min/med/max="
      f"{min(map(len,polys))}/{int(np.median(list(map(len,polys))))}/{max(map(len,polys))}")

interior = P[~E]

def thinout(seq_pts, eps):
    """greedy keep-first: keep pts[0], then next at 3D dist >= eps."""
    keep = [seq_pts[0]]
    for q in seq_pts[1:]:
        if np.linalg.norm(q - keep[-1]) >= eps:
            keep.append(q)
    return keep

def dedupe(vals, lo, hi, tol=0.1):
    v = np.sort(np.asarray(vals, float))
    v = v[(v >= lo - tol) & (v <= hi + tol)]
    out = []
    for x in v:
        if not out or abs(x - out[-1]) > tol:
            out.append(float(x))
    return np.asarray(out)

dom = ((-25.0, -25.0, -20.0), (25.0, 25.0, 120.0))
for tol in (0.0, 0.001, 0.003, 0.005, 0.01, 0.02, 0.05, 0.1):
    eps = max(1e-8, tol) * D
    kept = []
    for ch in polys:
        seq = P[ch]
        k1 = thinout(seq, eps)
        k2 = thinout(seq[::-1], eps)
        kept.extend(k1)
        kept.extend(k2)
    kept = np.asarray(kept)
    line = f"tol={tol:<6} eps={eps:7.3f} "
    for i_ax, ax in enumerate("xyz"):
        gold = np.asarray(mk["s_lines"][ax], float)
        cand = dedupe(np.concatenate([interior[:, i_ax], kept[:, i_ax]]),
                      dom[0][i_ax], dom[1][i_ax])
        n_extra = sum(1 for v in cand
                      if not np.any(np.abs(gold - v) < 0.1))
        n_miss = sum(1 for v in gold
                     if not np.any(np.abs(cand - v) < 0.1))
        line += f"{ax}:cand={len(cand)}/g={len(gold)} +{n_extra}/-{n_miss}  "
    print(line)

# P0 round 74: exact feasibility of polyline-level include/exclude:
#  extra value -> ALL polylines producing it must be excluded
#  gold value -> >=1 producing polyline included (interior always in)
# Then inspect which polylines get excluded and their geometry.
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
interior = [i for i in range(len(P)) if i not in pl_of]

def proj_vals(vals, i_ax):
    v = np.sort(np.asarray(vals, float))
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lo+0.1) & (v < hi-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

# value -> set of polylines producing it (interior = -1, always included)
for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    cand = proj_vals(P[:, i_ax], i_ax)
    val_pls = {}
    for v in cand:
        pls = {-1} if any(abs(P[i, i_ax]-v) < 1e-3 and i in interior
                          for i in range(len(P))) else set()
        for i in range(len(P)):
            if abs(P[i, i_ax]-v) < 1e-3 and i in pl_of:
                pls.add(pl_of[i])
        val_pls[v] = pls
    extras = [v for v in cand if not np.any(np.abs(g-v) < 0.1)]
    must_excl = set()
    for v in extras:
        must_excl |= (val_pls[v] - {-1})
    # conflict: a gold value produced ONLY by excluded polylines
    conflicts = []
    for w in g:
        pls = None
        for v in cand:
            if abs(v-w) < 0.1:
                pls = val_pls[v]
                break
        if pls is None:
            conflicts.append((w, "no producer"))
            continue
        if pls - {-1} <= must_excl and -1 not in pls:
            conflicts.append((w, sorted(pls & must_excl)))
    print(f"{ax}: must-exclude polylines={sorted(must_excl)} "
          f"n={len(must_excl)} conflicts={len(conflicts)}")
    for c in conflicts[:8]:
        print("   conflict:", c)
    # where are the excluded polylines geometrically?
    if ax == "y":
        for k in sorted(must_excl):
            seq = polylines[k]
            pts = P[seq]
            print(f"   pl{k}: n={len(seq)} bbox={pts.min(0).round(2)}.."
                  f"{pts.max(0).round(2)} len={sum(np.linalg.norm(np.diff(pts,axis=0),axis=1)):.1f}")

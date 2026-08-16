# P0 round 75: node-level exclusion set = nodes producing any extra value.
# Verify each gold value survives; then dump excluded-node properties:
# mesh valence, edge valence, segment lengths to neighbours, angle.
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

adj = {}
tri_at = {i: 0 for i in range(N)}
for a, b, c in tri:
    for u, v in ((a, b), (b, c), (c, a)):
        adj.setdefault(int(u), set()).add(int(v))
        adj.setdefault(int(v), set()).add(int(u))
    for v in (a, b, c):
        tri_at[int(v)] += 1

def proj_vals(vals, i_ax):
    v = np.sort(np.asarray(vals, float))
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lo+0.1) & (v < hi-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

# per-axis: nodes producing extra values
kill = set()
for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    cand = proj_vals(P[:, i_ax], i_ax)
    extras = [v for v in cand if not np.any(np.abs(g-v) < 0.1)]
    for v in extras:
        for i in range(N):
            if abs(P[i, i_ax]-v) < 1e-3:
                kill.add(i)
print(f"kill set: {len(kill)} nodes")

# feasibility: every gold value has a producer outside kill
bad = 0
for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    for w in g:
        prod = [i for i in range(N) if abs(P[i, i_ax]-w) < 0.1
                and i not in kill]
        if not prod:
            bad += 1
            print(f"  UNCOVERED gold {ax}={w:.3f}")
print(f"uncovered gold values: {bad}")

# resulting projection counts with kill removed
keep = np.array(sorted(set(range(N)) - kill))
for i_ax, ax in enumerate("xyz"):
    cand = proj_vals(P[keep, i_ax], i_ax)
    ex = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
    ms = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
    print(f"{ax}: {len(cand)}/{len(gold[ax])} +{ex}/-{ms}")

# properties of kill vs kept nodes
ens = set(int(i) for i in np.where(em)[0])
def props(i):
    nb = adj.get(i, set())
    enb = nb & ens if i in ens else set()
    d = sorted(np.linalg.norm(P[list(nb)] - P[i], axis=1)) if nb else [0]
    return (int(em[i]), len(nb), len(enb),
            round(float(d[0]), 2), round(float(np.mean(d)), 2),
            tri_at[i])

kill_props = [props(i) for i in sorted(kill)]
keep_sample = [props(i) for i in sorted(set(range(N)) - kill)]
def summarize(name, pr):
    for k, label in ((1, "valence"), (2, "evalence"), (3, "mindist"),
                     (5, "tri_at")):
        vals = [p[k] for p in pr]
        print(f"{name}: {label} min/med/max = "
              f"{min(vals)}/{float(np.median(vals))}/{max(vals)}")
summarize("kill  ", kill_props)
summarize("keep  ", keep_sample)
# valence histogram
for name, pr in (("kill", kill_props), ("keep", keep_sample)):
    from collections import Counter
    print(name, "valence hist:", dict(sorted(Counter(p[1] for p in pr).items())))
    print(name, "evalence hist:", dict(sorted(Counter(p[2] for p in pr).items())))
    print(name, "tri_at hist:", dict(sorted(Counter(p[5] for p in pr).items())))

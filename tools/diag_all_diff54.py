# P0 round 54: attribute golden S lines and extra candidate lines to
# edge vs interior display-mesh nodes.  Extras that come only from
# edge nodes support the ThinOut hypothesis; extras from interior
# nodes need another rule.
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
P = world(np.asarray(part.points)*1000.0)
E = part.edge_mask
assert part.edge_mask is not None
print(f"nodes={len(P)} edge={int(E.sum())} interior={int((~E).sum())}")

# membership: how many triangles share each node
tri = part.triangles
mem = np.zeros(len(P), dtype=int)
for a, b, c in tri:
    for v in (a, b, c):
        mem[v] += 1

def proj_col(mask, i_ax):
    v = P[mask, i_ax]
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lo + 0.1) & (v < hi - 0.1)]   # strictly inside domain
    v = np.sort(v)
    out = []
    for x in v:
        if not out or abs(x - out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(mk["s_lines"][ax], float)
    # keep only in-domain gold (marks include domain B lines with other tags)
    gold = np.asarray([v for v in gold
                       if dom[0][i_ax] + 0.1 < v < dom[1][i_ax] - 0.1])
    ed = proj_col(E, i_ax)
    it = proj_col(~E, i_ax)
    # multiplicity of each extra value (how many nodes project to it)
    allp = P[:, i_ax]
    line = f"{ax}: gold={len(gold)} edgeproj={len(ed)} intproj={len(it)}  "
    for label, gold_v in (("G", gold),):
        n_edge_only = sum(1 for v in gold_v if np.any(np.abs(ed-v) < 0.1)
                          and not np.any(np.abs(it-v) < 0.1))
        n_int_only = sum(1 for v in gold_v if np.any(np.abs(it-v) < 0.1)
                         and not np.any(np.abs(ed-v) < 0.1))
        n_both = sum(1 for v in gold_v if np.any(np.abs(it-v) < 0.1)
                     and np.any(np.abs(ed-v) < 0.1))
        n_neither = sum(1 for v in gold_v
                        if not np.any(np.abs(ed-v) < 0.1)
                        and not np.any(np.abs(it-v) < 0.1))
        line += (f"gold edge-only={n_edge_only} int-only={n_int_only} "
                 f"both={n_both} neither={n_neither}")
    print(line)
    # extras: candidate values (strictly in domain) not matching gold
    cand = np.unique(np.round(proj_col(np.ones(len(P), bool), i_ax), 6))
    extras = [v for v in cand if not np.any(np.abs(gold - v) < 0.1)]
    stat = []
    for v in extras:
        n_all = int(np.sum(np.abs(allp - v) < 1e-3))
        n_e = int(np.sum(np.abs(P[E, i_ax] - v) < 1e-3))
        n_i = n_all - n_e
        # max triangle-membership among projecting edge nodes
        idx = [i for i in range(len(P)) if abs(P[i, i_ax]-v) < 1e-3]
        mmax = max(mem[i] for i in idx) if idx else 0
        stat.append((v, n_e, n_i, mmax))
    print(f"   extras={len(extras)} (val, n_edge, n_int, max_mem):")
    print("   ", [(round(v, 3), ne, ni, mm) for v, ne, ni, mm in stat])
    # same stats for gold values for contrast
    gstat = []
    for v in gold:
        idx = [i for i in range(len(P)) if abs(P[i, i_ax]-v) < 1e-3]
        if not idx:
            continue
        mmax = max(mem[i] for i in idx)
        n_e = sum(1 for i in idx if E[i])
        gstat.append((v, n_e, len(idx)-n_e, mmax))
    print(f"   gold (val, n_edge, n_int, max_mem):")
    print("   ", [(round(v, 3), ne, ni, mm) for v, ne, ni, mm in gstat][:40])

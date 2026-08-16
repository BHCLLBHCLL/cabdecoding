# P0 round 61: is the S-line set the 136/138 projections collapsed by a
# single 1D merge distance?  Sweep dthr with two merge policies
# (greedy-keep-first chain and cluster-mean) per axis.
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
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)

gold = {}
projv = {}
for i_ax, ax in enumerate("xyz"):
    g = np.asarray([v for v in mk["s_lines"][ax]
                    if dom[0][i_ax]+0.1 < v < dom[1][i_ax]-0.1])
    col = np.sort(P[:, i_ax])
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    col = col[(col > lo+0.1) & (col < hi-0.1)]
    out = []
    for x in col:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    gold[ax] = g
    projv[ax] = np.asarray(out)
    print(f"{ax}: proj={len(out)} gold={len(g)}")

def chain_merge(vals, d):
    out = [vals[0]]
    for v in vals[1:]:
        if v - out[-1] > d:
            out.append(v)
    return np.asarray(out)

def cluster_merge(vals, d):
    groups = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= d:
            groups[-1].append(v)
        else:
            groups.append([v])
    return np.asarray([float(np.mean(g)) for g in groups])

for d in (0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6, 0.7, 0.8, 1.0):
    line = f"dthr={d:<4} "
    for policy, fn in (("chain", chain_merge), ("mean", cluster_merge)):
        for ax in "xyz":
            m = fn(projv[ax].tolist(), d)
            line += (f"{policy[0]}:{ax}{len(m)}"
                     f"(g{len(gold[ax])}) ")
    print(line)

# check nearest-neighbour gaps inside gold per axis
for ax in "xyz":
    g = np.sort(gold[ax])
    gaps = np.diff(g)
    print(f"{ax} gold gaps: min={gaps.min():.3f} p10={np.percentile(gaps,10):.3f} "
          f"med={np.median(gaps):.3f}; pairs<0.1: {(gaps<0.1).sum()}, "
          f"<0.2: {(gaps<0.2).sum()}, <0.5: {(gaps<0.5).sum()}")

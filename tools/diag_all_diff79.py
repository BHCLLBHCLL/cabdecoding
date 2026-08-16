# P0 round 79: variants to supply the missing y=47.5 without extras.
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
ends = set()
for seq in polylines:
    ends.add(seq[0]); ends.add(seq[-1])
corners = {u for u in ends if len(eadj.get(u, ())) != 2}
bbox_pts = np.vstack([P.min(0), P.max(0)])

def evaluate(name, extra_pts):
    print(f"--- {name} ---")
    ok = True
    for i_ax, ax in enumerate("xyz"):
        vals = list(P[inside, i_ax])
        if len(extra_pts):
            vals += list(extra_pts[:, i_ax])
        v = np.sort(np.asarray(vals, float))
        lox, hix = dom[0][i_ax], dom[1][i_ax]
        v = v[(v > lox+0.1) & (v < hix-0.1)]
        out = []
        for x in v:
            if not out or abs(x-out[-1]) > 1e-3:
                out.append(float(x))
        m = [out[0]] if out else []
        for x in out[1:]:
            if x - m[-1] > 0.1:
                m.append(x)
        m = np.asarray(m)
        g = gold[ax]
        ex = sum(1 for v2 in m if not np.any(np.abs(g-v2) < 0.1))
        ms = sum(1 for v2 in g if not np.any(np.abs(m-v2) < 0.1))
        if ex or ms or len(m) != len(g):
            ok = False
        print(f"{ax}: merged={len(m)} gold={len(g)} extras={ex} miss={ms}")
        if ex:
            print("   extras:", [round(x,3) for x in m
                                 if not np.any(np.abs(g-x) < 0.1)][:12])
        if ms:
            print("   miss:", [round(x,3) for x in g
                               if not np.any(np.abs(m-x) < 0.1)][:12])
    print("  ==>", "EXACT MATCH" if ok else "no")

evaluate("(a) clip + part-bbox", bbox_pts)
evaluate("(b) clip + endpoints", P[sorted(ends)])
evaluate("(c) clip + corners", P[sorted(corners)])
evaluate("(d) clip-only", np.zeros((0, 3)))

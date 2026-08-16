# P0 round 71: candidate node subsets vs gold:
#   (a) interior U polyline endpoints (B-rep corners)
#   (b) nodes with edge-degree >= 3 (corners) U interior
#   (c) coarser facettings (tol factor 2,4,8,16) all-node projections
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
ends = set()
for seq in polylines:
    ends.add(seq[0]); ends.add(seq[-1])
deg3 = {u for u, nb in eadj.items() if len(nb) >= 3}
interior = set(range(len(P))) - ens

def proj_vals(vals, i_ax):
    v = np.sort(np.asarray(vals, float))
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = v[(v > lo+0.1) & (v < hi-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

def report(name, nodes):
    idx = np.array(sorted(nodes))
    line = f"{name:<28}"
    ok = True
    for i_ax, ax in enumerate("xyz"):
        cand = proj_vals(P[idx, i_ax], i_ax)
        ex = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
        ms = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
        line += f"{ax}:{len(cand)}/{len(gold[ax])} +{ex}/-{ms}  "
        if ex or ms:
            ok = False
    print(line, "MATCH" if ok else "")

report("all", range(len(P)))
report("interior U ends", interior | ends)
report("interior U deg3 U ends", interior | deg3 | ends)
report("ends only", ends)
report("deg3 only", deg3)

# coarser facettings: scale the six recipe tolerances by f
mod = ps_facet2_nodes
from ctypes import byref, memset, sizeof, c_int, c_void_p, POINTER
D = float(np.linalg.norm(P.max(0) - P.min(0)))   # mm diagonal
for f in (0.25, 0.5, 2.0, 4.0, 8.0):
    kw = mod.stpre_recipe(D, angle_deg=mod.STPRE_RECIPE["angle_deg"],
                          ccm=mod.STPRE_RECIPE["ccm"]*f,
                          mfw=mod.STPRE_RECIPE["mfw"]*f,
                          cct=mod.STPRE_RECIPE["cct"]*f,
                          spt=mod.STPRE_RECIPE["spt"]*f)
    opts = mod._Facet2OptionsV5()
    memset(byref(opts), 0, sizeof(opts))
    opts.control.o_t_version = 5
    opts.control.max_facet_sides = 3
    for k, v in kw.items():
        setattr(opts.control, "is_" + k, 1)
        setattr(opts.control, k, float(v))
    opts.data_point_idx = 1
    opts.point_vec = 1
    res = mod._Facet2Result()
    pk = sess.pk
    pk.PK_TOPOL_facet_2.restype = c_int
    pk.PK_TOPOL_facet_2.argtypes = [c_int, POINTER(c_int), c_void_p,
                                    POINTER(mod._Facet2OptionsV5),
                                    POINTER(mod._Facet2Result)]
    if pk.PK_TOPOL_facet_2(1, (c_int*1)(int(imp)), None,
                           byref(opts), byref(res)) != 0:
        print(f"facet f={f} FAILED")
        continue
    import struct
    from ctypes import string_at
    tabs = mod.cast(res.tables,
                    mod.POINTER(mod._FacetTable * res.number_of_tables)).contents
    pts = None
    for t in tabs:
        if int(t.fctab) == mod.FCTAB_POINT_VEC:
            ptr, length = struct.unpack_from("<Qi", string_at(t.ptr, 16))
            pts = np.frombuffer(string_at(ptr, length*24),
                                dtype=np.float64).reshape(-1, 3)
    Pf = world(pts * 1000.0)
    line = f"facet x{f:<5} n={len(Pf):<5}"
    for i_ax, ax in enumerate("xyz"):
        cand = proj_vals(Pf[:, i_ax], i_ax)
        ex = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
        ms = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
        line += f"{ax}:{len(cand)}/{len(gold[ax])} +{ex}/-{ms}  "
    print(line)

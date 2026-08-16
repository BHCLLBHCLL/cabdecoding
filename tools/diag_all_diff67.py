# P0 round 67: proper per-B-rep-edge polyline reconstruction via fin_fin
# rings restricted to each edge's fin set; then test recipe
#   S-lines = interior-node projections  U  ThinOut(edge polyline, eps)
# over an eps sweep.
import json, struct, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk
from ctypes import string_at, byref, memset, sizeof, c_int, c_void_p, POINTER

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

mod = ps_facet2_nodes
opts = mod._Facet2OptionsV5()
memset(byref(opts), 0, sizeof(opts))
opts.control.o_t_version = 5
opts.control.max_facet_sides = 3
P0 = np.asarray(sess.facet_body_stpre(imp).points) * 1000.0
D = float((P0.max(0) - P0.min(0)).max())
kw = mod.stpre_recipe(D, angle_deg=mod.STPRE_RECIPE["angle_deg"],
                      ccm=mod.STPRE_RECIPE["ccm"], mfw=mod.STPRE_RECIPE["mfw"],
                      cct=mod.STPRE_RECIPE["cct"], spt=mod.STPRE_RECIPE["spt"])
for k, v in kw.items():
    setattr(opts.control, "is_" + k, 1)
    setattr(opts.control, k, float(v))
opts.facet_fin = 1
opts.fin_fin = 1
opts.fin_data = 1
opts.data_point_idx = 1
opts.point_vec = 1
opts.fin_edge = 1
res = mod._Facet2Result()
pk = sess.pk
pk.PK_TOPOL_facet_2.restype = c_int
pk.PK_TOPOL_facet_2.argtypes = [c_int, POINTER(c_int), c_void_p,
                                POINTER(mod._Facet2OptionsV5),
                                POINTER(mod._Facet2Result)]
assert pk.PK_TOPOL_facet_2(1, (c_int*1)(int(imp)), None,
                           byref(opts), byref(res)) == 0
tabs = mod.cast(res.tables,
                mod.POINTER(mod._FacetTable * res.number_of_tables)).contents
data = {}
for t in tabs:
    raw16 = string_at(t.ptr, 16)
    ptr, length = struct.unpack_from("<Qi", raw16)
    data[int(t.fctab)] = (ptr, length)

def pairs(ptr, count):
    raw = string_at(ptr, count*8)
    return [(struct.unpack_from("<i", raw, i*8)[0],
             struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(count)]

def ints(ptr, count):
    if count <= 0 or not ptr:
        return []
    return list(struct.unpack_from("<%di" % count, string_at(ptr, count*4)))

fd_ptr, fd_len = data[mod.FCTAB_FIN_DATA]
dp_ptr, dp_len = data[mod.FCTAB_DATA_POINT_IDX]
fc_ptr, fc_len = data[0x57C2]
ff_ptr, ff_len = data[mod.FCTAB_FIN_FIN]
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)
fin2edge = dict(pairs(fc_ptr, fc_len))
fin2next = dict(pairs(ff_ptr, ff_len))
n_fins = len(fin_data)
print(f"fins={n_fins} fin2edge={len(fin2edge)} fin2next={len(fin2next)}")

# per-edge ordered polylines: walk fin2next chains within the edge's fins
edge_fins = {}
for f, e in fin2edge.items():
    if e >= 0:
        edge_fins.setdefault(e, []).append(f)

def fin_points(f):
    lo = fin_data[f]
    hi = fin_data[f+1] if f+1 < n_fins else len(point_of_data)
    if f == max(fin2edge, default=-1):
        hi = len(point_of_data)
    return point_of_data[lo:hi]

polylines = []
for e, fins in edge_fins.items():
    fs = set(fins)
    nxt = {f: fin2next[f] for f in fins if fin2next.get(f) in fs}
    # chain starts: fins not pointed to by another fin in this edge
    pointed = set(nxt.values())
    starts = [f for f in fins if f not in pointed]
    if not starts:
        starts = [fins[0]]          # pure ring
    seen_fin = set()
    for s in starts:
        seq = []
        f = s
        while f is not None and f not in seen_fin and f in fs:
            seen_fin.add(f)
            seq.extend(fin_points(f))
            f = nxt.get(f)
            if f == s:
                break               # ring closed
        if len(seq) >= 2:
            polylines.append(seq)

# dedupe consecutive repeated points
pl_pts = []
for seq in polylines:
    out = []
    for p in seq:
        if not out or p != out[-1]:
            out.append(p)
    pl_pts.append(out)
lens = [len(p) for p in pl_pts]
print(f"polylines={len(pl_pts)} len min/med/max="
      f"{min(lens)}/{int(np.median(lens))}/{max(lens)} "
      f"total pts={sum(lens)}")

part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
on_pl = set()
for seq in pl_pts:
    on_pl.update(seq)
interior = np.array([i for i in range(len(P)) if i not in on_pl])
print(f"nodes={len(P)} on-edge-polyline={len(on_pl)} interior={len(interior)}")

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

def thinout(seq_pts, eps):
    keep = [seq_pts[0]]
    for q in seq_pts[1:]:
        if np.linalg.norm(q - keep[-1]) >= eps:
            keep.append(q)
    return keep

for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    c_int = proj_vals(P[interior, i_ax], i_ax)
    ex = [v for v in c_int if not np.any(np.abs(g-v) < 0.1)]
    ms = [v for v in g if not np.any(np.abs(c_int-v) < 0.1)]
    print(f"{ax}: interior-only cand={len(c_int)} gold={len(g)} "
          f"extras={len(ex)} miss={len(ms)}")

print()
for tol in (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05):
    eps = max(1e-8, tol) * D
    kept_idx = set(interior.tolist())
    for seq in pl_pts:
        pts = [P[i] for i in seq]
        for q in thinout(pts, eps):
            pass
    # collect kept point indices: thinout returns coords; redo with idx
    kept_idx = set(interior.tolist())
    for seq in pl_pts:
        keep = [seq[0]]
        for i in seq[1:]:
            if np.linalg.norm(P[i] - P[keep[-1]]) >= eps:
                keep.append(i)
        kept_idx.update(keep)
    idx = np.array(sorted(kept_idx))
    line = f"tol={tol:<6} eps={eps:6.3f} "
    for i_ax, ax in enumerate("xyz"):
        cand = proj_vals(P[idx, i_ax], i_ax)
        ex = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
        ms = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
        line += f"{ax}:{len(cand)}/{len(gold[ax])} +{ex}/-{ms}  "
    print(line)

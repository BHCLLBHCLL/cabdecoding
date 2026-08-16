# P0 round 55: rebuild per-model-edge polylines from the facet fin tables
# (facet_fin ring order + fin_data + fin_edge), apply greedy ThinOut
# (eps = max(1e-8, tol) * bbox_max_extent) and compare the surviving
# node projections with golden S lines.
import json, struct, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk
from ctypes import string_at

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_0"]
dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))

# ---- run PK_TOPOL_facet_2 with fin tables and decode raw fin info ----
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")

part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
D = float((P.max(0) - P.min(0)).max())

# re-decode the tables directly (mirror of _decode_result) to get the
# fin->edge mapping with ring order
raw = part  # need tables again -> redo the call once and read tables
# The private decode path is not exposed; rebuild using the same ctypes
# structures through a tiny re-run:
mod = ps_facet2_nodes
res_ptr = mod._Facet2Result()
from ctypes import byref, memset, sizeof, c_int, c_void_p, POINTER
opts = mod._Facet2OptionsV5()
memset(byref(opts), 0, sizeof(opts))
opts.control.o_t_version = 5
opts.control.max_facet_sides = 3
kw = mod.stpre_recipe(D, angle_deg=mod.STPRE_RECIPE["angle_deg"],
                      ccm=mod.STPRE_RECIPE["ccm"], mfw=mod.STPRE_RECIPE["mfw"],
                      cct=mod.STPRE_RECIPE["cct"], spt=mod.STPRE_RECIPE["spt"])
for k, v in kw.items():
    setattr(opts.control, "is_" + k, 1)
    setattr(opts.control, k, float(v))
opts.facet_fin = 1
opts.fin_data = 1
opts.data_point_idx = 1
opts.point_vec = 1
opts.fin_edge = 1
pk = sess.pk
pk.PK_TOPOL_facet_2.restype = c_int
pk.PK_TOPOL_facet_2.argtypes = [c_int, POINTER(c_int), c_void_p,
                                POINTER(mod._Facet2OptionsV5),
                                POINTER(mod._Facet2Result)]
rc = pk.PK_TOPOL_facet_2(1, (c_int*1)(int(imp)), None, byref(opts),
                         byref(res_ptr))
assert rc == 0, rc
# walk tables
n_tables = res_ptr.number_of_tables
tabs = mod.cast(res_ptr.tables,
                mod.POINTER(mod._FacetTable * n_tables)).contents
data = {}
for t in tabs:
    raw16 = string_at(t.ptr, 16)
    ptr, length = struct.unpack_from("<Qi", raw16)
    data[int(t.fctab)] = (ptr, length)

def pairs(ptr, count):
    raw = string_at(ptr, count * 8)
    return [(struct.unpack_from("<i", raw, i*8)[0],
             struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(count)]

def ints(ptr, count):
    if count <= 0 or not ptr:
        return []
    raw = string_at(ptr, count * 4)
    return list(struct.unpack_from("<%di" % count, raw))

FF, FD, DPI, PV, FE = (mod.FCTAB_FACET_FIN, mod.FCTAB_FIN_DATA,
                       mod.FCTAB_DATA_POINT_IDX, mod.FCTAB_POINT_VEC,
                       getattr(mod, "FCTAB_FACET_FACE"))
ff_ptr, ff_len = data[FF]
fd_ptr, fd_len = data[FD]
dp_ptr, dp_len = data[DPI]
fe_ptr, fe_len = data[FE]
fin_of_facet = {}
for facet, fin in pairs(ff_ptr, ff_len):
    if fin >= 0 and facet >= 0:
        fin_of_facet.setdefault(facet, []).append(fin)
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)

def node_of_fin(f):
    di = fin_data[f]
    return point_of_data[di]

# build fin->edge map once, then directed segments (tail -> head) per edge
fin2edge = dict(pairs(fe_ptr, fe_len))
seg_by_edge = {}
for facet, fins in fin_of_facet.items():
    if len(fins) < 3:
        continue
    ns = [node_of_fin(f) for f in fins[:3]]
    for i in range(3):
        fin = fins[i]
        ed = fin2edge.get(fin)
        if ed is None or ed <= 0:
            continue
        u, v = ns[i], ns[(i + 1) % 3]
        seg_by_edge.setdefault(ed, set()).add((u, v))

print(f"model edges: {len(seg_by_edge)}, segs total "
      f"{sum(len(s) for s in seg_by_edge.values())}")

# chain segments into node sequences (undirected: twin fins from the
# two adjacent faces give each segment twice, in both directions)
chains = []
for ed, segs in seg_by_edge.items():
    adj_e = {}
    for u, v in {(min(u, v), max(u, v)) for u, v in segs}:
        adj_e.setdefault(u, set()).add(v)
        adj_e.setdefault(v, set()).add(u)
    visited = set()
    starts = sorted(n for n in adj_e if len(adj_e[n]) == 1) \
        + sorted(n for n in adj_e if len(adj_e[n]) > 1)
    for s in starts:
        if s in visited:
            continue
        seq = [s]
        visited.add(s)
        cur = s
        prev = -1
        while True:
            nxt = [x for x in adj_e.get(cur, ()) if x != prev]
            # on closed loops allow returning to start only at the end
            nxt2 = [x for x in nxt if x != s or x == seq[0]
                    and len(seq) > 2]
            pick = None
            for x in nxt:
                if x in visited and not (x == seq[0] and len(seq) > 2):
                    continue
                pick = x
                break
            if pick is None:
                break
            prev, cur = cur, pick
            visited.add(cur)
            seq.append(cur)
        chains.append(seq)
lens = [len(c) for c in chains]
print(f"chains={len(chains)} len min/med/max="
      f"{min(lens)}/{int(np.median(lens))}/{max(lens)}")

interior = P[~part.edge_mask]

def thinout(seq_pts, eps):
    keep = [seq_pts[0]]
    for q in seq_pts[1:]:
        if np.linalg.norm(q - keep[-1]) >= eps:
            keep.append(q)
    return keep

def dedupe(vals, i_ax, tol=1e-3):
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = np.sort(np.asarray(vals, float))
    v = v[(v > lo + 0.1) & (v < hi - 0.1)]
    out = []
    for x in v:
        if not out or abs(x - out[-1]) > tol:
            out.append(float(x))
    return np.asarray(out)

gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i] + 0.1 < v < dom[1][i] - 0.1])
        for i, ax in enumerate("xyz")}

for tol in (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05):
    eps = max(1e-8, tol) * D
    kept_f = [p for c in chains for p in thinout([P[i] for i in c], eps)]
    kept_r = [p for c in chains for p in thinout([P[i] for i in c][::-1], eps)]
    for label, kept in (("fwd", kept_f), ("rev", kept_r)):
        kept = np.asarray(kept)
        line = f"tol={tol:<6} eps={eps:6.3f} {label}: "
        for i_ax, ax in enumerate("xyz"):
            cand = dedupe(kept[:, i_ax], i_ax)
            n_extra = sum(1 for v in cand
                          if not np.any(np.abs(gold[ax] - v) < 0.1))
            n_miss = sum(1 for v in gold[ax]
                         if not np.any(np.abs(cand - v) < 0.1))
            line += f"{ax}:{len(cand)}/{len(gold[ax])} +{n_extra}/-{n_miss} "
        print(line)

# P0 round 60: rebuild model-edge polylines WITHOUT fin ring order:
#   node->edge from fin2edge(fin->edge) + fin_data(fin->start node);
#   adjacency from triangle geometry restricted to same-edge nodes.
# Then greedy ThinOut per polyline (both directions, tol sweep) and
# compare surviving projections with golden S lines.
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
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)
fin2edge = dict(pairs(fc_ptr, fc_len))

edge_nodes = {}
for fin, ed in fin2edge.items():
    if 0 <= fin < len(fin_data):
        pi = point_of_data[fin_data[fin]]
        if 0 <= pi:
            edge_nodes.setdefault(ed, set()).add(pi)
print(f"edges={len(edge_nodes)} tagged nodes="
      f"{len(set().union(*edge_nodes.values()))}")

part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
tri = part.triangles
gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i]+0.1 < v < dom[1][i]-0.1])
        for i, ax in enumerate("xyz")}

# geometry adjacency (mesh edges)
adj_all = {}
for a, b, c in tri:
    for u, v in ((a, b), (b, c), (c, a)):
        adj_all.setdefault(int(u), set()).add(int(v))
        adj_all.setdefault(int(v), set()).add(int(u))

# per-edge chains: connectivity within edge node sets
chains = []
for ed, nodes in edge_nodes.items():
    ns = set(nodes)
    eadj = {u: (adj_all.get(u, set()) & ns) for u in ns}
    # degree stats
    visited = set()
    for s in sorted(ns):
        if s in visited:
            continue
        # walk maximal path (allow loop closure)
        seq = [s]
        visited.add(s)
        cur, prev = s, -1
        while True:
            nxt = [x for x in eadj[cur] if x != prev]
            pick = None
            for x in nxt:
                if x not in visited or (x == s and len(seq) > 2):
                    pick = x
                    break
            if pick is None:
                break
            if pick == s:
                seq.append(s)
                break
            prev, cur = cur, pick
            visited.add(cur)
            seq.append(cur)
        chains.append(seq)
lens = [len(c) for c in chains]
deg_ok = sum(1 for ed, nodes in edge_nodes.items()
             for n in nodes if len(adj_all.get(n, ()) & nodes) <= 2)
print(f"chains={len(chains)} len min/med/max={min(lens)}/"
      f"{int(np.median(lens))}/{max(lens)} deg<=2 nodes={deg_ok}")

def thinout(seq_pts, eps):
    keep = [seq_pts[0]]
    for q in seq_pts[1:]:
        if np.linalg.norm(q - keep[-1]) >= eps:
            keep.append(q)
    return keep

def dedupe(vals, i_ax, tol=1e-3):
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    v = np.sort(np.asarray(vals, float))
    v = v[(v > lo+0.1) & (v < hi-0.1)]
    out = []
    for x in v:
        if not out or abs(x-out[-1]) > tol:
            out.append(float(x))
    return np.asarray(out)

for tol in (0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02):
    eps = max(1e-8, tol) * D
    out_lines = []
    for direction in ("fwd", "rev"):
        kept = []
        for c in chains:
            pts = [P[i] for i in c]
            if direction == "rev":
                pts = pts[::-1]
            kept.extend(thinout(pts, eps))
        kept = np.asarray(kept)
        line = f"tol={tol:<7} eps={eps:6.3f} {direction}: "
        for i_ax, ax in enumerate("xyz"):
            cand = dedupe(kept[:, i_ax], i_ax)
            n_extra = sum(1 for v in cand
                          if not np.any(np.abs(gold[ax]-v) < 0.1))
            n_miss = sum(1 for v in gold[ax]
                         if not np.any(np.abs(cand-v) < 0.1))
            line += f"{ax}:{len(cand)}/{len(gold[ax])} +{n_extra}/-{n_miss} "
        out_lines.append(line)
    print("\n".join(out_lines))

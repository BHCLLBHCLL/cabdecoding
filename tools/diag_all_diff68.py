# P0 round 68: single consistent mesh: points from point_vec table,
# triangles from facet_fin+fin_data+data_point_idx, edges from fin_edge
# (token 0x57C2).  Then order each edge's nodes by walking mesh adjacency
# restricted to the edge, and test recipe
#   S-lines = interior-node projections U ThinOut(edge polyline, eps).
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

ff_ptr, ff_len = data[mod.FCTAB_FACET_FIN]
fd_ptr, fd_len = data[mod.FCTAB_FIN_DATA]
dp_ptr, dp_len = data[mod.FCTAB_DATA_POINT_IDX]
pv_ptr, pv_len = data[mod.FCTAB_POINT_VEC]
fe_ptr, fe_len = data[0x57C2]
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)
fin2edge = dict(pairs(fe_ptr, fe_len))
facet_fins = {}
for facet, fin in pairs(ff_ptr, ff_len):
    facet_fins.setdefault(facet, []).append(fin)

# point coordinates: 3 doubles per point (metres); world() eats mm
Pm = np.frombuffer(string_at(pv_ptr, pv_len*24), dtype=np.float64).reshape(-1, 3)
P = world(Pm * 1000.0)
print(f"points={len(P)} fins={len(fin_data)} facets={len(facet_fins)}")

# node id per fin (its start data point)
fin_node = {f: point_of_data[fin_data[f]] for f in range(len(fin_data))
            if 0 <= fin_data[f] < len(point_of_data)}

# triangles as node triples
tris = []
for facet, fins in facet_fins.items():
    if len(fins) == 3:
        t = tuple(fin_node.get(f, -1) for f in fins)
        if -1 not in t:
            tris.append(t)
tris = np.asarray(tris, int)
print(f"triangles={len(tris)}")

# edge node sets from fin_edge
edge_nodes = {}
for fin, ed in fin2edge.items():
    if ed >= 0 and fin in fin_node:
        edge_nodes.setdefault(ed, set()).add(fin_node[fin])
on_edge = set().union(*edge_nodes.values())
interior = [i for i in range(len(P)) if i not in on_edge]
print(f"on-edge={len(on_edge)} interior={len(interior)} edges={len(edge_nodes)}")

# adjacency
adj = {}
for a, b, c in tris:
    for u, v in ((a, b), (b, c), (c, a)):
        adj.setdefault(int(u), set()).add(int(v))
        adj.setdefault(int(v), set()).add(int(u))

# per-edge polylines: walk adjacency restricted to edge node set
polylines = []
for ed, ns in edge_nodes.items():
    ns = set(ns)
    eadj = {u: (adj.get(u, set()) & ns) for u in ns}
    visited = set()
    for s in ns:
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
lens = [len(p) for p in polylines]
print(f"polylines={len(polylines)} len min/med/max="
      f"{min(lens)}/{int(np.median(lens))}/{max(lens)} pts={sum(lens)}")

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

for i_ax, ax in enumerate("xyz"):
    g = gold[ax]
    c = proj_vals(P[interior, i_ax], i_ax)
    ex = [v for v in c if not np.any(np.abs(g-v) < 0.1)]
    ms = [v for v in g if not np.any(np.abs(c-v) < 0.1)]
    print(f"{ax}: interior cand={len(c)} gold={len(g)} "
          f"extras={len(ex)} miss={len(ms)}")

print()
for tol in (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05):
    eps = max(1e-8, tol) * D
    kept = set(interior)
    for seq in polylines:
        keep = [seq[0]]
        for i in seq[1:]:
            if np.linalg.norm(P[i] - P[keep[-1]]) >= eps:
                keep.append(i)
        kept.update(keep)
    idx = np.array(sorted(kept))
    line = f"tol={tol:<6} eps={eps:6.3f} "
    for i_ax, ax in enumerate("xyz"):
        cand = proj_vals(P[idx, i_ax], i_ax)
        ex = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
        ms = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
        line += f"{ax}:{len(cand)}/{len(gold[ax])} +{ex}/-{ms}  "
    print(line)

# P0 round 56: for z-axis symmetric gold/extra pairs, trace each source
# node to its model-edge chain (id, length, position, 3D coords) to
# infer why one side survives and the symmetric side is dropped.
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
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
mod = ps_facet2_nodes

# redo facet_2 call to reach fin tables
opts = mod._Facet2OptionsV5()
memset(byref(opts), 0, sizeof(opts))
opts.control.o_t_version = 5
opts.control.max_facet_sides = 3
D = float((P.max(0) - P.min(0)).max())
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
    raw = string_at(ptr, count * 8)
    return [(struct.unpack_from("<i", raw, i*8)[0],
             struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(count)]

def ints(ptr, count):
    if count <= 0 or not ptr:
        return []
    return list(struct.unpack_from("<%di" % count, string_at(ptr, count*4)))

ff_ptr, ff_len = data[mod.FCTAB_FACET_FIN]
fd_ptr, fd_len = data[mod.FCTAB_FIN_DATA]
dp_ptr, dp_len = data[mod.FCTAB_DATA_POINT_IDX]
fe_ptr, fe_len = data[mod.FCTAB_FACET_FACE]
fin_of_facet = {}
for facet, fin in pairs(ff_ptr, ff_len):
    if fin >= 0 and facet >= 0:
        fin_of_facet.setdefault(facet, []).append(fin)
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)
fin2edge = dict(pairs(fe_ptr, fe_len))

seg_by_edge = {}
for facet, fins in fin_of_facet.items():
    if len(fins) < 3:
        continue
    ns = [point_of_data[fin_data[f]] for f in fins[:3]]
    for i in range(3):
        ed = fin2edge.get(fins[i])
        if ed is None or ed <= 0:
            continue
        u, v = ns[i], ns[(i+1) % 3]
        seg_by_edge.setdefault(ed, set()).add((min(u, v), max(u, v)))

# node -> (edge_tag, chain_id, pos, chain_len)
node_info = {}
for cid, (ed, segs) in enumerate(sorted(seg_by_edge.items())):
    adj_e = {}
    for u, v in segs:
        adj_e.setdefault(u, set()).add(v)
        adj_e.setdefault(v, set()).add(u)
    # longest path via DFS from endpoints (approx chain)
    best = []
    seen_global = set()
    starts = sorted([n for n in adj_e if len(adj_e[n]) == 1]) + \
        sorted([n for n in adj_e if len(adj_e[n]) > 1])
    for s in starts:
        if s in seen_global:
            continue
        stack = [(s, [s])]
        while stack:
            cur, path = stack.pop()
            if len(path) > len(best):
                best = path
            for x in adj_e.get(cur, ()):
                if x in path:
                    continue
                stack.append((x, path + [x]))
        for n in best:
            seen_global.add(n)
        for pos, n in enumerate(best):
            node_info[n] = (ed, cid, pos, len(best))
        best = []

gold_z = np.asarray([v for v in mk["s_lines"]["z"]
                     if dom[0][2] + 0.1 < v < dom[1][2] - 0.1])
cand_z = np.unique(np.round(P[part.edge_mask][:, 2], 6))
extras = [v for v in cand_z
          if dom[0][2]+0.1 < v < dom[1][2]-0.1
          and not np.any(np.abs(gold_z - v) < 0.1)]

def node_rows(val):
    idx = [i for i in range(len(P))
           if part.edge_mask[i] and abs(P[i, 2]-val) < 1e-3]
    return idx

print("z EXTRAS detail (val, node, xyz, edge_tag, chain_id, pos, len):")
for v in extras[:12]:
    rows = []
    for i in node_rows(v):
        ed, cid, pos, ln = node_info.get(i, (-1, -1, -1, -1))
        rows.append((int(i), tuple(P[i].round(2)), ed, cid, pos, ln))
    print(f" {v:9.3f}: {rows}")

print("\nz GOLDS detail:")
for v in [x for x in gold_z if x > 0][:14]:
    rows = []
    for i in node_rows(v):
        ed, cid, pos, ln = node_info.get(i, (-1, -1, -1, -1))
        rows.append((int(i), tuple(P[i].round(2)), ed, cid, pos, ln))
    print(f" {v:9.3f}: {rows}")

# symmetry bookkeeping: for each |v| bucket, is +v gold&-v extra or both gold?
pos = {round(v, 3) for v in gold_z if v > 0}
neg = {round(v, 3) for v in gold_z if v < 0}
ex = {round(v, 3) for v in extras}
print("\nsymmetry map (|v|: status):")
for a in sorted({abs(v) for v in gold_z} | {abs(v) for v in extras}):
    sp = "+G" if round(a, 3) in pos else ("+E" if round(a, 3) in ex else "+-")
    sn = "-G" if round(-a, 3) in neg else ("-E" if round(-a, 3) in ex else "--")
    print(f"  {a:8.3f}: {sp} {sn}")

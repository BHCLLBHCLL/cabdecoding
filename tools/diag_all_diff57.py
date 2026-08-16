# P0 round 57: correct fin->FACE semantics (token 0x57C2).  A mesh
# segment (u,v) is a model-edge segment iff its two adjacent fins lie
# on different faces.  Build model-edge polylines from those segments,
# greedy ThinOut them and compare projections with golden S lines.
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
opts.fin_edge = 1          # asks for token 0x57C2 (fin->face)
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
fc_ptr, fc_len = data[0x57C2]
fin_of_facet = {}
for facet, fin in pairs(ff_ptr, ff_len):
    if fin >= 0 and facet >= 0:
        fin_of_facet.setdefault(facet, []).append(fin)
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)
fin2face = dict(pairs(fc_ptr, fc_len))
print(f"fins mapped to faces: {len(fin2face)} of {len(fin_data)}")

# segment (u,v) -> set of faces
seg_faces = {}
for facet, fins in fin_of_facet.items():
    if len(fins) < 3:
        continue
    ns = [point_of_data[fin_data[f]] for f in fins[:3]]
    for i in range(3):
        f = fins[i]
        fc = fin2face.get(f)
        if fc is None:
            continue
        u, v = ns[i], ns[(i+1) % 3]
        key = (min(u, v), max(u, v))
        seg_faces.setdefault(key, set()).add(fc)

model_segs = [k for k, fc in seg_faces.items() if len(fc) >= 2]
print(f"segs total={len(seg_faces)} model-edge segs={len(model_segs)}")
medge_nodes = {n for k in model_segs for n in k}
print(f"model-edge nodes={len(medge_nodes)} of {len(point_of_data) and len(set(point_of_data))}")

part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i] + 0.1 < v < dom[1][i] - 0.1])
        for i, ax in enumerate("xyz")}

# raw model-edge-node projections vs gold
for i_ax, ax in enumerate("xyz"):
    col = P[sorted(medge_nodes), i_ax]
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    col = np.sort(col[(col > lo+0.1) & (col < hi-0.1)])
    out = []
    for x in col:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    cand = np.asarray(out)
    n_extra = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
    n_miss = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
    print(f"{ax}: medge-proj={len(cand)} gold={len(gold[ax])} "
          f"+{n_extra}/-{n_miss}")

# chains of model-edge segments
adj = {}
for u, v in model_segs:
    adj.setdefault(u, set()).add(v)
    adj.setdefault(v, set()).add(u)
visited = set()
chains = []
starts = sorted([n for n in adj if len(adj[n]) == 1]) + sorted(adj)
for s in starts:
    if s in visited:
        continue
    seq = [s]
    visited.add(s)
    cur = s
    while True:
        nxt = [x for x in adj.get(cur, ()) if x not in visited]
        if not nxt:
            break
        cur = nxt[0]
        visited.add(cur)
        seq.append(cur)
    chains.append(seq)
lens = [len(c) for c in chains]
print(f"chains={len(chains)} len min/med/max={min(lens)}/"
      f"{int(np.median(lens))}/{max(lens)}")

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

for tol in (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05):
    eps = max(1e-8, tol) * D
    kept_f = np.asarray([p for c in chains
                         for p in thinout([P[i] for i in c], eps)])
    line = f"tol={tol:<6} eps={eps:6.3f} fwd: "
    for i_ax, ax in enumerate("xyz"):
        cand = dedupe(kept_f[:, i_ax], i_ax)
        n_extra = sum(1 for v in cand if not np.any(np.abs(gold[ax]-v) < 0.1))
        n_miss = sum(1 for v in gold[ax] if not np.any(np.abs(cand-v) < 0.1))
        line += f"{ax}:{len(cand)}/{len(gold[ax])} +{n_extra}/-{n_miss} "
    print(line)

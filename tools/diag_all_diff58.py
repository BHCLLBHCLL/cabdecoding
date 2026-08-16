# P0 round 58: full attribution matrix per axis:
#   A = all-node projections, B = model-edge-node projections
#   gold vs A/B: hits, extras, misses; for misses list source nodes
# (interior vs edge, triangle membership).
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
fc_ptr, fc_len = data[0x57C2]
fin_of_facet = {}
for facet, fin in pairs(ff_ptr, ff_len):
    if fin >= 0 and facet >= 0:
        fin_of_facet.setdefault(facet, []).append(fin)
fin_data = ints(fd_ptr, fd_len)
point_of_data = ints(dp_ptr, dp_len)
fin2edge = dict(pairs(fc_ptr, fc_len))

edge_nodes = {}
for fin, ed in fin2edge.items():
    if 0 <= fin < len(fin_data):
        pi = point_of_data[fin_data[fin]]
        if 0 <= pi:
            edge_nodes.setdefault(ed, set()).add(pi)
medge = set().union(*edge_nodes.values()) if edge_nodes else set()

part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
tri = part.triangles
mem = np.zeros(len(P), int)
for a, b, c in tri:
    for v in (a, b, c):
        mem[v] += 1

is_me = np.zeros(len(P), bool)
is_me[sorted(medge)] = True
print(f"nodes={len(P)} model-edge={int(is_me.sum())} interior={int((~is_me).sum())}")

gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i]+0.1 < v < dom[1][i]-0.1])
        for i, ax in enumerate("xyz")}

def proj(mask, i_ax):
    col = np.sort(P[mask, i_ax])
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    col = col[(col > lo+0.1) & (col < hi-0.1)]
    out = []
    for x in col:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

for i_ax, ax in enumerate("xyz"):
    A = proj(np.ones(len(P), bool), i_ax)
    B = proj(is_me, i_ax)
    G = gold[ax]
    print(f"\n{ax}: |A|={len(A)} |B|={len(B)} |G|={len(G)}")
    for label, C in (("A", A), ("B", B)):
        ex = [v for v in C if not np.any(np.abs(G-v) < 0.1)]
        ms = [v for v in G if not np.any(np.abs(C-v) < 0.1)]
        print(f"  {label}: extras={len(ex)} misses={len(ms)}")
    msB = [v for v in G if not np.any(np.abs(B-v) < 0.1)]
    for v in msB:
        idx = [i for i in range(len(P)) if abs(P[i, i_ax]-v) < 0.1]
        if not idx:
            continue
        info = [(int(i), bool(is_me[i]), int(mem[i]),
                 tuple(P[i].round(2))) for i in idx]
        print(f"   miss {v:9.3f}: {info[:8]}")
    exB = [v for v in B if not np.any(np.abs(G-v) < 0.1)]
    print(f"   B extras: {[round(v,3) for v in exB]}")

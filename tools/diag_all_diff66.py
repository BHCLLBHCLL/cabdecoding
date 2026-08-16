# P0 round 66: test hypotheses on the vertex filter:
#  H-corner: S-lines = projections of chain ENDPOINTS only (topological
#            corner vertices, edge valence != 2)
#  H-edge-purity: extras separate cleanly per model edge (some edges
#            contribute, some don't)
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
medge = set().union(*edge_nodes.values())

part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
tri = part.triangles

# mesh adjacency restricted to model-edge nodes -> corner = deg != 2
adj_all = {}
for a, b, c in tri:
    for u, v in ((a, b), (b, c), (c, a)):
        adj_all.setdefault(int(u), set()).add(int(v))
        adj_all.setdefault(int(v), set()).add(int(u))
medge = np.array(sorted(medge), int)
deg = np.array([len(adj_all.get(n, ()) & set(medge.tolist())) for n in medge])
corners = medge[deg != 2]
print(f"model-edge nodes={len(medge)} corners(deg!=2)={len(corners)} "
      f"deg histogram={np.bincount(deg)}")

gold = {ax: np.asarray([v for v in mk["s_lines"][ax]
                        if dom[0][i]+0.1 < v < dom[1][i]-0.1])
        for i, ax in enumerate("xyz")}

def proj(nodes, i_ax):
    col = np.sort(P[nodes, i_ax])
    lo, hi = dom[0][i_ax], dom[1][i_ax]
    col = col[(col > lo+0.1) & (col < hi-0.1)]
    out = []
    for x in col:
        if not out or abs(x-out[-1]) > 1e-3:
            out.append(float(x))
    return np.asarray(out)

def cmp(name, cand, g):
    ex = [v for v in cand if not np.any(np.abs(g-v) < 0.1)]
    ms = [v for v in g if not np.any(np.abs(cand-v) < 0.1)]
    print(f"  {name}: cand={len(cand)} gold={len(g)} extras={len(ex)} "
          f"miss={len(ms)}")
    return ex, ms

for i_ax, ax in enumerate("xyz"):
    print(f"\n{ax}:")
    cmp("all-nodes", proj(np.arange(len(P)), i_ax), gold[ax])
    cmp("corners", proj(corners, i_ax), gold[ax])
    cmp("edge-nodes", proj(medge, i_ax), gold[ax])

# H-edge-purity: per edge, fraction of its y-projections that are gold hits
i_ax = 1  # y
G = gold["y"]
pure_hit, pure_extra, mixed = 0, 0, 0
extra_edges = []
for ed, nodes in edge_nodes.items():
    vals = proj(np.array(sorted(nodes)), i_ax)
    if not len(vals):
        continue
    hits = sum(1 for v in vals if np.any(np.abs(G-v) < 0.1))
    if hits == len(vals):
        pure_hit += 1
    elif hits == 0:
        pure_extra += 1
        extra_edges.append((ed, len(nodes), len(vals)))
    else:
        mixed += 1
print(f"\nper-edge purity (y axis): pure-gold={pure_hit} pure-extra="
      f"{pure_extra} mixed={mixed}")
print("pure-extra edges (ed, nodes, vals):",
      sorted(extra_edges, key=lambda t: -t[2])[:15])

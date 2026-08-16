# P0 diagnostic round 43: edge-level attribution of anchor candidates.
# Use the 0x57C2 {fin, edge} table to group edge nodes by B-rep edge tag.
# Test whether keep/drop is decided per-edge (same edge -> all its node
# projections share fate), and list attributes of drop-only edges.
import json, sys, struct
from collections import defaultdict
from ctypes import string_at
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as pf
import cab_vtk, cab_grid

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
dmin = np.asarray(g["records"][0]["input"]["domain_min"], float)
dmax = np.asarray(g["records"][0]["input"]["domain_max"], float)

sess = pf._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")

# call facet with fin_edge and keep the raw tables: replicate
# facet_body_stpre but grab fin->edge pairs and fin->node idx.
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)

# we need fin-level data again: rerun the raw call and decode manually
res = sess._facet2_call([int(imp)], want_fin_edge=True)
tables = __import__("ctypes").cast(
    res.tables, __import__("ctypes").POINTER(
        pf._FacetTable * res.number_of_tables)).contents
data = {t.fctab: t.ptr for t in tables if t.ptr}

def table_wrapper(ptr):
    raw = string_at(ptr, 16)
    return struct.unpack_from("<Qi", raw)

def pairs(ptr, count):
    raw = string_at(ptr, count * 8)
    return [(struct.unpack_from("<i", raw, i*8)[0],
             struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(count)]

fd_ptr, fd_len = table_wrapper(data[pf.FCTAB_FIN_DATA])
fin_data = list(struct.unpack_from(
    "<%di" % fd_len, string_at(fd_ptr, fd_len*4)))
dp_ptr, dp_len = table_wrapper(data[pf.FCTAB_DATA_POINT_IDX])
point_of_data = list(struct.unpack_from(
    "<%di" % dp_len, string_at(dp_ptr, dp_len*4)))

fe_ptr = data.get(pf.FCTAB_FACET_FACE)
fe_data_ptr, fe_len = table_wrapper(fe_ptr)
fe_pairs = pairs(fe_data_ptr, fe_len)
edge_nodes: dict[int, set] = defaultdict(set)
for fin, edge in fe_pairs:
    if 0 <= fin < len(fin_data):
        di = fin_data[fin]
        if 0 <= di < len(point_of_data):
            edge_nodes[edge].add(point_of_data[di])
print(f"edges with nodes: {len(edge_nodes)}")

AX = int(sys.argv[1]) if len(sys.argv) > 1 else 2
ax = "xyz"[AX]
gold_s = np.asarray(marks["tr03_imp_vd_0"]["s_lines"][ax], float)

# candidate rough values (edge-node projections, cluster-merged 0.1)
Eall = P[part.edge_mask]
raw = Eall[:, AX]
raw = raw[(raw >= dmin[AX]) & (raw <= dmax[AX])]
rough = np.sort(cab_grid._clip_dedupe(
    [float(raw.min()), float(raw.max())] + [float(v) for v in raw],
    dmin[AX], dmax[AX], tol=0.1))
rough = np.asarray(rough, float)

# per-candidate source edges
cand_edges = {}
for v in rough:
    if abs(v - dmin[AX]) < 1e-9 or abs(v - dmax[AX]) < 1e-9:
        continue
    keep = bool(np.any(np.abs(gold_s - v) < 0.1))
    src = set()
    for e, nodes in edge_nodes.items():
        for ni in nodes:
            if abs(P[ni, AX] - v) < 0.1:
                src.add(e)
                break
    cand_edges[v] = (keep, src)

# edge fate purity: does any edge contribute to both keep and drop values?
edge_fate = defaultdict(set)
for v, (keep, src) in cand_edges.items():
    for e in src:
        edge_fate[e].add(keep)
mixed = [e for e, f in edge_fate.items() if len(f) > 1]
print(f"edges feeding both keep & drop values: {len(mixed)} / {len(edge_fate)}")

n_drop = sum(1 for k, _ in cand_edges.values() if not k)
n_keep = len(cand_edges) - n_drop
print(f"candidates keep={n_keep} drop={n_drop}")
# edges only in drops
drop_only = set()
for v, (keep, src) in cand_edges.items():
    if not keep:
        drop_only |= src
keep_src = set()
for v, (keep, src) in cand_edges.items():
    if keep:
        keep_src |= src
print(f"drop-only edges: {len(drop_only - keep_src)}; "
      f"edges shared keep+drop: {len(drop_only & keep_src)}")
shared = drop_only & keep_src
for e in sorted(shared)[:12]:
    vals_k = [round(v,3) for v,(k,s) in cand_edges.items() if k and e in s]
    vals_d = [round(v,3) for v,(k,s) in cand_edges.items() if not k and e in s]
    print(f"  edge {e}: keepvals={vals_k[:4]} dropvals={vals_d[:4]}")

# P0 diagnostic round 44: full candidate table (keep AND drop rows) with
# source-edge count, node count, and per-node triangle degree, to eyeball
# a separating predicate.  z axis default.
import json, sys, struct
from collections import defaultdict
from ctypes import string_at, cast, POINTER
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

part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
tris = np.asarray(part.triangles)

# triangle degree per node
deg = np.zeros(len(P), dtype=int)
for t3 in tris:
    for vi in t3:
        deg[vi] += 1

# fin->edge decode
res = sess._facet2_call([int(imp)], want_fin_edge=True)
tables = cast(res.tables, POINTER(pf._FacetTable * res.number_of_tables)).contents
data = {t.fctab: t.ptr for t in tables if t.ptr}

def table_wrapper(ptr):
    raw = string_at(ptr, 16)
    return struct.unpack_from("<Qi", raw)

def pairs(ptr, count):
    raw = string_at(ptr, count * 8)
    return [(struct.unpack_from("<i", raw, i*8)[0],
             struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(count)]

fd_ptr, fd_len = table_wrapper(data[pf.FCTAB_FIN_DATA])
fin_data = list(struct.unpack_from("<%di" % fd_len, string_at(fd_ptr, fd_len*4)))
dp_ptr, dp_len = table_wrapper(data[pf.FCTAB_DATA_POINT_IDX])
point_of_data = list(struct.unpack_from("<%di" % dp_len, string_at(dp_ptr, dp_len*4)))
fe_ptr = data.get(pf.FCTAB_FACET_FACE)
fe_data_ptr, fe_len = table_wrapper(fe_ptr)
edge_nodes = defaultdict(set)
for fin, edge in pairs(fe_data_ptr, fe_len):
    if 0 <= fin < len(fin_data):
        di = fin_data[fin]
        if 0 <= di < len(point_of_data):
            edge_nodes[edge].add(point_of_data[di])

AX = int(sys.argv[1]) if len(sys.argv) > 1 else 2
ax = "xyz"[AX]
gold_s = np.asarray(marks["tr03_imp_vd_0"]["s_lines"][ax], float)
Eall = P[part.edge_mask]
raw = Eall[:, AX]
raw = raw[(raw >= dmin[AX]) & (raw <= dmax[AX])]
rough = np.sort(cab_grid._clip_dedupe(
    [float(raw.min()), float(raw.max())] + [float(v) for v in raw],
    dmin[AX], dmax[AX], tol=0.1))
rough = np.asarray(rough, float)

print(f"== {ax}: {'value':>9} {'K/D':>3} {'#nod':>4} {'#edg':>4} {'degset':>12} ==")
for v in rough:
    if abs(v - dmin[AX]) < 1e-9 or abs(v - dmax[AX]) < 1e-9:
        continue
    keep = bool(np.any(np.abs(gold_s - v) < 0.1))
    nodes = [i for i in range(len(P))
             if part.edge_mask[i] and abs(P[i, AX] - v) < 0.1]
    src_e = set()
    for e, ns in edge_nodes.items():
        if any((np.abs(P[list(ns), AX] - v) < 0.1).any() for _ in [0]):
            src_e.add(e)
    degs = sorted(set(int(deg[i]) for i in nodes))
    print(f"  {v:>9.3f} {'K' if keep else 'D':>3} {len(nodes):>4} "
          f"{len(src_e):>4} {str(degs[:5]):>12}")

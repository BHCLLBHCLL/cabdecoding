# P0 diagnostic round 42: feature table for per-axis anchor candidates.
# For each cluster-merged edge-node projection value (candidate S line),
# classify keep (in golden S) vs drop, and print per-value features:
# source node count, membership stats, B-rep-vertex match, face count.
import json, sys
from collections import Counter
from ctypes import (byref, c_int, c_void_p, POINTER, memset, sizeof)
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as pf
import cab_vtk, cab_grid
from ps_facet2_nodes import (_Facet2OptionsV5, _Facet2Result, stpre_recipe,
                             STPRE_RECIPE)

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
E = P[part.edge_mask]
V = world(np.asarray(sess.body_vertices(imp))*1000.0)

probe = sess.facet2(imp, facet_tol=1e-4, facet_angle_deg=12.0)
pl = np.asarray(probe.points)
D = float(np.linalg.norm(pl.max(0) - pl.min(0)))
kw = stpre_recipe(D, angle_deg=STPRE_RECIPE["angle_deg"],
                  ccm=STPRE_RECIPE["ccm"], mfw=STPRE_RECIPE["mfw"],
                  cct=STPRE_RECIPE["cct"], spt=STPRE_RECIPE["spt"])

def facet_tag(tag):
    pk = sess.pk
    pk.PK_TOPOL_facet_2.restype = c_int
    pk.PK_TOPOL_facet_2.argtypes = [
        c_int, POINTER(c_int), c_void_p, POINTER(_Facet2OptionsV5),
        POINTER(_Facet2Result)]
    opts = _Facet2OptionsV5()
    memset(byref(opts), 0, sizeof(opts))
    opts.control.o_t_version = 5
    opts.control.max_facet_sides = 3
    for key, val in kw.items():
        setattr(opts.control, "is_" + key, 1)
        setattr(opts.control, key, float(val))
    opts.facet_fin = 1; opts.fin_data = 1; opts.data_point_idx = 1
    opts.point_vec = 1
    result = _Facet2Result()
    memset(byref(result), 0, sizeof(result))
    rc = pk.PK_TOPOL_facet_2(1, (c_int*1)(int(tag)), None, byref(opts), byref(result))
    if rc != 0 or result.number_of_tables <= 0 or not result.tables:
        return None
    return sess._decode_result(result, int(tag), f"face{tag}")

faces = sess.body_faces(imp)
node_count = Counter()
node_faces = {}
for f in faces:
    fp = facet_tag(f)
    if fp is None or not len(fp.points):
        continue
    Q = world(np.asarray(fp.points)*1000.0)
    for q in np.unique(np.round(Q, 6), axis=0):
        key = tuple(q)
        node_count[key] += 1
        node_faces.setdefault(key, set()).add(f)

keys = np.array(list(node_count.keys()))
counts = np.array(list(node_count.values()))
d2 = np.linalg.norm(keys[None, :, :] - E[:, None, :], axis=2)
membership = counts[np.argmin(d2, axis=1)]
mind = d2.min(axis=1)
membership[mind > 1e-3] = 0

AX = int(sys.argv[1]) if len(sys.argv) > 1 else 2  # default z
ax = "xyz"[AX]
gold_s = np.asarray(marks["tr03_imp_vd_0"]["s_lines"][ax], float)
raw = E[:, AX]
raw = raw[(raw >= dmin[AX]) & (raw <= dmax[AX])]
rough = np.sort(cab_grid._clip_dedupe(
    [float(raw.min()), float(raw.max())] + [float(v) for v in raw],
    dmin[AX], dmax[AX], tol=0.1))
rough = np.asarray(rough, float)

print(f"== {ax} axis: candidates={len(rough)} ==")
rows_keep, rows_drop = [], []
for v in rough:
    if abs(v - dmin[AX]) < 1e-9 or abs(v - dmax[AX]) < 1e-9:
        continue  # domain boundary
    keep = bool(np.any(np.abs(gold_s - v) < 0.1))
    sel = np.abs(E[:, AX] - v) < 0.1
    nodes = E[sel]
    idx = np.where(sel)[0]
    mems = membership[idx]
    bv = sum(1 for n in nodes
             if np.any(np.linalg.norm(V - n, axis=1) < 1e-6))
    nfac = [len(node_faces.get(tuple(np.round(n, 6)), ())) for n in nodes]
    med_mem = int(np.median(mems)) if len(mems) else -1
    row = dict(v=v, keep=keep, n=len(nodes),
               mem=(int(mems.min()), med_mem, int(mems.max())) if len(mems) else (9, 9, 9),
               bv=bv, fac=max(nfac) if nfac else 0)
    (rows_keep if keep else rows_drop).append(row)

print(f"{'value':>10} {'keep':>4} {'#nodes':>6} {'mem(min/med/max)':>16} {'bv':>3} {'maxfac':>6}")
for r in rows_drop:
    print(f"{r['v']:>10.3f} {'DROP':>4} {r['n']:>6} "
          f"{str(r['mem']):>16} {r['bv']:>3} {r['fac']:>6}")
print("---- keep mem-min histogram:", Counter(r['mem'][0] for r in rows_keep))
print("---- drop mem-min histogram:", Counter(r['mem'][0] for r in rows_drop))
print("---- keep bv>0:", sum(1 for r in rows_keep if r['bv'] > 0),
      " drop bv>0:", sum(1 for r in rows_drop if r['bv'] > 0))

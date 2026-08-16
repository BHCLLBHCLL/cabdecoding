# P0 diagnostic round 23: anchors = projections of nodes shared by >=2
# faces (i.e. nodes on model edges) vs interior (1-face) nodes?
# Also test: nodes on B-rep edges via per-face membership count.
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as pf
import cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

sess = pf._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
whole = sess.facet_body_stpre(imp)
P = world(np.asarray(whole.points)*1000.0)

# per-node face-membership count via triangles' fin_edge data is not
# available here; use per-face faceting (diff22) and coordinate matching.
from ctypes import (byref, c_int, c_void_p, POINTER, memset, sizeof)
from ps_facet2_nodes import (_Facet2OptionsV5, _Facet2Result, stpre_recipe,
                             STPRE_RECIPE)

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
    opts.facet_fin = 1
    opts.fin_data = 1
    opts.data_point_idx = 1
    opts.point_vec = 1
    result = _Facet2Result()
    memset(byref(result), 0, sizeof(result))
    rc = pk.PK_TOPOL_facet_2(
        1, (c_int * 1)(int(tag)), None, byref(opts), byref(result))
    if rc != 0 or result.number_of_tables <= 0 or not result.tables:
        return None
    return sess._decode_result(result, int(tag), f"face{tag}")

faces = sess.body_faces(imp)
node_count = Counter()
for f in faces:
    part = facet_tag(f)
    if part is None or not len(part.points):
        continue
    Q = world(np.asarray(part.points)*1000.0)
    for q in np.unique(np.round(Q, 6), axis=0):
        node_count[tuple(q)] += 1

# map whole-body nodes to membership count (nearest within 1e-4)
keys = np.array(list(node_count.keys()))
counts = np.array(list(node_count.values()))
d2 = np.linalg.norm(keys[None, :, :] - P[:, None, :], axis=2)
membership = counts[np.argmin(d2, axis=1)]
mind = d2.min(axis=1)
membership[mind > 1e-3] = 0
print("membership histogram:", Counter(membership.tolist()))

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(P[:, i_ax])
    d = np.min(np.abs(vals[None, :] - gold[:, None]), axis=1)
    anchors = set(np.round(gold[d < 1e-9], 9))
    # candidate sets by membership threshold
    for mthr in (2, 3):
        sel = P[membership >= mthr][:, i_ax]
        if len(sel) == 0:
            continue
        sv = np.unique(sel)
        hit = sum(1 for a in anchors if np.any(np.abs(sv - a) < 1e-6))
        extra = len(sv) - sum(1 for v in sv if any(abs(v - a) < 1e-6 for a in anchors))
        print(f"{ax} m>={mthr}: vals={len(sv)} anchor-hit={hit}/{len(anchors)} "
              f"extra={extra}")

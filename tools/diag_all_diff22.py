# P0 diagnostic round 22: per-FACE facet attribution.  Facet every face of
# the Impeller with the body-diagonal STpre recipe, then check per face and
# per axis whether its node coordinates are golden anchors or not.
import json, sys
from ctypes import (byref, c_int, c_void_p, POINTER, cast, memset, sizeof,
                    c_double)
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as pf
import cab_vtk
from ps_facet2_nodes import (_Facet2OptionsV5, _Facet2Result, stpre_recipe,
                             STPRE_RECIPE)

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

sess = pf._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")

# body-diagonal D (same value facet_body_stpre uses)
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

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

# anchor lookup per axis: exact float64 values
whole = sess.facet_body_stpre(imp)
Pw = world(np.asarray(whole.points)*1000.0)
anchor_sets = {}
for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(Pw[:, i_ax])
    d = np.min(np.abs(vals[None, :] - gold[:, None]), axis=1)
    anchor_sets[ax] = np.round(gold[d < 1e-9], 9)

faces = sess.body_faces(imp)
print(f"faces={len(faces)}")
rows = []
for f in faces:
    part = facet_tag(f)
    if part is None or not len(part.points):
        rows.append((f, None))
        continue
    Q = world(np.asarray(part.points)*1000.0)
    stat = {}
    for i_ax, ax in enumerate("xyz"):
        fv = np.unique(Q[:, i_ax])
        A = anchor_sets[ax]
        hit = sum(1 for v in fv if np.any(np.abs(A - v) < 1e-6))
        stat[ax] = (hit, len(fv) - hit)
    rows.append((f, Q, stat))

print(f"\n{'face':>6} {'nodes':>6}   x(anch,non)   y(anch,non)   z(anch,non)")
pure = {"x": 0, "y": 0, "z": 0}
for r in rows:
    if len(r) == 2:
        print(f"{r[0]:>6} FACET-FAIL")
        continue
    f, Q, stat = r
    print(f"{f:>6} {len(Q):>6}   "
          f"{stat['x'][0]:>3},{stat['x'][1]:>3}       "
          f"{stat['y'][0]:>3},{stat['y'][1]:>3}       "
          f"{stat['z'][0]:>3},{stat['z'][1]:>3}")
    for ax in "xyz":
        if stat[ax][1] == 0:
            pure[ax] += 1
print("\nfaces with zero non-anchor coords:", pure)

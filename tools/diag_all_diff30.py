# P0 diagnostic round 30: face normal vs per-axis keep purity.
# Small faces are pure-anchored or all-dropped per axis; test whether the
# face normal's component sign/magnitude on each axis decides it.
import json, sys
from ctypes import (byref, c_int, c_void_p, POINTER, cast, memset, sizeof)
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

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

whole = sess.facet_body_stpre(imp)
Pw = world(np.asarray(whole.points)*1000.0)
def geo_values(col, tol=1e-6):
    v = np.sort(np.unique(col))
    out = [v[0]]
    for x in v[1:]:
        if x - out[-1] > tol:
            out.append(x)
    return np.asarray(out)

gold_sets = {ax: np.round(np.asarray(rec0["output"]["axes"][ax], float), 6)
             for ax in "xyz"}
dropped = {}
for i, ax in enumerate("xyz"):
    gv = geo_values(Pw[:, i])
    d = np.min(np.abs(gv[:, None] - gold_sets[ax][None, :]), axis=1)
    dropped[ax] = set(np.round(gv[d > 1e-6], 6).tolist())

faces = sess.body_faces(imp)
print(f"{'face':>6} {'nodes':>5}  normal(la,lb,lc)          pure-y  pure-z")
data = []
for f in faces:
    part = facet_tag(f)
    if part is None or not len(part.points):
        continue
    Q = world(np.asarray(part.points)*1000.0)
    # fit plane normal
    c = Q.mean(0)
    _, sv, vt = np.linalg.svd(Q - c)
    n = vt[-1]
    resid = sv[-1]
    stat = {}
    for i_ax, ax in enumerate("xyz"):
        fv = geo_values(Q[:, i_ax])
        nd = sum(1 for v in fv if round(float(v), 6) in dropped[ax])
        stat[ax] = (len(fv) - nd, nd)  # anchored, dropped
    py = ("ALL" if stat["y"][1] == 0 and stat["y"][0] > 0 else
          "DROP" if stat["y"][0] == 0 else "mix")
    pz = ("ALL" if stat["z"][1] == 0 and stat["z"][0] > 0 else
          "DROP" if stat["z"][0] == 0 else "mix")
    data.append((f, len(Q), n, resid, py, pz, stat))

# summary: normal sign vs purity per axis
from collections import Counter
for i_ax, ax in enumerate("xyz"):
    tab = Counter()
    for f, nq, n, resid, py, pz, stat in data:
        if nq > 15:      # small faces only
            continue
        p = py if ax == "y" else pz
        tab[(p, round(float(n[i_ax]), 1))] += 1
    print(f"\n{ax}: purity x normal-component (small faces)")
    for (p, nc), c in sorted(tab.items()):
        print(f"  pure={p:4s} n_{ax}={nc:+5.1f}: {c}")

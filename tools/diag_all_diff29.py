# P0 diagnostic round 29: per-face purity.  For every face list
# (surf-class, nodes, per-axis anchored/total).  Faces whose projections
# are ALL non-golden are the drop contributors - find their common trait.
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

SURF_CLASSES = {4001:"c4001", 4002:"c4002", 5202:"plane", 5203:"cylinder",
                5205:"torus", 5208:"bsurf"}

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

def surf_class(tag):
    pk = sess.pk
    pk.PK_FACE_ask_surf.restype = c_int
    pk.PK_FACE_ask_surf.argtypes = [c_int, POINTER(c_int)]
    s = c_int(0)
    if pk.PK_FACE_ask_surf(int(tag), byref(s)) != 0 or s.value == 0:
        return None
    return sess.entity_class(s.value)

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

whole = sess.facet_body_stpre(imp)
Pw = world(np.asarray(whole.points)*1000.0)
# geometric value clusters of the whole body per axis (noise-collapsed)
def geo_values(col, tol=1e-6):
    v = np.sort(np.unique(col))
    out = [v[0]]
    for x in v[1:]:
        if x - out[-1] > tol:
            out.append(x)
    return np.asarray(out)

geo = {ax: geo_values(Pw[:, i]) for i, ax in enumerate("xyz")}
gold_sets = {}
for i, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    gold_sets[ax] = np.round(gold, 6)
print("geo projection counts:",
      {ax: len(geo[ax]) for ax in "xyz"})
dropped = {}
for i, ax in enumerate("xyz"):
    d = np.min(np.abs(geo[ax][:, None] - gold_sets[ax][None, :]), axis=1)
    dropped[ax] = set(np.round(geo[ax][d > 1e-6], 6).tolist())
    print(f"{ax}: geo={len(geo[ax])} dropped={len(dropped[ax])}")

faces = sess.body_faces(imp)
rows = []
for f in faces:
    sc = surf_class(f)
    part = facet_tag(f)
    if part is None or not len(part.points):
        continue
    Q = world(np.asarray(part.points)*1000.0)
    stat = {}
    for i_ax, ax in enumerate("xyz"):
        fv = geo_values(Q[:, i_ax])
        n_anchor = sum(1 for v in fv
                       if round(float(v), 6) not in dropped[ax])
        stat[ax] = (n_anchor, len(fv) - n_anchor)
    rows.append((f, SURF_CLASSES.get(sc, str(sc)), len(Q), stat))

rows.sort(key=lambda r: (r[1], -r[2]))
print(f"\n{'face':>6} {'type':>8} {'nodes':>6}  y(anch,drop)  z(anch,drop)")
allpure, allanchor = [], []
for f, sc, n, stat in rows:
    tag = ""
    if stat["y"][1] > 0 and stat["z"][1] > 0:
        pass
    if stat["y"][0] == 0 and stat["y"][1] > 0:
        tag += " Y-ALLDROP"
    if stat["z"][0] == 0 and stat["z"][1] > 0:
        tag += " Z-ALLDROP"
    if not tag and stat["y"][1] == 0 and stat["z"][1] == 0:
        tag = " PURE-ANCHOR"
    print(f"{f:>6} {sc:>8} {n:>6}  {stat['y'][0]:>4},{stat['y'][1]:<4}    "
          f"{stat['z'][0]:>4},{stat['z'][1]:<4}  {tag}")

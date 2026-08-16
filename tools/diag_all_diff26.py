# P0 diagnostic round 26: face-TYPE discrimination.  STpre pushes grid
# lines from PreFace (PushLine@PreFace); test whether the golden anchor
# keep/drop decision for each STL projection value correlates with the
# surface type (planar/cylindrical/conical/toroidal/spline) of the faces
# whose tessellation nodes project onto that value.
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

FACE_TYPES = {0:"unknown",1:"planar",2:"cylindrical",3:"conical",
              4:"toroidal",5:"spline",6:"massive",7:"blank",8:"defunct",
              9:"transform",10:"foreign",11:"parametric",12:"spun",
              13:"scanned",14:"offset",15:"blend",16:"constant_blend",
              17:"rolling_ball_blend",18:"vertex_blend",19:" Fashion",
              20:"mesh",21:"construction",22:"extrusion",23:"swept",
              24:" plspline",25:"torus_plspline"}

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

SURF_CLASSES = {5201:"surf",5202:"plane",5203:"cylinder",5204:"cone",
                5205:"torus",5206:"spin",5207:"bag",5208:"bsurf",
                5209:"offset",5210:"foreign",5211:"fashion",5212:"mesh",
                5213:"plspline",5214:"torus_plspline",5215:"construction"}

def face_type(tag):
    """Surface class via PK_FACE_ask_surf + entity_class (ask_type broken)."""
    pk = sess.pk
    try:
        pk.PK_FACE_ask_surf.restype = c_int
        pk.PK_FACE_ask_surf.argtypes = [c_int, POINTER(c_int)]
    except OSError:
        return None
    s = c_int(0)
    if pk.PK_FACE_ask_surf(int(tag), byref(s)) != 0 or s.value == 0:
        return None
    return sess.entity_class(s.value)

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
dom_lo = np.asarray(rec0["input"]["domain_min"], float)
dom_hi = np.asarray(rec0["input"]["domain_max"], float)

whole = sess.facet_body_stpre(imp)
Pw = world(np.asarray(whole.points)*1000.0)

faces = sess.body_faces(imp)
print(f"faces={len(faces)}")

# value -> set of face types touching it (per axis)
from collections import defaultdict
types_of = [defaultdict(set) for _ in range(3)]
ftype_hist = defaultdict(int)
nf_facet_fail = 0
for f in faces:
    ft = face_type(f)
    ftype_hist[ft] += 1
    part = facet_tag(f)
    if part is None or not len(part.points):
        nf_facet_fail += 1
        continue
    Q = world(np.asarray(part.points)*1000.0)
    for i_ax in range(3):
        for v in np.unique(Q[:, i_ax]):
            types_of[i_ax][round(float(v), 6)].add(ft)
print(f"face types histogram: "
      f"{ {SURF_CLASSES.get(k,k): v for k,v in sorted(ftype_hist.items())} }")
print(f"facet-failed faces: {nf_facet_fail}")

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(Pw[:, i_ax])
    in_dom = vals[(vals >= dom_lo[i_ax]) & (vals <= dom_hi[i_ax])]
    kept = np.array([np.min(np.abs(gold - v)) < 1e-6 for v in in_dom])
    print(f"\n=== {ax}: in-domain vals={len(in_dom)} kept={kept.sum()} "
          f"dropped={(~kept).sum()} ===")
    # per-face-type keep stats (a value touched by >=1 node on that type)
    stat = defaultdict(lambda: [0, 0])
    for v, k in zip(in_dom, kept):
        for ft in types_of[i_ax].get(round(float(v), 6), (None,)):
            stat[ft][0 if k else 1] += 1
    for ft, (nk, nd) in sorted(stat.items(), key=lambda kv: str(kv[0])):
        name = SURF_CLASSES.get(ft, str(ft)) if ft is not None else "no-face"
        print(f"  {name:>14}: kept={nk:3d} dropped={nd:3d}")
    # values with no face attribution
    noattr = [v for v, k in zip(in_dom, kept)
              if round(float(v), 6) not in types_of[i_ax]]
    print(f"  values without face attribution: {len(noattr)}")

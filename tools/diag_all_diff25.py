# P0 diagnostic round 25: inspect the 0x57C2 table semantics on tr03.
# Hypothesis: records are {fin, X} where X may be face (V35 facet_face)
# or edge.  Compare field-2 unique values against body faces/edges and
# test which node mask reproduces the golden anchor lines.
import json, sys, struct
from pathlib import Path
from ctypes import string_at, byref, memset, sizeof, c_int, c_void_p, POINTER, cast
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk
from ps_facet2_nodes import (_Facet2OptionsV5, _Facet2Result, _FacetTable,
    FCTAB_FACET_FACE, FCTAB_FACET_FIN, FCTAB_FIN_DATA,
    FCTAB_DATA_POINT_IDX, FCTAB_POINT_VEC, stpre_recipe, STPRE_RECIPE)

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
faces = sess.body_faces(imp)
edges = sess.body_edges(imp)
print(f"body faces={len(faces)} edges={len(edges)}")

_probe = sess.facet2(imp, facet_tol=1e-4, facet_angle_deg=12.0)
_pl = np.asarray(_probe.points) * 1000.0
D = float(np.linalg.norm(_pl.max(0) - _pl.min(0))) / 1000.0
kw = stpre_recipe(D, angle_deg=STPRE_RECIPE["angle_deg"], ccm=STPRE_RECIPE["ccm"],
    mfw=STPRE_RECIPE["mfw"], cct=STPRE_RECIPE["cct"], spt=STPRE_RECIPE["spt"])

pk = sess.pk
pk.PK_TOPOL_facet_2.restype = c_int
pk.PK_TOPOL_facet_2.argtypes = [c_int, POINTER(c_int), c_void_p,
    POINTER(_Facet2OptionsV5), POINTER(_Facet2Result)]
opts = _Facet2OptionsV5()
memset(byref(opts), 0, sizeof(opts))
opts.control.o_t_version = 5
opts.control.max_facet_sides = 3
for k, v in kw.items():
    setattr(opts.control, "is_"+k, 1)
    setattr(opts.control, k, float(v))
opts.facet_fin = 1; opts.fin_data = 1; opts.data_point_idx = 1
opts.point_vec = 1; opts.fin_edge = 1
result = _Facet2Result()
memset(byref(result), 0, sizeof(result))
rc = pk.PK_TOPOL_facet_2(1, (c_int*1)(imp), None, byref(opts), byref(result))
print(f"facet rc={rc} tables={result.number_of_tables}")

tables = cast(result.tables, POINTER(_FacetTable*result.number_of_tables)).contents
data = {t.fctab: t.ptr for t in tables if t.ptr}

def wrap(ptr):
    raw = string_at(ptr, 16)
    return struct.unpack_from("<Qi", raw)

def pairs(ptr, n):
    raw = string_at(ptr, n*8)
    return [(struct.unpack_from("<i", raw, i*8)[0],
             struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(n)]

ff_ptr, ff_n = wrap(data[FCTAB_FACET_FIN])
fin_of_facet = {}
for facet, fin in pairs(ff_ptr, ff_n):
    if fin >= 0 and facet >= 0:
        fin_of_facet.setdefault(facet, []).append(fin)

fd_ptr, fd_n = wrap(data[FCTAB_FIN_DATA])
fin_data = list(struct.unpack_from("<%di"%fd_n, string_at(fd_ptr, fd_n*4)))
dp_ptr, dp_n = wrap(data[FCTAB_DATA_POINT_IDX])
point_of_data = list(struct.unpack_from("<%di"%dp_n, string_at(dp_ptr, dp_n*4)))
pv_ptr, pv_n = wrap(data[FCTAB_POINT_VEC])
P = np.frombuffer(string_at(pv_ptr, pv_n*24), dtype="<f8", count=pv_n*3)\
      .reshape(-1,3).copy()
W = world(P*1000.0)
print(f"nodes={len(P)} facets(tris)={len(fin_of_facet)} fins={len(fin_data)}")

fe_ptr, fe_n = wrap(data[FCTAB_FACET_FACE])
fe = pairs(fe_ptr, fe_n)
f1 = np.array([a for a,b in fe]); f2 = np.array([b for a,b in fe])
print(f"0x57C2 records={fe_n} field1[min,max]=({f1.min()},{f1.max()}) "
      f"field2 uniques={len(np.unique(f2))}")
print(f"  field2 values: {sorted(np.unique(f2))[:25]}")
print(f"  -> field1 looks like {'FACET' if f1.max() >= len(fin_data) else 'FIN'}"
      f" (n_fins={len(fin_data)}, n_facets={len(fin_of_facet)})")

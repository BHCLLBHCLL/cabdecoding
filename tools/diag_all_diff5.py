# P0 diagnostic round 5: fin_edge table raw stats + strict edge!=0 mask.
import json, sys, math, struct
from ctypes import string_at, cast, POINTER
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk
from ps_facet2_nodes import _Facet2Result, _FacetTable

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")

# derive bbox diagonal from a probe facet (body_box unavailable on this tag)
_probe = sess.facet2(imp, facet_tol=1e-4, facet_angle_deg=12.0)
_pl = np.asarray(_probe.points) * 1000.0
D = float(np.linalg.norm(_pl.max(0) - _pl.min(0))) / 1000.0
kw = ps_facet2_nodes.stpre_recipe(D, angle_deg=10.0)
from ps_facet2_nodes import _Facet2OptionsV5, FCTAB_FACET_FACE
from ctypes import memset, byref, sizeof, c_int, c_void_p
pk = sess.pk
pk.PK_TOPOL_facet_2.restype = c_int
pk.PK_TOPOL_facet_2.argtypes = [c_int, POINTER(c_int), c_void_p,
                                POINTER(_Facet2OptionsV5), POINTER(_Facet2Result)]
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
opts.fin_edge = 1
result = _Facet2Result()
memset(byref(result), 0, sizeof(result))
rc = pk.PK_TOPOL_facet_2(1, (c_int*1)(imp), None, byref(opts), byref(result))
print("rc:", rc, "tables:", result.number_of_tables)
tables = cast(result.tables, POINTER(_FacetTable * result.number_of_tables)).contents
data = {t.fctab: t.ptr for t in tables if t.ptr}

def wrapper(ptr):
    raw = string_at(ptr, 16)
    return struct.unpack_from("<Qi", raw)

for tok, name in ((0x57C2, "fin_edge(0x57C2)"), (0x57B2, "facet_fin")):
    if tok in data:
        dp, ln = wrapper(data[tok])
        raw = string_at(dp, ln*8)
        recs = [(struct.unpack_from("<i", raw, i*8)[0],
                 struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(ln)]
        edges = [e for _, e in recs]
        print(f"{name}: {ln} records, distinct edges {len(set(edges))}, "
              f"zero-edges {edges.count(0)}, negative {sum(1 for e in edges if e < 0)}")
        print("  first 10:", recs[:10])

# strict mask: only fins whose edge tag is a plausible PK_EDGE (class bits)
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
T = np.asarray(part.triangles)
# rebuild strict mask from records
dp, ln = wrapper(data[0x57C2])
raw = string_at(dp, ln*8)
recs = [(struct.unpack_from("<i", raw, i*8)[0],
         struct.unpack_from("<i", raw, i*8+4)[0]) for i in range(ln)]
fd_ptr, fd_len = wrapper(data[0x57B6])
fin_data = list(struct.unpack_from("<%di" % fd_len, string_at(fd_ptr, fd_len*4)))
dp_ptr, dp_len = wrapper(data[0x57B7])
point_of_data = list(struct.unpack_from("<%di" % dp_len, string_at(dp_ptr, dp_len*4)))
strict = np.zeros(len(P), bool)
for fin, edge in recs:
    if edge != 0 and 0 <= fin < len(fin_data):
        di = fin_data[fin]
        if 0 <= di < len(point_of_data):
            pi = point_of_data[di]
            if 0 <= pi < len(P):
                strict[pi] = True
print("strict mask:", int(strict.sum()), "of", len(P))

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
inp = rec0["input"]
lo, hi = P.min(0), P.max(0)
v = sess.body_vertices(imp)
verts_w = world(np.asarray(v)*1000.0)
_orig = cab_grid.stpre_rules._trunc_round
cab_grid.stpre_rules._trunc_round = lambda x: max(1, math.ceil(x - 1e-9))
try:
    for label, pts in (("all", P), ("strict-edge", P[strict])):
        spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]),
            domain_max=tuple(inp["domain_max"]), vertex_detection="all",
            method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
            threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
            geometric_ratio_external=tuple(inp["ratio_out"]))
        _, detailed = cab_grid.build_axes({"Impeller": pts}, spec,
                                          part_vertices={"Impeller": verts_w},
                                          part_bounds=(lo, hi))
        res = []
        for ax in "xyz":
            gold = np.asarray(rec0["output"]["axes"][ax], float)
            nat = np.asarray(detailed[ax], float)
            if len(gold) == len(nat) and np.max(np.abs(np.sort(nat)-np.sort(gold))) <= 2e-4:
                res.append(f"{ax}:OK({len(nat)})")
            else:
                res.append(f"{ax}:{len(nat)}vs{len(gold)}")
        print(f"{label}: {res}")
finally:
    cab_grid.stpre_rules._trunc_round = _orig

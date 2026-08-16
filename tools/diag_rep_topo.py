# P0 rep: correlate B-rep vertex keep/drop with topology (edges,
# smoothness, face types).
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk
from ctypes import (c_int, c_void_p, POINTER, byref, cast)

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_1"]
dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
pk = sess.pk

gold_s = {}
for i, ax in enumerate("xyz"):
    gold_s[ax] = np.asarray(
        [x for x in mk["s_lines"][ax]
         if dom[0][i]+0.1 < x < dom[1][i]-0.1], float)

# body vertices (tags + points)
pk.PK_BODY_ask_vertices.restype = c_int
pk.PK_BODY_ask_vertices.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
n = c_int(0); arr = c_void_p()
rc = pk.PK_BODY_ask_vertices(int(imp), byref(n), byref(arr))
vtags = list(cast(arr, POINTER(c_int * n.value)).contents)
print("body vertices:", len(vtags))

# vertex faces
def vertex_faces(vt):
    pk.PK_VERTEX_ask_faces.restype = c_int
    pk.PK_VERTEX_ask_faces.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
    m = c_int(0); fa = c_void_p()
    if pk.PK_VERTEX_ask_faces(int(vt), byref(m), byref(fa)) != 0:
        return []
    if not fa or m.value <= 0:
        return []
    return list(cast(fa, POINTER(c_int * m.value)).contents)

def face_type(ft):
    pk.PK_FACE_ask_type.restype = c_int
    pk.PK_FACE_ask_type.argtypes = [c_int, POINTER(c_int)]
    t = c_int(0)
    if pk.PK_FACE_ask_type(int(ft), byref(t)) != 0:
        return -1
    return t.value

def edge_is_smooth(et):
    pk.PK_EDGE_is_smooth.restype = c_int
    pk.PK_EDGE_is_smooth.argtypes = [c_int, POINTER(c_int)]
    s = c_int(0)
    if pk.PK_EDGE_is_smooth(int(et), byref(s)) != 0:
        return None
    return s.value

# edges -> vertices (for vertex adjacency), faces
edges = sess.body_edges(imp)
print("body edges:", len(edges))
pk.PK_EDGE_ask_vertices.restype = c_int
pk.PK_EDGE_ask_vertices.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
pk.PK_EDGE_ask_faces.restype = c_int
pk.PK_EDGE_ask_faces.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]

v_edges = defaultdict(list)
e_smooth = {}
e_ftypes = {}
for et in edges:
    m = c_int(0); va = c_void_p()
    if pk.PK_EDGE_ask_vertices(int(et), byref(m), byref(va)) != 0:
        continue
    if not va or m.value <= 0:
        vs = []
    else:
        vs = list(cast(va, POINTER(c_int * m.value)).contents)
    e_smooth[et] = edge_is_smooth(et)
    m2 = c_int(0); fa = c_void_p()
    fts = []
    if (pk.PK_EDGE_ask_faces(int(et), byref(m2), byref(fa)) == 0
            and fa and m2.value > 0):
        fs = list(cast(fa, POINTER(c_int * m2.value)).contents)
        fts = sorted(face_type(f) for f in fs)
    e_ftypes[et] = fts
    for v in vs:
        v_edges[v].append(et)

# per-vertex feature table
rows = []
for vt in vtags:
    p = sess.vertex_point(vt)
    if p is None:
        continue
    W = world(p.reshape(1, 3) * 1000.0)[0]
    es = v_edges.get(vt, [])
    sms = [e_smooth.get(e) for e in es]
    fts = sorted(face_type(f) for f in vertex_faces(vt))
    rows.append(dict(tag=vt, pos=W, n_edges=len(es),
                     n_smooth=sum(1 for s in sms if s == 1),
                     n_sharp=sum(1 for s in sms if s == 0),
                     n_unknown_sm=sum(1 for s in sms if s not in (0, 1)),
                     face_types=tuple(fts)))

print("rows:", len(rows))

# classify per-axis keep/drop
for i, ax in enumerate("xyz"):
    gz = gold_s[ax]
    keep_rows, drop_rows = [], []
    seen = set()
    for r in rows:
        key = round(r["pos"][i], 6)
        lo, hi = dom[0][i]+0.1, dom[1][i]-0.1
        if not (lo < key < hi):
            continue
        # dedupe by value so repeated vertices don't double-count
        is_keep = bool(np.any(np.abs(gz - key) < 0.1))
        (keep_rows if is_keep else drop_rows).append((key, r))
    uniq_keep = {}
    uniq_drop = {}
    for key, r in keep_rows:
        uniq_keep.setdefault(key, r)
    for key, r in drop_rows:
        uniq_drop.setdefault(key, r)
    # a value is DROPPED only if no vertex with that value is kept
    drop_vals = [k for k in uniq_drop if k not in uniq_keep]
    keep_vals = [k for k in uniq_keep if True]
    print(f"\n=== {ax}: keep {len(set(keep_vals))} drop {len(drop_vals)}")
    for label, vals in (("KEEP", sorted(set(keep_vals))),
                        ("DROP", sorted(drop_vals))):
        print(f" {label}:")
        for k in vals:
            rs = [r for key, r in keep_rows + drop_rows if key == k]
            for r in rs[:1]:
                print(f"   {k:9.3f} deg={r['n_edges']} "
                      f"smooth={r['n_smooth']} sharp={r['n_sharp']} "
                      f"unk={r['n_unknown_sm']} faces={r['face_types']}")

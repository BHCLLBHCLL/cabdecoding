# P0 rep: rotational-sector hypothesis.  Label each B-rep vertex by
# keep/drop (per-axis value level) and inspect its cylindrical angle.
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk
from ctypes import c_int, c_void_p, POINTER, byref, cast

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

gold_s = {ax: np.asarray(
    [x for x in mk["s_lines"][ax]
     if dom[0][i]+0.1 < x < dom[1][i]-0.1], float)
    for i, ax in enumerate("xyz")}

V = world(sess.body_vertices(imp)*1000.0)
print("vertices:", len(V))

# radius/angle about the z axis (x = axis of the impeller?)
r_xy = np.hypot(V[:, 0], V[:, 1])
th_xy = np.degrees(np.arctan2(V[:, 1], V[:, 0])) % 360.0
r_yz = np.hypot(V[:, 1], V[:, 2])
th_yz = np.degrees(np.arctan2(V[:, 2], V[:, 1])) % 360.0

# impeller axis: x probably (hub along x).  Group vertices by radius
# shells and list (theta, y, z, ykeep, zkeep)
def val_label(ax_i, val):
    gz = gold_s["xyz"[ax_i]]
    lo, hi = dom[0][ax_i]+0.1, dom[1][ax_i]-0.1
    if not (lo < val < hi):
        return "out"
    return "K" if np.any(np.abs(gz - val) < 0.1) else "D"

# cluster identical vertices (dupes) by rounding
key = np.round(V, 6)
uniq, idx = np.unique(key, axis=0, return_index=True)
print("unique vertices:", len(uniq))

rows = []
for i in idx:
    y_k = val_label(1, V[i, 1])
    z_k = val_label(2, V[i, 2])
    rows.append((V[i, 0], V[i, 1], V[i, 2], th_xy[i], r_xy[i], y_k, z_k))

# hypothesis test: for each rotational family (same r_xy to 3 decimals,
# same x), list angles + labels
fam = defaultdict(list)
for x, y, z, th, r, yk, zk in rows:
    fam[(round(x, 4), round(r, 4))].append((th, yk, zk, round(z, 3), round(y, 3)))

n_fam = 0
for k in sorted(fam):
    members = sorted(fam[k])
    if len(members) < 2:
        continue
    n_fam += 1
    labs = "".join(m[1] for m in members)
    if n_fam <= 40:
        print(f"x={k[0]:8.3f} r={k[1]:7.3f} n={len(members)} "
              + " ".join(f"{m[0]:6.1f}/{m[1]}{m[2]}/z{m[3]:8.3f}"
                         for m in members))
print("families >=2:", n_fam)

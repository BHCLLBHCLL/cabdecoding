# P0 diagnostic round 12: per-S-line features -> what distinguishes kept vs
# dropped display-mesh projection lines?
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

stl_path = ROOT/"tools"/"probe_work"/"imp_stpre.stl"
raw = stl_path.read_bytes()
txt = raw.decode("ascii", "ignore").split()
tris, i = [], 0
while i < len(txt):
    if txt[i] == "vertex":
        tris.append((float(txt[i+1]), float(txt[i+2]), float(txt[i+3])))
        i += 4
    else:
        i += 1
S = np.asarray(tris)*1000.0
Su, inv = np.unique(np.round(S, 6), axis=0, return_inverse=True)
T = inv.reshape(-1, 3)
# vertex normals from incident triangle normals
tn = np.zeros((len(T), 3))
for k in range(len(T)):
    a, b, c = Su[T[k, 0]], Su[T[k, 1]], Su[T[k, 2]]
    tn[k] = np.cross(b - a, c - a)
    n = np.linalg.norm(tn[k])
    if n > 0:
        tn[k] /= n
vn = np.zeros((len(Su), 3))
for k in range(len(T)):
    vn[T[k]] += tn[k]
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-30)
# crease: max angle between incident triangle normals at each vertex
from collections import defaultdict
inc = defaultdict(list)
for k in range(len(T)):
    for v in T[k]:
        inc[v].append(k)
crease = np.zeros(len(Su))
for v, ks in inc.items():
    N = tn[ks]
    dots = np.clip(N @ N.T, -1, 1)
    crease[v] = np.degrees(np.arccos(dots.min()))

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
TOL = 0.02

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(np.round(Su[:, i_ax], 6))
    in_dom = vals[(vals >= gold[0] - 0.05) & (vals <= gold[-1] + 0.05)]
    print(f"\n=== {ax} ===")
    kept_v, drop_v = [], []
    for v in in_dom:
        m = np.abs(Su[:, i_ax] - v) < 1e-4
        feat = dict(n=int(m.sum()),
                    crease=float(crease[m].max()),
                    ncomp=float(np.abs(vn[m, i_ax]).max()))
        rec = (float(v), feat)
        if np.any(np.abs(gold - v) < TOL):
            kept_v.append(rec)
        else:
            drop_v.append(rec)
    print(f"kept={len(kept_v)} dropped={len(drop_v)}")
    print("dropped (value, nverts, maxcrease, max|n_ax|):")
    for v, f in drop_v:
        # distance to nearest kept S line
        kd = min(abs(v - kv) for kv, _ in kept_v) if kept_v else -1
        print(f"  {v:9.4f}  n={f['n']:3d} crease={f['crease']:6.1f} "
              f"|n{ax}|={f['ncomp']:.3f} d_keep={kd:.4f}")
    kc = np.array([f["crease"] for _, f in kept_v])
    dc = np.array([f["crease"] for _, f in drop_v])
    kn = np.array([f["ncomp"] for _, f in kept_v])
    dn = np.array([f["ncomp"] for _, f in drop_v])
    knv = np.array([f["n"] for _, f in kept_v])
    dnv = np.array([f["n"] for _, f in drop_v])
    print(f"kept  crease[min/med/max]={kc.min():.1f}/{np.median(kc):.1f}/{kc.max():.1f} "
          f"|n|={kn.min():.2f}/{np.median(kn):.2f}/{kn.max():.2f} "
          f"nverts={knv.min()}/{int(np.median(knv))}/{knv.max()}")
    if len(dc):
        print(f"drop  crease[min/med/max]={dc.min():.1f}/{np.median(dc):.1f}/{dc.max():.1f} "
              f"|n|={dn.min():.2f}/{np.median(dn):.2f}/{dn.max():.2f} "
              f"nverts={dnv.min()}/{int(np.median(dnv))}/{dnv.max()}")

# P0 diagnostic round 18: convex-hull-node hypothesis - golden S lines =
# projections of nodes on the part's convex hull (display mesh).
import json, sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

stl_path = ROOT/"tools"/"probe_work"/"imp_stpre.stl"
raw = stl_path.read_bytes()
if raw[:5] == b"solid":
    txt = raw.decode("ascii", "ignore").split()
    tris, i = [], 0
    while i < len(txt):
        if txt[i] == "vertex":
            tris.append((float(txt[i+1]), float(txt[i+2]), float(txt[i+3])))
            i += 4
        else:
            i += 1
    S = np.asarray(tris)*1000.0
else:
    n = int.from_bytes(raw[80:84], "little")
    S = np.zeros((n*3, 3))
    for k in range(n):
        off = 84 + k*50 + 12
        for v in range(3):
            S[k*3+v] = np.frombuffer(raw[off+v*12:off+v*12+12], "<f4")
    S = S.astype(float)*1000.0
Su, inv = np.unique(np.round(S, 6), axis=0, return_inverse=True)

hull = ConvexHull(Su)
hset = np.zeros(len(Su), bool)
for f in hull.simplices:
    hset[f] = True
print(f"nodes={len(Su)} hull nodes={int(hset.sum())}")

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
TOL = 0.02

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(np.round(Su[:, i_ax], 6))
    in_dom = vals[(vals >= gold[0] - 0.05) & (vals <= gold[-1] + 0.05)]
    kept = np.array([np.any(np.abs(gold - v) < TOL) for v in in_dom])
    hull_vals = np.unique(np.round(Su[hset, i_ax], 6))
    pred = np.array([np.any(np.abs(hull_vals - v) < TOL) for v in in_dom])
    agree = int((pred == kept).sum())
    fk = int((pred & ~kept).sum())
    fn = int((~pred & kept).sum())
    print(f"{ax}: hull-pred agree={agree}/{len(in_dom)} false-keep={fk} false-drop={fn}")
    for j, v in enumerate(in_dom):
        if pred[j] != kept[j]:
            n_at = int((np.abs(Su[:, i_ax] - v) < 1e-4).sum())
            print(f"   {v:9.4f} pred={pred[j]} gold={kept[j]} n={n_at}")

# P0 diagnostic round 17: is a projection line DROPPED for axis A when all
# nodes at that coordinate have only incident triangles whose normal is
# parallel to A (|n_A| ~ 0)?  i.e. STpre keeps a coord for axis A only if the
# local surface actually "faces" A.
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
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
T = inv.reshape(-1, 3)
tn = np.zeros((len(T), 3))
for k in range(len(T)):
    a, b, c = Su[T[k, 0]], Su[T[k, 1]], Su[T[k, 2]]
    tn[k] = np.cross(b - a, c - a)
    nrm = np.linalg.norm(tn[k])
    if nrm > 0:
        tn[k] /= nrm
inc = defaultdict(list)
for k in range(len(T)):
    for v in T[k]:
        inc[v].append(k)

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)
TOL = 0.02

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(np.round(Su[:, i_ax], 6))
    in_dom = vals[(vals >= gold[0] - 0.05) & (vals <= gold[-1] + 0.05)]
    kept = np.array([np.any(np.abs(gold - v) < TOL) for v in in_dom])
    # per candidate value: does ANY node at v have an incident tri with |n_ax|>=eps?
    for eps in (0.0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5):
        pred = np.zeros(len(in_dom), bool)
        for j, v in enumerate(in_dom):
            nodes = np.where(np.abs(Su[:, i_ax] - v) < 1e-4)[0]
            ok = False
            for u in nodes:
                if any(abs(tn[k, i_ax]) > eps for k in inc[u]):
                    ok = True
                    break
            pred[j] = ok
        agree = int((pred == kept).sum())
        fp = int((pred & ~kept).sum())   # predicted keep but gold dropped
        fn = int((~pred & kept).sum())   # gold kept but predicted drop
        print(f"{ax} eps={eps:4.2f}: agree={agree}/{len(in_dom)} "
              f"false-keep={fp} false-drop={fn}")
    # detail for best eps: list mismatches
    eps = 0.1
    print(f"  -- {ax} mismatches at eps={eps} --")
    for j, v in enumerate(in_dom):
        pred = any(abs(tn[k, i_ax]) > eps
                   for u in np.where(np.abs(Su[:, i_ax] - v) < 1e-4)[0]
                   for k in inc[u])
        if pred != kept[j]:
            print(f"    {v:9.4f} pred_keep={pred} gold_keep={kept[j]}")

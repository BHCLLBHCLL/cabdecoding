# P0 diagnostic round 19: classify golden anchors against our FLOAT64 facet
# (STpre gridding projects float64 Parasolid tess values; the STL export
# rounds to f32 and merges/splits values -> previous TOL contradictions).
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
P = world(np.asarray(part.points)*1000.0)
print(f"facet nodes={len(P)}")

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    vals = np.unique(P[:, i_ax])          # float64, no rounding
    # distance of every gold line to nearest facet value
    d = np.min(np.abs(vals[None, :] - gold[:, None]), axis=1)
    n_exact = int((d < 1e-9).sum())
    n_near = int(((d >= 1e-9) & (d < 0.02)).sum())
    n_far = int((d >= 0.02).sum())
    print(f"\n=== {ax}: gold={len(gold)} exact={n_exact} near={n_near} far(fill)={n_far}")
    if n_near:
        idx = np.where((d >= 1e-9) & (d < 0.02))[0]
        for i in idx[:10]:
            j = int(np.argmin(np.abs(vals - gold[i])))
            print(f"   near gold {gold[i]:.6f} d={d[i]:.2e} facet={vals[j]:.6f}")
    # kept/dropped classification of facet values (in-domain)
    in_dom = vals[(vals >= gold[0] - 0.05) & (vals <= gold[-1] + 0.05)]
    kept = np.array([np.any(np.abs(gold - v) < 0.02) for v in in_dom])
    print(f"facet in-domain={len(in_dom)} kept={int(kept.sum())} dropped={int((~kept).sum())}")
    # dropped: mirror-pair status + nearest kept distance
    kd = [np.min(np.abs(in_dom[kept] - v)) if kept.any() else -1
          for v in in_dom[~kept]]
    mir = [bool(np.any(np.abs(in_dom[kept] + v) < 1e-6)) for v in in_dom[~kept]]
    print("dropped summary: mirror-of-kept:",
          sum(mir), "/", len(mir),
          " | d_keep<0.02:", sum(1 for x in kd if x < 0.02),
          " 0.02-0.1:", sum(1 for x in kd if 0.02 <= x < 0.1),
          " >=0.1:", sum(1 for x in kd if x >= 0.1))
    print("dropped values (val, d_keep, mirror):")
    for v, k, m in zip(in_dom[~kept], kd, mir):
        print(f"   {v:10.4f}  d={k:7.4f}  mirror={m}")

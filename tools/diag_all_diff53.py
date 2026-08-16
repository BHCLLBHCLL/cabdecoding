# P0 round 53: use STpre's own display mesh (tools/probe_work/
# imp_stpre.stl, 2206 tris) as the node source; test whether the S-line
# set equals ALL vertex projections or a thinned subset, per axis.
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

txt = (ROOT/"tools"/"probe_work"/"imp_stpre.stl").read_text(
    encoding="ascii", errors="replace")
verts = []
for ln in txt.splitlines():
    s = ln.strip()
    if s.startswith("vertex"):
        parts = s.split()
        try:
            verts.append([float(x) for x in parts[1:4]])
        except ValueError:
            pass
V = np.asarray(verts, float) * 1000.0  # STL metres -> mm
# dedupe (STL lists per-triangle vertices)
Vu = np.unique(np.round(V, 6), axis=0)
print(f"stl tri-verts={len(V)} unique={len(Vu)} "
      f"bbox={Vu.min(0).round(3)}..{Vu.max(0).round(3)}")

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_0"]
dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))

def dedupe(vals, lo, hi, tol=1e-3):
    v = np.sort(np.asarray(vals, float))
    v = v[(v >= lo - 0.1) & (v <= hi + 0.1)]
    out = []
    for x in v:
        if not out or abs(x - out[-1]) > tol:
            out.append(float(x))
    return np.asarray(out)

# strict (1e-3) dedupe: raw projection multiplicity before any merge
for i_ax, ax in enumerate("xyz"):
    gold = np.asarray(mk["s_lines"][ax], float)
    cand = dedupe(Vu[:, i_ax], dom[0][i_ax], dom[1][i_ax], tol=1e-3)
    n_extra = sum(1 for v in cand if not np.any(np.abs(gold - v) < 0.1))
    n_miss = sum(1 for v in gold if not np.any(np.abs(cand - v) < 0.1))
    print(f"{ax}: cand={len(cand)} gold={len(gold)} "
          f"extra={n_extra} miss={n_miss}")
    if n_extra:
        ex = [v for v in cand if not np.any(np.abs(gold - v) < 0.1)]
        print("   extras:", [round(v, 3) for v in ex][:30])
    if n_miss:
        ms = [v for v in gold if not np.any(np.abs(cand - v) < 0.1)]
        print("   misses:", [round(v, 3) for v in ms][:30])

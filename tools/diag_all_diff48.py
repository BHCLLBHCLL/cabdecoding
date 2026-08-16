# P0 diagnostic round 48: dump golden all-mode axis lines with spacings,
# marking which rough (S+B) interval each subdivision run belongs to.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_0"]
d = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
rec0 = next(r for r in d["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]
            and r["input"]["vertex_detection"] == 0)

for i_ax, ax in enumerate("xyz"):
    pairs = mk["axes"][ax]
    vals = np.asarray([v for v, m in pairs], float)
    mks = [m for v, m in pairs]
    gold = np.asarray(rec0["output"]["axes"][ax], float)
    print(f"== {ax}: marks n={len(vals)} probe n={len(gold)} "
          f"same={np.allclose(np.sort(vals), np.sort(gold), atol=1e-9)}")
    # identify runs: consecutive N lines between S/B anchors
    out = []
    cur = []
    for v, m in zip(vals, mks):
        if m == "N":
            cur.append(v)
        else:
            if cur:
                out.append(cur)
                cur = []
    if cur:
        out.append(cur)
    print(f"   S/B anchors: {[round(v,3) for v,m in zip(vals,mks) if m!='N'][:40]}")
    print(f"   N runs: {len(out)}")
    for r in out[:40]:
        sp = np.diff(np.asarray(r))
        print(f"     n={len(r):>3} [{r[0]:.3f}..{r[-1]:.3f}] "
              f"spacing={['%.4f' % s for s in sp[:6]]}"
              f"{'...' if len(sp) > 6 else ''}")

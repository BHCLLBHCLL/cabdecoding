# P0 diagnostic round 8: dump probe inputs + full-axis interval analysis.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

g = json.loads((ROOT / "data" / "stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
for r in g["records"]:
    i = r["input"]
    if i["threshold"] == [0.1, 0.1, 0.1] and i["vertex_detection"] in (0, 1):
        print(json.dumps({k: i[k] for k in
                          ("vertex_detection", "standard_length", "threshold",
                           "ratio_in", "ratio_out", "domain_min", "domain_max")},
                         default=str))
        print("  counts:", {a: len(r["output"]["axes"][a]) for a in "xyz"})

# interval analysis on golden axes for vd=all
rec0 = next(r for r in g["records"]
            if r["input"]["threshold"] == [0.1, 0.1, 0.1]
            and r["input"]["vertex_detection"] == 0)
for ax in "xyz":
    a = np.asarray(rec0["output"]["axes"][ax], float)
    d = np.diff(a)
    print(f"\ngolden {ax}: {len(a)} lines, n_int={len(d)}")
    print("  spacings:", " ".join(f"{x:.4f}" for x in d))
    print("  head 8:", " ".join(f"{x:.4f}" for x in a[:8]))
    print("  tail 8:", " ".join(f"{x:.4f}" for x in a[-8:]))

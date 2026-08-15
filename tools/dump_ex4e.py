"""Dump ex4e battery axes for vd0/vd3 with gaps."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]

g = json.loads((ROOT/"data"/"stpre_probe_20260808_ex4e.json").read_text(encoding="utf-8"))
for r in g["records"]:
    if "battery" not in r["name"]: continue
    vd = r["input"]["vertex_detection"]
    if vd not in (0, 3): continue
    for ax in sys.argv[1:]:
        arr = np.array(r["output"]["axes"][ax])
        gaps = np.diff(arr)
        print(f"=== {r['name']} {ax}: {len(arr)} pts ===")
        for i in range(len(arr)):
            gs = f"gap {gaps[i]:.5f}" if i < len(gaps) else ""
            print(f"  [{i:3d}] {arr[i]:12.6f}  {gs}")

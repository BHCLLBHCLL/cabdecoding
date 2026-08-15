"""Dump one axis for a given vd mode with gaps."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]

def main():
    vd = int(sys.argv[1]); ax = sys.argv[2]
    g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
    rec = next(r for r in g["records"] if r["input"]["vertex_detection"] == vd and r["input"]["threshold"]==[0.1,0.1,0.1])
    arr = np.array(rec["output"]["axes"][ax])
    gaps = np.diff(arr)
    print(f"vd{vd} {ax}: {len(arr)} pts")
    for i in range(len(arr)):
        gstr = f"gap {gaps[i]:.5f}" if i < len(gaps) else ""
        print(f"  [{i:3d}] {arr[i]:12.6f}  {gstr}")

if __name__ == "__main__":
    main()

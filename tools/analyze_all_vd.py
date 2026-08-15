"""Compare golden axes across vertex-detection modes."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
    recs = [r for r in g["records"] if r["input"]["threshold"] == [0.1,0.1,0.1]]
    for r in recs:
        vd = r["input"]["vertex_detection"]
        axes = r["output"]["axes"]
        name = {0:"all",1:"rep",2:"axisplane",3:"minmax",4:"none",5:"uniform"}[vd]
        counts = tuple(len(axes[a]) for a in "xyz")
        print(f"== vd{vd} {name:10s} counts {counts}")
        for ax in "xyz":
            arr = np.array(axes[ax])
            gaps = np.diff(arr)
            # find roughly-uniform regions (consecutive equal gaps) and geometric tails
            # print first few and last few gaps
            print(f"   {ax}: first5 gaps {np.round(gaps[:5],4).tolist()} ... last5 gaps {np.round(gaps[-5:],4).tolist()}")

if __name__ == "__main__":
    main()

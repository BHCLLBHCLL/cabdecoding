"""Analyze STpre golden tr03 axes: gaps, vertex planes, region structure."""
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def load_golden():
    g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
    rec = next(r for r in g["records"] if r["name"] == "tr03_imp_vd_0")
    return rec

def main():
    rec = load_golden()
    import ps_facet2_nodes
    sess = ps_facet2_nodes._get_session()
    xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
    tags = sess.expand_to_bodies(sess.receive_xt(xt))
    imp = None
    for t in tags:
        if sess.body_name(t) == "Impeller": imp = t
    if imp is None: imp = tags[0]
    verts = sess.body_vertices(imp) * 1000.0

    for ax in "xyz":
        arr = np.array(rec["output"]["axes"][ax])
        gaps = np.diff(arr)
        vcoords = np.unique(np.round(verts[:, "xyz".index(ax)], 6))
        print(f"===== {ax} axis: {len(arr)} pts, {len(gaps)} intervals =====")
        print(f"  vertex coords ({len(vcoords)}): {np.round(vcoords,4).tolist()}")
        # gaps summary
        print(f"  gap min {gaps.min():.4f} max {gaps.max():.4f}")
        # print first 25 gaps and last 25 gaps
        for i in range(min(25, len(gaps))):
            flag = " V" if any(abs(arr[i]-v)<1e-3 for v in vcoords) else ""
            print(f"    [{i:3d}] {arr[i]:12.5f}  gap {gaps[i]:9.5f}{flag}")
        print(f"    ...")
        for i in range(max(0, len(gaps)-20), len(gaps)):
            flag = " V" if any(abs(arr[i]-v)<1e-3 for v in vcoords) else ""
            print(f"    [{i:3d}] {arr[i]:12.5f}  gap {gaps[i]:9.5f}{flag}")

if __name__ == "__main__":
    main()

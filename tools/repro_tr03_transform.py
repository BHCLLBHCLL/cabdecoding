"""Reproduce tr03 grid WITH the Impeller transform applied."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, ps_facet2_nodes, cab_vtk

def apply_transform(pts_mm, transform_str):
    # transform is column-major 4x4 (unit m); apply to mm coords via cab_vtk (expects m)
    return cab_vtk._apply_transform(np.asarray(pts_mm, dtype=float)/1000.0, transform_str) * 1000.0

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"

def main():
    g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
    rec = next(r for r in g["records"] if r["name"] == "tr03_imp_vd_0")
    gx = np.array(rec["output"]["axes"]["x"]); gy = np.array(rec["output"]["axes"]["y"]); gz = np.array(rec["output"]["axes"]["z"])
    sess = ps_facet2_nodes._get_session()
    xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
    tags = sess.expand_to_bodies(sess.receive_xt(xt))
    imp = None
    for t in tags:
        if sess.body_name(t) == "Impeller": imp = t
    if imp is None: imp = tags[0]
    verts = sess.body_vertices(imp) * 1000.0
    tess = np.asarray(sess.facet_body(imp).points) * 1000.0
    # apply transform (world coords)
    verts_w = apply_transform(verts, TRANSFORM)
    tess_w = apply_transform(tess, TRANSFORM)
    print("world tess bounds:", np.round(tess_w.min(0),4), np.round(tess_w.max(0),4))
    print("world vert bounds:", np.round(verts_w.min(0),4), np.round(verts_w.max(0),4))
    print("world vertex x unique:", np.unique(np.round(verts_w[:,0],6)))
    print("world tess x unique:", np.unique(np.round(tess_w[:,0],6)))

    inp = rec["input"]
    spec = cab_grid.GridSpec(
        unit="mm",
        domain_min=tuple(inp["domain_min"]), domain_max=tuple(inp["domain_max"]),
        vertex_detection="all", method="rough_and_detail",
        standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]),
        geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]),
    )
    part_points = {"Impeller": tess_w}
    part_vertices = {"Impeller": verts_w}
    lo = tess_w.min(0); hi = tess_w.max(0)
    rough, detailed = cab_grid.build_axes(part_points, spec, part_vertices=part_vertices, part_bounds=(lo, hi))
    print("rough x:", np.round(rough["x"],4).tolist())
    print("rough y first/last:", np.round(rough["y"][:8],4).tolist(), np.round(rough["y"][-4:],4).tolist())
    dx = np.array(detailed["x"]); dy = np.array(detailed["y"]); dz = np.array(detailed["z"])
    print("NATIVE counts", len(dx), len(dy), len(dz), " GOLDEN", len(gx), len(gy), len(gz))

if __name__ == "__main__":
    main()

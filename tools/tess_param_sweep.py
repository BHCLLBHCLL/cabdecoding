"""Sweep facet parameters on tr03 Impeller: distinct x/y/z projections vs STpre all-mode counts."""
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = None
for t in tags:
    if sess.body_name(t) == "Impeller": imp = t
if imp is None: imp = tags[0]

# STpre display tess: PKFaces_RenderV3 scales chord tolerance by body size.
# Sweep facet params and report distinct world projections.
for tol, ang in [(1e-4, 12.0), (1e-5, 12.0), (1e-5, 6.0), (1e-6, 6.0),
                 (1e-4, 6.0), (5e-5, 8.0)]:
    tess = sess.facet_body(imp, facet_tol=tol, facet_angle_deg=ang)
    if tess is None:
        print(f"tol={tol} ang={ang}: no tess")
        continue
    pts = cab_vtk._apply_transform(np.asarray(tess.points), TRANSFORM) * 1000.0
    ux = len(np.unique(np.round(pts[:,0], 6)))
    uy = len(np.unique(np.round(pts[:,1], 6)))
    uz = len(np.unique(np.round(pts[:,2], 6)))
    print(f"tol={tol} ang={ang}: n_pts={len(pts):5d}  distinct world x={ux} y={uy} z={uz}")
    if ux > 4:
        print("   x values:", np.sort(np.unique(np.round(pts[:,0],4))).tolist())

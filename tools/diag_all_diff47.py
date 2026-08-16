# P0 diagnostic round 47: tr03 all-node (edge + interior) projections vs
# golden S lines, battery-style double-sided matching.  If the battery
# conclusion (S lines = ALL tess node projections) holds here, the extra
# lines must come from our facet being denser than STpre's meshing mesh.
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk, cab_grid

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
dmin = np.asarray(g["records"][0]["input"]["domain_min"], float)
dmax = np.asarray(g["records"][0]["input"]["domain_max"], float)

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp, want_fin_edge=True)
P = world(np.asarray(part.points)*1000.0)
print(f"nodes={len(P)} edge={int(part.edge_mask.sum())} "
      f"interior={int((~part.edge_mask).sum())}")

mk = marks["tr03_imp_vd_0"]
for i_ax, ax in enumerate("xyz"):
    gold_s = np.asarray(mk["s_lines"][ax], float)
    for label, N in (("edge", P[part.edge_mask]), ("all", P)):
        col = N[:, i_ax]
        col = col[(col >= dmin[i_ax]) & (col <= dmax[i_ax])]
        rough = np.sort(cab_grid._clip_dedupe(
            [float(col.min()), float(col.max())] + [float(v) for v in col],
            dmin[i_ax], dmax[i_ax], tol=0.1))
        rough = np.asarray(rough, float)
        n_extra = sum(1 for v in rough
                      if abs(v-dmin[i_ax]) > 1e-9 and abs(v-dmax[i_ax]) > 1e-9
                      and not np.any(np.abs(gold_s - v) < 0.1))
        n_miss = sum(1 for v in gold_s if not np.any(np.abs(rough - v) < 0.1))
        print(f"{ax} [{label:>5}]: rough={len(rough)} extra={n_extra} miss={n_miss}")
    # per-node: how many nodes hit no S line?
    ds = np.min(np.abs(P[:, i_ax][:, None] - gold_s[None, :]), axis=1)
    in_dom = (P[:, i_ax] >= dmin[i_ax]) & (P[:, i_ax] <= dmax[i_ax])
    print(f"   nodes not matching any S: {int(((ds > 0.1) & in_dom).sum())}/{int(in_dom.sum())}")

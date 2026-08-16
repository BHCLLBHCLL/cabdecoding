# P0 rep: which B-rep vertex projections survive in STpre rep-mode
# axes?  Correlate keep/drop with vertex topology (edge count, face
# types, smooth edges) via Parasolid queries.
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p):
    return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

marks = json.loads((ROOT/"data"/"stpre_tr03_marks.json").read_text(encoding="utf-8"))
mk = marks["tr03_imp_vd_1"]
dom = ((-20.0, -20.0, -20.0), (70.0, 120.0, 120.0))

sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")

# B-rep vertices via session helpers
v = sess.body_vertices(imp)
V = world(np.asarray(v)*1000.0)

# per-vertex topology via raw PK: edges -> faces
mod = ps_facet2_nodes
def vertex_topology(tag):
    """Return (n_edges, n_faces, face_types, n_smooth_edges) for a vertex."""
    try:
        rc, n_edges, edges = mod._pk_call(
            "PK_VERTEX_ask_edges", tag) if hasattr(mod, "_pk_call") else (None,)*3
    except Exception:
        pass
    return None

# fall back: use session API if it exposes vertex edges/faces
attrs = [a for a in dir(sess) if "vert" in a.lower() or "edge" in a.lower()]
print("session vertex/edge helpers:", attrs)

# gold rep S-lines per axis (clip interior like diag79)
gold_s = {}
for i, ax in enumerate("xyz"):
    vals = [x for x in mk["s_lines"][ax]
            if dom[0][i]+0.1 < x < dom[1][i]-0.1]
    gold_s[ax] = np.asarray(vals, float)
    print(f"{ax}: gold rep S-lines = {len(vals)}")

for i, ax in enumerate("xyz"):
    gz = gold_s[ax]
    zz = np.unique(np.round(V[:, i], 6))
    zz = zz[(zz > dom[0][i]+0.1) & (zz < dom[1][i]-0.1)]
    keep = [z for z in zz if np.any(np.abs(gz - z) < 0.1)]
    drop = [z for z in zz if not np.any(np.abs(gz - z) < 0.1)]
    print(f"\n{ax}: B-rep in-domain projections {len(zz)}, "
          f"keep {len(keep)}, drop {len(drop)}")
    print(f"  drop: {[round(z, 3) for z in drop]}")
    # extra gold lines not near any B-rep projection
    extra = [z for z in gz if not np.any(np.abs(zz - z) < 0.1)]
    print(f"  gold-without-B-rep: {[round(z, 3) for z in extra]}")

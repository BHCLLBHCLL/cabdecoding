# Scan pskernel exports for vertex/edge topology query functions.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes

sess = ps_facet2_nodes._get_session()
pk = sess.pk
import ctypes
names = []
for cand in (
        "PK_VERTEX_ask_edges", "PK_EDGE_ask_faces", "PK_EDGE_ask_vertices",
        "PK_EDGE_is_smooth", "PK_EDGE_ask_smoothness",
        "PK_FACE_ask_type", "PK_FACE_ask_edges", "PK_FACE_ask_vertices",
        "PK_VERTEX_ask_faces", "PK_VERTEX_ask_body", "PK_EDGE_ask_body",
        "PK_FACE_ask_vertices_o", "PK_VERTEX_ask_edges_o",
        "PK_EDGE_is_parameterisation", "PK_EDGE_ask_curve",
        "PK_CURVE_ask_type", "PK_EDGE_ask_orientation"):
    try:
        getattr(pk, cand)
        names.append((cand, "OK"))
    except AttributeError:
        names.append((cand, "--"))
for n, s in names:
    print(f"{s} {n}")

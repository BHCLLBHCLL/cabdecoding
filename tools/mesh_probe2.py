"""Sweep o_t_version/create values for PK_MESH_create_from_facets."""
import ctypes as C
from ctypes import CFUNCTYPE, POINTER, Structure, byref, c_int, c_double, c_void_p, cast
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as _ps

sess = _ps._get_session()
pk = sess.pk

CALLS = []
@CFUNCTYPE(c_int, c_int, c_int, c_void_p, c_void_p, c_int, c_void_p, c_void_p)
def facet_reader(is_first, n_verts, coords, normals, n_facets, facet_data, ctx):
    CALLS.append((is_first, n_verts, n_facets))
    return 0  # continue

class _Box(Structure):
    _fields_ = [("x", c_double * 2), ("y", c_double * 2), ("z", c_double * 2)]

class _MeshCreateOpts(Structure):
    _fields_ = [
        ("o_t_version", c_int),
        ("vertices_estimate", c_int),
        ("facet_estimate", c_int),
        ("facet_free", c_void_p),
        ("create", c_int),
        ("have_box", c_int),
        ("box", _Box),
        ("thread_safe", c_int),
    ]

pk.PK_SESSION_set_check_arguments(0)
pk.PK_MESH_create_from_facets.restype = c_int
pk.PK_MESH_create_from_facets.argtypes = [
    c_void_p, c_void_p, POINTER(_MeshCreateOpts), POINTER(c_int)]

for ver in (0, 1, 2, 3, 4, 5):
    for create in (0, 1, 2, 3):
        CALLS.clear()
        opts = _MeshCreateOpts()
        C.memset(byref(opts), 0, C.sizeof(opts))
        opts.o_t_version = ver
        opts.create = create
        mesh = c_int(0)
        try:
            rc = pk.PK_MESH_create_from_facets(facet_reader, None, byref(opts), byref(mesh))
            print(f"ver={ver} create={create}: rc={rc} mesh={mesh.value} calls={CALLS}")
        except Exception as e:
            print(f"ver={ver} create={create}: EXC {e}")

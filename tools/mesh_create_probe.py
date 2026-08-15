"""Canonical V37 PK_MESH_create_from_facets probe (reverse-engineered ABI).

Everything below was derived from pskernel.dll (Parasolid V37) disassembly
plus q-solid.com V35 docs.  The V35 header signature is 4 args:

    PK_MESH_create_from_facets(facet_reader, context, options, mesh)

but several enum VALUES differ from naive guesses:

  * PK_SESSION_set_facet_geometry must be called with PK_facet_geometry_all_c
    = 0x64E7 (no_c = 0x64E6) or the kernel rejects mesh creation with
    error 5237 (frustra byte +0x48 gate).
  * PK_MESH_create_now_c = 0x6784, PK_MESH_create_later_c = 0x6785.
  * facet_reader callback: void cb(context, PK_MESH_facet_t *facets,
    PK_MESH_cb_status_t *status);  facet struct = {int facet_type; int pad;
    union ptr}.  V37 facet_type values: 5 = index block, 6 = vector block,
    1/2/3/4 = other block kinds.  Index block layout:
    {int is_relative_index; int n_vertex_positions; PK_VECTOR_t *vertex_
    positions; PK_VECTOR_t *vertex_normals; int n_facet_indices;
    int *facet_indices}.
  * callback status tokens (NOT 0/1!): 0x187a4 = continue, 0x187a6 = stop,
    0x187a8 = memory_full.

Current state: create_now (0x6784) passes all gates, the reader is invoked
and the block is consumed, but the finalize step returns 5241 ("mesh has no
valid facets").  create_later (0x6785) returns a valid mesh tag (the entity
stores the reader for lazy loading), but PK_MESH_make_bodies on the
unmaterialised mesh returns 907 and the lazy pull (PK_MESH_ask_n_mfacets)
crashes, so the remaining work is materialising the lazy mesh.

Usage: python tools/mesh_create_probe.py
"""
import ctypes as C
from ctypes import CFUNCTYPE, POINTER, Structure, byref, c_int, c_double, c_void_p, sizeof, memset
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as _ps

def log(s):
    print(s, flush=True)

sess = _ps._get_session()
pk = sess.pk
pk.PK_SESSION_set_check_arguments(0)
pk.PK_SESSION_set_facet_geometry.restype = c_int
pk.PK_SESSION_set_facet_geometry.argtypes = [c_int]
log("set_facet_geometry(0x64E7) rc = " + str(pk.PK_SESSION_set_facet_geometry(0x64E7)))

class _Vec(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]

class _IndexBlock(Structure):
    _fields_ = [
        ("is_relative_index", c_int),
        ("n_vertex_positions", c_int),
        ("vertex_positions", POINTER(_Vec)),
        ("vertex_normals", c_void_p),
        ("n_facet_indices", c_int),
        ("facet_indices", POINTER(c_int)),
    ]

class _Facet(Structure):
    _fields_ = [
        ("facet_type", c_int),
        ("_pad", c_int),
        ("index", POINTER(_IndexBlock)),
    ]

class _Box(Structure):
    _fields_ = [("x", c_double * 2), ("y", c_double * 2), ("z", c_double * 2)]

class _Opts(Structure):
    _fields_ = [
        ("o_t_version", c_int),
        ("vertices_estimate", c_int),
        ("facets_estimate", c_int),
        ("facet_free", c_void_p),
        ("create", c_int),
        ("have_box", c_int),
        ("box", _Box),
        ("thread_safe", c_int),
    ]

class _MakeOpts(Structure):
    _fields_ = [
        ("o_t_version", c_int),
        ("vertex_angle", c_double),
        ("allow_disjoint", c_int),
        ("preferred_body_type", c_int),
    ]

tet_v = [_Vec(0,0,0), _Vec(1,0,0), _Vec(0,1,0), _Vec(0,0,1)]
tet_i = [0,1,2, 0,3,1, 1,3,2, 2,3,0]
_v = (_Vec * 4)(*tet_v)
_i = (c_int * 12)(*tet_i)
BLOCK = _IndexBlock(1, 4, C.cast(_v, POINTER(_Vec)), None, 12, C.cast(_i, POINTER(c_int)))

CALLS = []
@CFUNCTYPE(None, c_void_p, POINTER(_Facet), POINTER(c_int))
def facet_reader(context, facets, status):
    CALLS.append(len(CALLS))
    facets[0].facet_type = 5
    facets[0].index = C.pointer(BLOCK)
    status[0] = 0x187a6

pk.PK_MESH_create_from_facets.restype = c_int
pk.PK_MESH_create_from_facets.argtypes = [
    c_void_p, c_void_p, POINTER(_Opts), POINTER(c_int)]
pk.PK_MESH_make_bodies.restype = c_int
pk.PK_MESH_make_bodies.argtypes = [c_int, POINTER(_MakeOpts), POINTER(c_int), POINTER(c_void_p)]
pk.PK_BODY_ask_type.restype = c_int
pk.PK_BODY_ask_type.argtypes = [c_int]

for create in (0x6784, 0x6785):
    CALLS.clear()
    opts = _Opts()
    memset(C.byref(opts), 0, sizeof(opts))
    opts.o_t_version = 2
    opts.vertices_estimate = 4
    opts.facets_estimate = 4
    opts.create = create
    mesh = c_int(0)
    rc = pk.PK_MESH_create_from_facets(facet_reader, None, C.byref(opts), C.byref(mesh))
    log("create=0x%X rc=%d mesh=%s calls=%d" % (create, rc, hex(mesh.value), len(CALLS)))
    if rc == 0 and mesh.value:
        mo = _MakeOpts(1, 4.0, 1, 0)
        n_bodies = c_int(-1)
        bodies = c_void_p()
        r2 = pk.PK_MESH_make_bodies(mesh.value, C.byref(mo), C.byref(n_bodies), C.byref(bodies))
        log("  make_bodies rc=%d n=%s" % (r2, n_bodies.value))
        if r2 == 0 and n_bodies.value > 0:
            arr = C.cast(bodies, POINTER(c_int * n_bodies.value)).contents
            log("  bodies=%s types=%s" % ([hex(t) for t in arr], [pk.PK_BODY_ask_type(t) for t in arr]))
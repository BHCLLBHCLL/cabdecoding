# P0 diagnostic round 27: probe PK_FACE type/surf APIs on one face.
import sys
from ctypes import byref, c_int, c_void_p, POINTER
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as pf

sess = pf._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
faces = sess.body_faces(imp)
pk = sess.pk
f = faces[0]
print(f"face tag={f} class={sess.entity_class(f)}")

def try_call(name, args_sig):
    fn = getattr(pk, name, None)
    if fn is None:
        print(f"{name}: NOT EXPORTED")
        return None
    outs = [c_int(0) for _ in args_sig[1:]]
    fn.restype = c_int
    fn.argtypes = args_sig
    rc = fn(int(f), *[byref(o) for o in outs])
    print(f"{name}: rc={rc} out={[o.value for o in outs]}")
    return [o.value for o in outs]

try_call("PK_FACE_ask_type", [c_int, POINTER(c_int)])
try_call("PK_FACE_ask_surf", [c_int, POINTER(c_int)])

fn = getattr(pk, "PK_SURF_ask_type", None)
if fn is not None:
    s = c_int(0)
    rc1 = pk.PK_FACE_ask_surf(int(f), byref(s))
    t = c_int(-1)
    fn.restype = c_int
    fn.argtypes = [c_int, POINTER(c_int)]
    rc2 = fn(s.value, byref(t))
    print(f"PK_SURF_ask_type: surf={s.value} rc1={rc1} rc2={rc2} type={t.value}")

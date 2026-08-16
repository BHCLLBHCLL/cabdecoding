# P0 round 72: A/B why manual facet2 call gives 960 pts while
# facet_body_stpre gives 1067 with the same six tolerances.
import struct, sys
from pathlib import Path
import numpy as np
from ctypes import string_at, byref, memset, sizeof, c_int, c_void_p, POINTER

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ps_facet2_nodes as mod

sess = mod._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")

part = sess.facet_body_stpre(imp)
P = np.asarray(part.points) * 1000.0
D = float(np.linalg.norm(P.max(0) - P.min(0)))
print(f"stpre mesh: pts={len(part.points)} tris={len(part.triangles)} D={D:.2f}")

def manual(tables_flag, tolf=1.0):
    kw = mod.stpre_recipe(D, angle_deg=mod.STPRE_RECIPE["angle_deg"],
                          ccm=mod.STPRE_RECIPE["ccm"]*tolf,
                          mfw=mod.STPRE_RECIPE["mfw"]*tolf,
                          cct=mod.STPRE_RECIPE["cct"]*tolf,
                          spt=mod.STPRE_RECIPE["spt"]*tolf)
    opts = mod._Facet2OptionsV5()
    memset(byref(opts), 0, sizeof(opts))
    opts.control.o_t_version = 5
    opts.control.max_facet_sides = 3
    for k, v in kw.items():
        setattr(opts.control, "is_" + k, 1)
        setattr(opts.control, k, float(v))
    opts.data_point_idx = 1
    opts.point_vec = 1
    if tables_flag:
        opts.facet_fin = 1
        opts.fin_data = 1
    res = mod._Facet2Result()
    pk = sess.pk
    pk.PK_TOPOL_facet_2.restype = c_int
    pk.PK_TOPOL_facet_2.argtypes = [c_int, POINTER(c_int), c_void_p,
                                    POINTER(mod._Facet2OptionsV5),
                                    POINTER(mod._Facet2Result)]
    rc = pk.PK_TOPOL_facet_2(1, (c_int*1)(int(imp)), None,
                             byref(opts), byref(res))
    tabs = mod.cast(res.tables,
                    mod.POINTER(mod._FacetTable * res.number_of_tables)).contents
    info = {}
    for t in tabs:
        ptr, length = struct.unpack_from("<Qi", string_at(t.ptr, 16))
        info[int(t.fctab)] = length
    return rc, info

for flag in (False, True):
    for tolf in (1.0, 8.0):
        rc, info = manual(flag, tolf)
        print(f"tables_extra={flag} tolf={tolf}: rc={rc} "
              f"point_vec={info.get(mod.FCTAB_POINT_VEC)} "
              f"facet_fin={info.get(mod.FCTAB_FACET_FIN)} "
              f"fin_data={info.get(mod.FCTAB_FIN_DATA)}")

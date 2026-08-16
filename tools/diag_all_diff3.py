# P0 diagnostic round 3: monkeypatch ceil subdivision x dedupe-tolerance sweep,
# per-line equality vs golden for all 6 tr03 vd modes.
import json, sys, math
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_grid, stpre_rules, ps_facet2_nodes, cab_vtk

TRANSFORM = "1,0,0,0,0,1,0,0,0,0,1,0,-0.0225,-0.0475,-0.0475,1"
def world(p): return cab_vtk._apply_transform(np.asarray(p, float)/1000.0, TRANSFORM)*1000.0

g = json.loads((ROOT/"data"/"stpre_probe_20260808_tr03.json").read_text(encoding="utf-8"))
sess = ps_facet2_nodes._get_session()
xt = (ROOT/"tests"/"tr03"/"_tr03_all.x_t").read_bytes()
tags = sess.expand_to_bodies(sess.receive_xt(xt))
imp = next(t for t in tags if sess.body_name(t) == "Impeller")
part = sess.facet_body_stpre(imp)
tess_w = world(np.asarray(part.points)*1000.0)
v = sess.body_vertices(imp)
verts_w = world(np.asarray(v)*1000.0)
lo, hi = tess_w.min(0), tess_w.max(0)

base_recs = {r["input"]["vertex_detection"]: r for r in g["records"]
             if r["input"]["threshold"] == [0.1, 0.1, 0.1]}

_orig_trunc = stpre_rules._trunc_round
_orig_clip = cab_grid._clip_dedupe

def run(det, tol_mode):
    rec = base_recs[{"all": 0, "representative": 1, "axis_plane": 2,
                     "minmax": 3, "not_considered": 4, "uniform": 5}[det]]
    inp = rec["input"]
    spec = cab_grid.GridSpec(unit="mm", domain_min=tuple(inp["domain_min"]),
        domain_max=tuple(inp["domain_max"]), vertex_detection=det,
        method="rough_and_detail", standard_length=tuple(inp["standard_length"]),
        threshold_length=tuple(inp["threshold"]), geometric_ratio=tuple(inp["ratio_in"]),
        geometric_ratio_external=tuple(inp["ratio_out"]))
    _, detailed = cab_grid.build_axes({"Impeller": tess_w}, spec,
                                      part_vertices={"Impeller": verts_w},
                                      part_bounds=(lo, hi))
    ok = []
    for ax in "xyz":
        gold = np.asarray(rec["output"]["axes"][ax], float)
        nat = np.asarray(detailed[ax], float)
        if len(gold) != len(nat):
            ok.append(f"{ax}:{len(nat)}!={len(gold)}")
        elif np.max(np.abs(np.sort(nat) - np.sort(gold))) > 2e-4:
            ok.append(f"{ax}:vals~")
        else:
            ok.append(f"{ax}:OK")
    return ok

# patch 1: ceil subdivision
stpre_rules._trunc_round = lambda x: max(1, math.ceil(x - 1e-9))
try:
    print("== ceil subdivision, default dedupe (thr=0.1) ==")
    for det in ("all", "representative", "minmax", "uniform"):
        print(f"  {det}: {run(det, None)}")
finally:
    stpre_rules._trunc_round = _orig_trunc

# patch 2: force _clip_dedupe tol sweep (with ceil)
def make_clip(force_tol):
    def clip(vals, lo, hi, tol=1e-9):
        return _orig_clip(vals, lo, hi, tol=force_tol)
    return clip

stpre_rules._trunc_round = lambda x: max(1, math.ceil(x - 1e-9))
try:
    for tol in (0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09):
        cab_grid._clip_dedupe = make_clip(tol)
        res = run("all", tol)
        print(f"== ceil + dedupe {tol}: all -> {res}")
        if all(r.endswith("OK") for r in res):
            for det in ("representative", "minmax", "uniform"):
                print(f"   {det}: {run(det, tol)}")
finally:
    stpre_rules._trunc_round = _orig_trunc
    cab_grid._clip_dedupe = _orig_clip

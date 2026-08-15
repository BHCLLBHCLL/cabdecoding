# Compare candidate vertex sources (B-rep, facet_2 tables, GO render)
# against STpre's tr03 S-line projections (from probe_tr03_marks.py).
import sys, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
marks = json.loads((workdir / 'tr03_marks.json').read_text(encoding='utf-8'))

a = CabArchive.parse((ROOT / 'tests' / 'tr03.cab').read_bytes())
a.fill_member_data()
xt = next(m.data for m in a.members if m.name.endswith('.x_t'))
d = next(m.data for m in a.members
         if m.name.endswith('.xml') and not m.name.startswith('_'))
root = parse_stpre(d).root
# Impeller transform (metres) -> world mm: local*1000 + t*1000
tr = (-0.0225, -0.0475, -0.0475)

import ps_facet2_nodes
sess = ps_facet2_nodes._get_session()
tags = sess.receive_xt(xt)
print('bodies:', [(t, sess.body_name(t)) for t in tags])
imp = None
for t in tags:
    if sess.body_name(t) == 'Impeller':
        imp = t
print('impeller tag:', imp)

def world_z(pts_m):
    p = np.asarray(pts_m, float)
    if len(p) == 0:
        return np.array([])
    return p[:, 2] * 1000.0 + tr[2] * 1000.0

def world_xyz(pts_m):
    p = np.asarray(pts_m, float)
    return p * 1000.0 + np.array(tr) * 1000.0

sources = {}
# B-rep vertices
bv = sess.body_vertices(imp)
print('B-rep vertices:', None if bv is None else len(bv))
sources['brep'] = world_xyz(bv) if bv is not None else None

# facet_2 at default tolerance
for tol, ang in ((1e-4, 12.0), (1e-3, 12.0), (1e-5, 12.0), (1e-4, 30.0),
                 (1e-4, 5.0), (5e-4, 12.0)):
    try:
        tess = sess.facet2(imp, facet_tol=tol, facet_angle_deg=ang)
        n = 0 if tess is None else len(tess.points)
        key = f'facet2_tol{tol:g}_ang{ang:g}'
        sources[key] = world_xyz(tess.points) if n else None
        print(key, 'points:', n)
    except Exception as exc:
        print('facet2', tol, ang, 'EXC', str(exc)[:100])

# GO render at default tolerance
for tol, ang in ((1e-4, 12.0), (1e-3, 12.0), (1e-5, 12.0)):
    try:
        tess = sess.facet_body(imp, facet_tol=tol, facet_angle_deg=ang)
        n = 0 if tess is None else len(tess.points)
        key = f'go_tol{tol:g}_ang{ang:g}'
        sources[key] = world_xyz(tess.points) if n else None
        print(key, 'points:', n)
    except Exception as exc:
        print('go', tol, ang, 'EXC', str(exc)[:100])

results = {}
for case, entry in marks.items():
    sl = entry['s_lines']
    results[case] = {}
    for ax in ('x', 'y', 'z'):
        target = np.asarray(sorted(sl.get(ax, [])), float)
        results[case][ax] = {'n_stpre': len(target),
                             'stpre': [round(v, 4) for v in target]}
        for key, pts in sources.items():
            if pts is None or len(pts) == 0:
                continue
            proj = np.unique(np.round(pts[:, 'xyz'.index(ax)], 4))
            inter = sorted(set(proj.tolist()) & set(
                [round(v, 4) for v in target]))
            results[case][ax].setdefault('matches', {})[key] = {
                'n_proj': len(proj), 'n_hit': len(inter),
                'missing': [round(v, 4) for v in target
                            if round(v, 4) not in set(proj.tolist())][:12],
                'extra': [v for v in proj.tolist()
                          if v not in set([round(t, 4) for t in target])][:12],
            }
for case, entry in results.items():
    print('=====', case)
    for ax in 'xyz':
        e = entry[ax]
        print(' axis', ax, 'STpre S n =', e['n_stpre'])
        for key, mm in sorted(e.get('matches', {}).items()):
            print('   ', key, 'proj', mm['n_proj'], 'hit', mm['n_hit'])
p = workdir / 'tr03_vertex_compare.json'
p.write_text(json.dumps(results, indent=2), encoding='utf-8')
print('wrote', p)
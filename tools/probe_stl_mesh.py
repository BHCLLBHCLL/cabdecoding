# Save STpre's own display mesh (SaveStlFile) for the impeller and
# compare its vertices with the vd_0 S-lines.
import sys, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from stpre_probe import tr03_vd_cases, _fresh_model, _apply_case

workdir = ROOT / 'tools' / 'probe_work'
case = next(c for c in tr03_vd_cases() if c.name == 'tr03_imp_vd_0')
model, archive = _fresh_model(case.base)
_apply_case(model, case, archive)
src = workdir / 'stl_in.cab'
cab_stpre_api.build_relay_cab(model, archive, src)
session = cab_stpre_api.STpreSession()
if not session.ensure_open(src):
    print('open failed', cab_stpre_api.last_error)
else:
    try:
        imp = session.model('Impeller')
        stl_path = str(workdir / 'imp_stpre.stl')
        rc = imp.SaveStlFile(stl_path) if hasattr(imp, 'SaveStlFile') else None
        print('SaveStlFile rc:', rc)
    except Exception as exc:
        print('EXC', type(exc).__name__, str(exc)[:200])
    session.close()

# parse the STL and compare
p = workdir / 'imp_stpre.stl'
if p.exists():
    txt = p.read_text(encoding='ascii', errors='replace')
    verts = []
    lines = txt.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith('vertex'):
            parts = ln.strip().split()
            if len(parts) >= 4:
                try:
                    verts.append([float(x) for x in parts[1:4]])
                except ValueError:
                    pass
    v = np.asarray(verts, float)
    print('stl vertices:', len(v))
    if len(v):
        # STL in mm already (STpre exports mm?)
        marks = json.loads((workdir / 'tr03_marks.json').read_text(
            encoding='utf-8'))
        v0 = marks['tr03_imp_vd_0']['s_lines']
        for ax in 'xyz':
            t = np.asarray(sorted(v0[ax]), float)
            proj = v[:, 'xyz'.index(ax)]
            hits = sum(1 for val in t if np.min(np.abs(proj - val)) <= 1e-3)
            print(f'{ax}: {hits}/{len(t)} covered, '
                  f'range {proj.min():.4f}..{proj.max():.4f} '
                  f'target {t.min():.4f}..{t.max():.4f}')

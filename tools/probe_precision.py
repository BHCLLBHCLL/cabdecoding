# Does the project <precision> control STpre's display mesh?
# Relay tr03 with precision 1..3, SaveStlFile, compare triangle counts
# and x-plane projections.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from stpre_probe import tr03_vd_cases, _fresh_model, _apply_case

workdir = ROOT / 'tools' / 'probe_work'
case = next(c for c in tr03_vd_cases() if c.name == 'tr03_imp_vd_0')
for prec in (0, 1, 2, 3, 4):
    model, archive = _fresh_model(case.base)
    _apply_case(model, case, archive)
    # set <project><precision>
    import xml.etree.ElementTree as ET
    proj = model.project
    if proj is None:
        continue
    el = proj.find('precision')
    if el is None:
        el = ET.SubElement(proj, 'precision')
    el.text = f' {prec} '
    src = workdir / f'prec{prec}_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print(prec, 'relay failed')
        continue
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print(prec, 'open failed', cab_stpre_api.last_error)
        continue
    try:
        imp = session.model('Impeller')
        stl = workdir / f'imp_prec{prec}.stl'
        rc = imp.SaveStlFile(str(stl)) if imp is not None else None
        if stl.exists():
            txt = stl.read_text(encoding='ascii', errors='replace')
            n_tris = sum(1 for ln in txt.splitlines()
                         if 'facet normal' in ln)
            xs = set()
            for ln in txt.splitlines():
                if ln.strip().startswith('vertex'):
                    parts = ln.strip().split()
                    if len(parts) >= 4:
                        try:
                            xs.add(round(float(parts[1]), 4))
                        except ValueError:
                            pass
            print(f'prec={prec}: tris={n_tris} xproj={sorted(xs)}')
        else:
            print(prec, 'no stl, rc=', rc)
    except Exception as exc:
        print(prec, 'EXC', type(exc).__name__, str(exc)[:120])
    finally:
        session.close()

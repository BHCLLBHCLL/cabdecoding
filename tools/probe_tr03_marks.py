# Re-run tr03 vertex-detection cases live against STpre COM and capture
# per-axis (value, mark) pairs incl. S lines (vertex projections).
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import stpre_probe
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)
cases = [c for c in stpre_probe.tr03_vd_cases()
         if c.name in ('tr03_imp_vd_0', 'tr03_imp_vd_1')]
out = {}
for c in cases:
    rec = stpre_probe.run_case(c, workdir)
    print(c.name, 'ok=', rec.get('ok'), 'err=', rec.get('error'))
    if not rec.get('ok'):
        continue
    cab = workdir / f'{c.name}_out.cab'
    a = CabArchive.parse(cab.read_bytes())
    a.fill_member_data()
    d = next(m.data for m in a.members
             if m.name.endswith('.xml') and not m.name.startswith('_'))
    root = parse_stpre(d).root
    mb = root.find('mesh_block')
    entry = {'name': c.name, 'axes': {}, 's_lines': {}}
    for ax in ('x', 'y', 'z'):
        el = mb.find(ax)
        if el is None:
            continue
        marks = []
        for g in el:
            if g.tag != 'g' or not g.text:
                continue
            parts = g.text.strip().split(',')
            try:
                v = float(parts[0].strip())
            except ValueError:
                continue
            mk = parts[1].strip().upper() if len(parts) > 1 else ''
            marks.append((v, mk))
        entry['axes'][ax] = marks
        entry['s_lines'][ax] = [v for v, mk in marks if mk == 'S']
    out[c.name] = entry
    print('   x S:', [round(v, 4) for v in entry['s_lines']['x']])
    print('   y S:', [round(v, 4) for v in entry['s_lines']['y']])
    print('   z S:', [round(v, 4) for v in entry['s_lines']['z']])
    print('   axis counts:', {a: len(v) for a, v in entry['axes'].items()})
p = workdir / 'tr03_marks.json'
p.write_text(json.dumps(out, indent=2), encoding='utf-8')
print('wrote', p)

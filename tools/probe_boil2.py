import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
src = workdir / 'boil_in.cab'
session = cab_stpre_api.STpreSession()
if not session.ensure_open(src):
    print('open failed', cab_stpre_api.last_error)
    sys.exit(1)
doc = session.doc
raw = session._doc
from cab_stpre_api import _invoke

print('SetAnalysisType boil_condensation:',
      doc.SetAnalysisType('boil_condensation', 'T'))
KEYS = [
    ('phase_boil', 'T'),
    ('phase_boil_latent_heat', '2256'),
    ('phase_gas_temp', '100'),
    ('phase_satulate_temp', '100'),
    ('phase_solid_temp', '0'),
    ('phase_gas_density', '0.6'),
]
for k, v in KEYS:
    try:
        rc = _invoke(raw, 'SetSolverParam', k, v)
        print('SetSolverParam', k, v, '->', rc)
    except Exception as e:
        print('SetSolverParam', k, 'EXC', str(e)[:100])

out = workdir / 'boil_params.cab'
print('save rc:', session.save(out))


def xml_bytes(path):
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    return None


def walk(el, prefix):
    out = []
    for c in el:
        key = prefix + '/' + c.tag
        text = (c.text or '').strip()
        out.append((key, text, len(c) > 0))
        out.extend(walk(c, key))
    return out


base = xml_bytes(workdir / 'boil_base.cab')
cur = xml_bytes(out)
rb = parse_stpre(base).root
rc = parse_stpre(cur).root
wb = {k: (t, n) for k, t, n in walk(rb, '')}
wc = {k: (t, n) for k, t, n in walk(rc, '')}
print('== diffs ==')
for k in sorted(set(wb) | set(wc)):
    b, c = wb.get(k), wc.get(k)
    if b != c:
        print(k, ':', b, '->', c)

# Full expression flow with type='script'.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_stpre_api import STpreValue
from stpre_probe import _fresh_model, _apply_case, ProbeCase

workdir = ROOT / 'tools' / 'probe_work'
model, archive = _fresh_model('box')
_apply_case(model, ProbeCase(name='expr4'), archive)
src = workdir / 'expr4_in.cab'
cab_stpre_api.build_relay_cab(model, archive, src)
session = cab_stpre_api.STpreSession()
if not session.ensure_open(src):
    print('open failed', cab_stpre_api.last_error)
else:
    doc = session.doc
    try:
        ex = doc.call('CreateExpression', 'E1', 'script')
        print('CreateExpression:', ex is not None)
        print('SetText rc:', cab_stpre_api._invoke(ex, 'SetText',
                                                  '1000*sin(2*pi*t)'))
        print('Get:', cab_stpre_api._invoke(ex, 'Get'))
        raw = doc.call('SetHeatSource', 'HeatExpr2', 0.0, 'W/m3')
        val = STpreValue(raw)
        print('SetExpression rc:', val.call('SetExpression', 'HSOC', 'E1'))
        out = workdir / 'expr4_out.cab'
        print('save rc:', session.save(out))
    except Exception as exc:
        print('EXC', type(exc).__name__, str(exc)[:200])
    finally:
        session.close()

from cab_container import CabArchive
from cabxml import parse_stpre
import xml.etree.ElementTree as ET
a = CabArchive.parse((workdir / 'expr4_out.cab').read_bytes())
a.fill_member_data()
d = next(m.data for m in a.members
         if m.name.endswith('.xml') and not m.name.startswith('_'))
root = parse_stpre(d).root
for el in root.iter():
    if el.tag in ('value', 'expression', 'function', 'user_data', 'script',
                  'series', 'formatted_script'):
        s = ET.tostring(el, encoding='unicode').strip()
        print('---', el.tag, '---')
        print(s[:800])

# Probe: what XML does STpre write for a heat source with an expression
# (function) value?  Create heat source + SetExpression, save, dump.
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from stpre_probe import _fresh_model, _apply_case
from stpre_probe import ProbeCase

workdir = ROOT / 'tools' / 'probe_work'
case = ProbeCase(name='expr_probe')
model, archive = _fresh_model('box')
_apply_case(model, case, archive)
src = workdir / 'expr_in.cab'
cab_stpre_api.build_relay_cab(model, archive, src)
session = cab_stpre_api.STpreSession()
if not session.ensure_open(src):
    print('open failed', cab_stpre_api.last_error)
else:
    try:
        doc = session.doc
        # create a heat source condition on the domain
        from cab_stpre_api import STpreValue
        raw = doc.call('SetHeatSource', 'HeatExpr1', 0.0, 'W/m3')
        print('SetHeatSource ->', raw is not None)
        val = STpreValue(raw)
        # attach an expression to its 'power' parameter
        rc = val.SetExpression('source', '1000*sin(2*pi*t)')
        print('SetExpression rc:', rc)
        try:
            rc2 = val.SetExpression('power', '2000')
            print('SetExpression(power) rc:', rc2)
        except Exception as exc:
            print('power EXC', type(exc).__name__, str(exc)[:120])
        out = workdir / 'expr_out.cab'
        print('save rc:', session.save(out))
    except Exception as exc:
        print('EXC', type(exc).__name__, str(exc)[:200])
    finally:
        session.close()

# dump the values + expressions from the saved cab
from cab_container import CabArchive
from cabxml import parse_stpre
import xml.etree.ElementTree as ET
a = CabArchive.parse((workdir / 'expr_out.cab').read_bytes())
a.fill_member_data()
d = next(m.data for m in a.members
         if m.name.endswith('.xml') and not m.name.startswith('_'))
root = parse_stpre(d).root
for el in root.iter():
    if el.tag in ('value', 'expression', 'function', 'script', 'series'):
        s = ET.tostring(el, encoding='unicode').strip()
        print('---', el.tag, '---')
        print(s[:600])
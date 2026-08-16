# Signature sweep for the documented-but-unwrapped STpre COM methods.
# Each candidate is called with several argument shapes until one does not
# raise; the winning call is saved and the XML diff recorded.
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)


def xml_member(path):
    arch = CabArchive.parse(Path(path).read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    return None


def walk(el, prefix):
    out = []
    for c in el:
        key = prefix + '/' + c.tag
        out.append((key, (c.text or '').strip(), len(c) > 0))
        out.extend(walk(c, key))
    return out


CANDIDATES = [
    ('SetSolverParam', [('steady_convergence', '1e-4'), ('cycle', '100')]),
    ('GetSolverParam', [('steady_convergence',), ()]),
    ('SetEvaporationParam', [('liquid_temp', '100'), ('liquid_temp', '100', 'C')]),
    ('GetEvaporationParam', [('liquid_temp',), ()]),
    ('SetSolidMeltParam', [('liquid_temp', '100'), ('solidus', '100')]),
    ('GetSolidMeltParam', [('liquid_temp',), ()]),
    ('SetPhaseParam', [('volume_correction', 'T'), ('key', 'T')]),
    ('GetPhaseParam', [('volume_correction',), ()]),
    ('SetPorousHeatTransfer', [('Xmin', 'conduction', '10'), ('Xmin', '0.5'), ('Xmin', 'HTRC', '10')]),
    ('GetPorousHeatTransfer', [('Xmin',), ()]),
    ('SetCycle', [('transient', '100'), ('1', '100')]),
    ('GetCycle', [(), ]),
    ('SetUserEntity', [('key1', '42'), ('key1', '42', 'BASE')]),
    ('GetUserEntity', [('key1',), ()]),
    ('GetScript', [('E1',), ()]),
    ('GetExpression', [('E1',), ()]),
    ('GetReferencedExpression', [('E1',), ()]),
    ('SetUserFunction', [('F1', 'x+y'), ('F1', 'x+y', 'script')]),
    ('GetUserFunction', [('F1',), ()]),
    ('SetUserData', [('D1', '3.5'), ('D1', '3.5', 'm')]),
    ('GetUserData', [('D1',), ()]),
]


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'com_sig_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    raw = session._doc
    base_out = workdir / 'com_sig_base.cab'
    session.save(base_out)
    base = {k: (t, n) for k, t, n in walk(parse_stpre(xml_member(base_out)).root, '')}
    results = {}
    for name, shapes in CANDIDATES:
        rec = {}
        for shape in shapes:
            try:
                val = cab_stpre_api._invoke(raw, name, *shape)
                rec['win_shape'] = list(shape)
                rec['val'] = str(val)[:120]
                break
            except TypeError:
                continue
            except Exception as e:
                rec['shape_' + str(len(shape))] = 'EXC:' + str(e)[:90]
        if 'win_shape' not in rec:
            rec['all_failed'] = True
        out = workdir / f'com_sig_{name}.cab'
        rec['save_rc'] = session.save(out)
        try:
            cur = {k: (t, n) for k, t, n in walk(parse_stpre(xml_member(out)).root, '')}
            diff = {k: (base.get(k), cur.get(k))
                    for k in set(base) | set(cur) if base.get(k) != cur.get(k)}
            rec['diff'] = dict(list(diff.items())[:8])
        except Exception as e:
            rec['diff_exc'] = str(e)[:90]
        results[name] = rec
        print(name, '->', json.dumps(rec, ensure_ascii=False)[:300])
    (workdir / 'com_sig_probe.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved com_sig_probe.json')


if __name__ == '__main__':
    main()

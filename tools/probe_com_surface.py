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


CALLS = [
    ('SetPorousHeatTransfer', ('region', 'Xmin', '0.5')),
    ('GetPorous', ()),
    ('GetPhase', ()),
    ('GetPhaseDiagram', ()),
    ('GetSolidMeltParam', ('key',)),
    ('SetSolidMeltParam', ('key', '100')),
    ('GetEvaporationParam', ('liquid_temp',)),
    ('SetEvaporationParam', ('liquid_temp', '100')),
    ('SetSolverParam', ('steady_convergence', '1e-4')),
    ('GetCycle', ()),
    ('SetCycle', ('100', '2')),
    ('GetUserEntity', ('key1',)),
    ('GetScriptArray', ()),
    ('GetExpressionArray', ()),
    ('GetDust', ()),
    ('GetParticle', ()),
    ('GetReaction', ()),
]


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'com_surf_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    raw = session._doc
    base_out = workdir / 'com_surf_base.cab'
    session.save(base_out)
    base = {k: (t, n) for k, t, n in walk(parse_stpre(xml_member(base_out)).root, '')}
    results = {}
    for name, args in CALLS:
        rec = {}
        for target, label in ((doc, 'typed'), (raw, 'raw')):
            try:
                fn = getattr(target, name)
                try:
                    val = fn(*args)
                    rec[label] = str(val)[:120]
                except TypeError:
                    rec[label] = 'TYPE_ERR'
            except Exception as e:
                rec[label] = 'EXC:' + str(e)[:100]
        out = workdir / f'com_surf_{name}.cab'
        rec['save_rc'] = session.save(out)
        try:
            cur = {k: (t, n) for k, t, n in walk(parse_stpre(xml_member(out)).root, '')}
            diff = {k: (base.get(k), cur.get(k))
                    for k in set(base) | set(cur) if base.get(k) != cur.get(k)}
            rec['diff'] = dict(list(diff.items())[:8])
        except Exception as e:
            rec['diff_exc'] = str(e)[:100]
        results[name] = rec
        print(name, '->', json.dumps(rec, ensure_ascii=False)[:280])
    (workdir / 'com_surface_probe.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved com_surface_probe.json')


if __name__ == '__main__':
    main()

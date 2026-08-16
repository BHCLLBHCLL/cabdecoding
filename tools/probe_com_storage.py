# Storage deep-evidence for the R11-wrapped COM methods: enable the
# parent analyses, call the methods with valid keys, save, and diff both
# the main XML and the property member.
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre, parse_property

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)


def members(path):
    arch = CabArchive.parse(Path(path).read_bytes())
    arch.fill_member_data()
    return {m.name: m.data for m in arch.members if m.data}


def xml_name(ms):
    return next(n for n in ms if n.endswith('.xml') and not n.startswith('_'))


def prop_name(ms):
    return next((n for n in ms if n.endswith('_property.xml')), None)


def walk(el, prefix):
    out = []
    for c in el:
        key = prefix + '/' + c.tag
        out.append((key, (c.text or '').strip(), len(c) > 0))
        out.extend(walk(c, key))
    return out


def snap(path):
    ms = members(path)
    out = {}
    xn = xml_name(ms)
    out['xml'] = {k: (t, n) for k, t, n in walk(parse_stpre(ms[xn]).root, '')}
    pn = prop_name(ms)
    if pn:
        out['prop'] = {k: (t, n) for k, t, n in
                       walk(parse_property(ms[pn]).root, '')}
    return out


def diff(a, b):
    out = {}
    for sect in ('xml', 'prop'):
        if sect not in a or sect not in b:
            continue
        for k in set(a[sect]) | set(b[sect]):
            if a[sect].get(k) != b[sect].get(k):
                out[f'{sect}{k}'] = (a[sect].get(k), b[sect].get(k))
    return out


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'com_stor_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    base_out = workdir / 'com_stor_base.cab'
    session.save(base_out)
    base = snap(base_out)

    # enable parents
    for kind in ('heat', 'free_surface', 'evap', 'solid_melt'):
        try:
            print('enable', kind, doc.SetAnalysisType(kind, 'T'))
        except Exception as e:
            print('enable', kind, 'EXC', str(e)[:60])

    steps = [
        ('SetEvaporationParam_liquid_temp',
         lambda: doc.SetEvaporationParam('liquid_temp', '100')),
        ('SetEvaporationParam_latent_heat',
         lambda: doc.SetEvaporationParam('latent_heat', '2256')),
        ('SetSolidMeltParam_liquid_temp',
         lambda: doc.SetSolidMeltParam('liquid_temp', '120')),
        ('SetUserEntity_key1',
         lambda: doc.SetUserEntity('key1', '42')),
        ('SetCycle_transient',
         lambda: doc.SetCycle('transient', '100')),
        ('SetSolverParam_steady_convergence',
         lambda: doc.SetSolverParam('steady_convergence', '1e-4')),
    ]
    results = {}
    cur = base
    for name, fn in steps:
        try:
            rc = fn()
        except Exception as e:
            results[name] = {'exc': str(e)[:100]}
            print(name, 'EXC', str(e)[:80])
            continue
        out = workdir / f'com_stor_{name}.cab'
        session.save(out)
        snap_now = snap(out)
        results[name] = {'rc': rc, 'diff': diff(cur, snap_now)}
        cur = snap_now
        print(name, '->', json.dumps(results[name], ensure_ascii=False)[:260])
    (workdir / 'com_storage_probe.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved')


if __name__ == '__main__':
    main()

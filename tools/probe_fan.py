# R3.5a probe: CreateFanModel storage format on a fresh box project.
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


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'fan_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    base_out = workdir / 'fan_base.cab'
    session.save(base_out)
    base = {k: (t, n) for k, t, n in walk(parse_stpre(xml_member(base_out)).root, '')}
    results = {}
    for label, call in [
        ('fan_2arg', lambda: doc.CreateFanModel('Fan1', (0, 0, 0), (20, 20, 20))),
        ('axialfan_2arg', lambda: doc.CreateAxialFanModel('Fan2', (30, 0, 0), (20, 20, 20))),
        ('blowerfan_2arg', lambda: doc.CreateBlowerFanModel('Fan3', (60, 0, 0), (20, 20, 20))),
    ]:
        try:
            val = call()
            rec = {'rc': str(val)[:80]}
        except TypeError as e:
            rec = {'type_err': str(e)[:120]}
        except Exception as e:
            rec = {'exc': str(e)[:120]}
        out = workdir / f'fan_{label}.cab'
        rec['save_rc'] = session.save(out)
        try:
            cur = {k: (t, n) for k, t, n in walk(parse_stpre(xml_member(out)).root, '')}
            diff = {k: (base.get(k), cur.get(k))
                    for k in set(base) | set(cur) if base.get(k) != cur.get(k)}
            rec['diff'] = dict(list(diff.items())[:14])
        except Exception as e:
            rec['diff_exc'] = str(e)[:100]
        results[label] = rec
        print(label, '->', json.dumps(rec, ensure_ascii=False)[:400])
    (workdir / 'fan_probe.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved')


if __name__ == '__main__':
    main()

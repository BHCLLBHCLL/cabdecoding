# Probe STpre COM SetAnalysisType with the boil kind strings found in
# STpreBase (boil_condensation = Phase change, boil_lee = Bubbles).
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)

KINDS = ['boil_condensation', 'boil_lee', 'boil', 'boiling',
         'condensation', 'phase_change']


def sections(data: bytes) -> dict:
    root = parse_stpre(data).root
    out = {}
    for tag in ('analysis_set', 'analysis_etc', 'condition_wizard', 'project'):
        el = root.find(tag)
        if el is None:
            out[tag] = None
            continue
        out[tag] = {c.tag: (c.text or '').strip() for c in el}
    return out


def xml_member_data(path: Path) -> bytes:
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    raise RuntimeError('no xml member')


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'boil_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    base_out = workdir / 'boil_base.cab'
    session.save(base_out)
    baseline = sections(xml_member_data(base_out))
    results = {}
    for kind in KINDS:
        rec = {}
        try:
            rec['get_val'] = doc.GetAnalysisType(kind)
        except Exception as exc:
            rec['get_exc'] = str(exc)[:120]
        try:
            rec['set_rc'] = doc.SetAnalysisType(kind, 'T')
            rec['get_after'] = doc.GetAnalysisType(kind)
        except Exception as exc:
            rec['set_exc'] = str(exc)[:120]
        out = workdir / f'boil_{kind}.cab'
        rec['save_rc'] = session.save(out)
        try:
            cur = sections(xml_member_data(out))
            diff = {}
            for tag in ('analysis_set', 'analysis_etc'):
                if baseline.get(tag) and cur.get(tag):
                    keys = set(baseline[tag]) | set(cur[tag])
                    for k in keys:
                        b, c = baseline[tag].get(k), cur[tag].get(k)
                        if b != c:
                            diff[f'{tag}.{k}'] = (b, c)
            rec['diff'] = diff
        except Exception as exc:
            rec['diff_exc'] = str(exc)[:120]
        results[kind] = rec
        print(kind, '->', json.dumps(rec, ensure_ascii=False)[:600])
    (workdir / 'boil_probe.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved boil_probe.json')


if __name__ == '__main__':
    main()

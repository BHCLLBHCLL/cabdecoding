# Probe STpre COM Get/SetAnalysisType with the documented kind strings.
# Sets flag 'T' per kind, saves, and diffs the analysis_set section.
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)

KINDS = [
    'aircon', 'move_body', 'move_body_t', 'plant_resistance',
    'marangoni', 'topopt', 'pcm', 'solid_melt', 'reaction', 'solar',
    'lamp', 'ecurrent', 'joule', 'es_field', 'es_field_initial',
    'vof', 'mars', 'mars1', 'humidity', 'diffusion', 'Particle',
    'porous_media', 'dem', 'printer_model', 'periodic', 'mapping',
    'luminance', 'mrt', 'gslr', 'ventilation',
]

def sections(data: bytes) -> dict:
    root = parse_stpre(data).root
    out = {}
    for tag in ('analysis_set', 'condition_wizard', 'project'):
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
    src = workdir / 'cwtypes2_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    results = {}
    try:
        base_out = workdir / 'cwtypes2_base.cab'
        ok = session.save(base_out)
        baseline = sections(xml_member_data(base_out))
        print('baseline save rc=', ok)
        for kind in KINDS:
            rec = {'get_val': None, 'set_rc': None}
            try:
                rec['get_val'] = doc.GetAnalysisType(kind)
            except Exception as exc:
                rec['get_exc'] = str(exc)[:100]
            try:
                rec['set_rc'] = doc.SetAnalysisType(kind, 'T')
                rec['get_after'] = doc.GetAnalysisType(kind)
            except Exception as exc:
                rec['set_exc'] = str(exc)[:100]
            out = workdir / f'cwtypes2_{kind}.cab'
            rec['save_rc'] = session.save(out)
            try:
                cur = sections(xml_member_data(out))
                diff = {}
                for tag in ('analysis_set', 'condition_wizard', 'project'):
                    if baseline.get(tag) and cur.get(tag):
                        keys = set(baseline[tag]) | set(cur[tag])
                        for k in keys:
                            b, c = baseline[tag].get(k), cur[tag].get(k)
                            if b != c:
                                diff[f'{tag}/{k}'] = [b, c]
                rec['diff'] = diff
            except Exception as exc:
                rec['diff_exc'] = str(exc)[:100]
            results[kind] = rec
            print(kind, 'set_rc=', rec.get('set_rc'),
                  'after=', rec.get('get_after'), 'save=', rec.get('save_rc'))
            if rec.get('diff'):
                print('   ', json.dumps(rec['diff'], ensure_ascii=False))
            # reset the flag so later kinds start from the same baseline
            try:
                doc.SetAnalysisType(kind, 'F')
            except Exception:
                pass
    finally:
        session.close()
    out_json = workdir / 'cwtypes2_probe.json'
    out_json.write_text(json.dumps({'baseline': baseline, 'results': results},
                                   indent=2, ensure_ascii=False), encoding='utf-8')
    print('wrote', out_json)

if __name__ == '__main__':
    main()

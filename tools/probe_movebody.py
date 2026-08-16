# Probe SetMoveBodyControl(key, params[]) XML + .s storage format.
# key: T(vel xyz) R(w, c xyz, axis xyz) B(vel xyz + w + c + axis) X(dx,dy,dz)
import sys, difflib, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)

PARAMS = {
    'T': (0.11, 0.22, 0.33),
    'R': (1.5, 10.0, 20.0, 30.0, 0.0, 0.5, 0.86),
    'B': (0.11, 0.22, 0.33, 1.5, 10.0, 20.0, 30.0, 0.0, 0.5, 0.86),
    'X': (0.05, 0.06, 0.07),
}

def xml_member(path: Path) -> bytes:
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    raise RuntimeError('no xml member')

def pretty(data: bytes) -> list[str]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data.decode('utf-8'))
    out = []
    def walk(el, depth):
        attr = ''.join(f' {k}="{v}"' for k, v in sorted(el.attrib.items()))
        txt = (el.text or '').strip()
        out.append('  ' * depth + f'<{el.tag}{attr}>{txt}' if len(el) == 0
                   else '  ' * depth + f'<{el.tag}{attr}>')
        if len(el):
            if txt:
                out.append('  ' * (depth + 1) + txt)
            for c in el:
                walk(c, depth + 1)
            out.append('  ' * depth + f'</{el.tag}>')
    walk(root, 0)
    return out

def diff_lines(a: list[str], b: list[str], label: str) -> None:
    d = [l for l in difflib.unified_diff(a, b, 'before', label, n=2, lineterm='')
         if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))]
    print(f'--- diff {label}: {len(d)} changed lines')
    for l in d:
        print(l)

def grep_movb(path: Path) -> list[str]:
    if not path.exists():
        return []
    txt = path.read_text(encoding='utf-8', errors='replace')
    hits = []
    for i, line in enumerate(txt.splitlines()):
        if re.search(r'MOVB', line):
            hits.append(f'{i+1}: {line.strip()}')
    return hits

def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    parts = [p.name for p in model.parts()]
    print('parts in relay cab:', parts)
    src = workdir / 'movebody_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    try:
        base_out = workdir / 'movebody_base.cab'
        session.save(base_out)
        prev = pretty(xml_member(base_out))

        doc.SetAnalysisType('move_body', 'T')
        mb_out = workdir / 'movebody_flag.cab'
        session.save(mb_out)
        diff_lines(prev, pretty(xml_member(mb_out)), 'flag-only')
        prev = pretty(xml_member(mb_out))

        part = session.model(parts[0])
        print('model name via COM:', part.call('GetName'))

        results = {}
        for key, arr in PARAMS.items():
            rec = {'key': key, 'params': arr}
            try:
                val = part.call('SetMoveBodyControl', key, list(arr))
                rec['rc'] = repr(val)[:80]
                if val is not None:
                    try:
                        rec['value_name'] = val.call('GetName') \
                            if hasattr(val, 'call') else None
                    except Exception as exc:
                        rec['value_name'] = f'ERR {exc}'[:80]
            except Exception as exc:
                rec['exc'] = str(exc)[:200]
            out_cab = workdir / f'movebody_{key}.cab'
            out_s = workdir / f'movebody_{key}.s'
            rec['save'] = session.save(out_cab)
            try:
                rc = doc.SaveSFile(str(out_s))
                rec['sfile_rc'] = rc
            except Exception as exc:
                rec['sfile_exc'] = str(exc)[:120]
            try:
                cur = pretty(xml_member(out_cab))
                import io
                buf = io.StringIO()
                d = [l for l in difflib.unified_diff(prev, cur, 'prev', key,
                                                     n=2, lineterm='')
                     if l.startswith(('+', '-'))
                     and not l.startswith(('+++', '---'))]
                rec['xml_diff_n'] = len(d)
                diff_lines(prev, cur, key)
                prev = cur
            except Exception as exc:
                rec['diff_exc'] = str(exc)[:120]
            rec['movb_s'] = grep_movb(out_s)
            results[key] = rec
            print(key, '=>', {k: v for k, v in rec.items()
                              if k not in ('params',)})
        out_json = workdir / 'movebody_probe.json'
        import json
        out_json.write_text(json.dumps(results, indent=2,
                                       ensure_ascii=False, default=str),
                            encoding='utf-8')
        print('wrote', out_json)
    finally:
        session.close()

if __name__ == '__main__':
    main()

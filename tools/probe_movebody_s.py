# Stage 2: mesh the box, set move_body + SetMoveBodyControl, SaveSFile,
# and dump the MOVB blocks to learn the solver .s syntax.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)

PARAMS = {
    'T': (0.11, 0.22, 0.33),
    'R': (1.5, 10.0, 20.0, 30.0, 0.0, 0.5, 0.86),
    'B': (0.11, 0.22, 0.33, 1.5, 10.0, 20.0, 30.0, 0.0, 0.5, 0.86),
    'X': (0.05, 0.06, 0.07),
}

def movb_blocks(path: Path) -> list[str]:
    txt = path.read_text(encoding='utf-8', errors='replace')
    lines = txt.splitlines()
    out, keep = [], False
    for line in lines:
        s = line.strip()
        if s.startswith(('MOVB', 'MOVR')) or s in ('MOVB',):
            keep = True
        elif keep and s and not s.startswith(('MOVB', 'MOVR')) \
                and s.isalpha() and len(s) <= 8 and s.isupper():
            keep = False  # next command section
        if keep:
            out.append(line.rstrip())
    return out

def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'movb_s_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    meshed = workdir / 'movb_s_meshed.cab'
    if not cab_stpre_api.run_stpre_grid_mesh(src, meshed):
        print('mesh failed', cab_stpre_api.last_error)
        return
    print('meshed ok', meshed.stat().st_size)

    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(meshed):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    try:
        doc.SetAnalysisType('move_body', 'T')
        part = session.model('box')
        for key, arr in PARAMS.items():
            part.call('SetMoveBodyControl', key, list(arr))
            s_out = workdir / f'movb_s_{key}.s'
            try:
                rc = doc.SaveSFile(str(s_out))
                print(f'== {key}: SaveSFile rc={rc} exists={s_out.exists()}')
            except Exception as exc:
                print(f'== {key}: SaveSFile exc {exc}')
                continue
            if s_out.exists():
                for l in movb_blocks(s_out):
                    print('   ', l)
    finally:
        session.close()

if __name__ == '__main__':
    main()

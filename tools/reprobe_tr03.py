"""Re-run tr03 probe cases live against STpre COM (workspace workdir)."""
import sys, json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import stpre_probe
from stpre_probe import ProbeCase

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)
cases = [c for c in stpre_probe.tr03_vd_cases()
         if c.name in ('tr03_imp_vd_0', 'tr03_imp_vd_1')]
records = []
for c in cases:
    rec = stpre_probe.run_case(c, workdir)
    print(c.name, 'ok=', rec.get('ok'), 'err=', rec.get('error'))
    if rec.get('ok'):
        m = rec['output']['axis_metrics']
        print('   counts:', [m[a]['count'] for a in 'xyz'])
        print('   z part lines:', [round(v, 4) for v in rec['output']['axes']['z']
              if 35 < v < 115])
    records.append(rec)
out = ROOT / 'tools' / 'probe_work' / 'retest.json'
out.write_text(json.dumps({'records': records}, indent=2), encoding='utf-8')
print('wrote', out)
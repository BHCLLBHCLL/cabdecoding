# P0 round 59 (live STpre): all-mode threshold sweep on the tr03
# impeller.  If the 26/21 extra candidate lines are absorbed as thr
# grows they are merge-tolerance artefacts; if they persist they come
# from an independent geometric rule.
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import stpre_probe
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)
base = dict(base="tr03", keep_parts=("Impeller",),
            domain_min=(-20.0, -20.0, -20.0),
            domain_max=(70.0, 120.0, 120.0))

results = {}
for thr in (0.1, 0.2, 0.5, 1.0, 2.0):
    name = f"tr03_all_thr{str(thr).replace('.','_')}"
    case = stpre_probe.ProbeCase(name=name, **base, vertex_detection=0,
                                 threshold=(thr, thr, thr))
    rec = stpre_probe.run_case(case, workdir)
    if not rec.get('ok'):
        print(name, 'FAILED', rec.get('error'))
        continue
    cab = workdir / f'{name}_out.cab'
    a = CabArchive.parse(cab.read_bytes())
    a.fill_member_data()
    d = next(m.data for m in a.members
             if m.name.endswith('.xml') and not m.name.startswith('_'))
    mb = parse_stpre(d).root.find('mesh_block')
    sl = {}
    for ax in ('x', 'y', 'z'):
        el = mb.find(ax)
        vals = []
        if el is not None:
            for g in el:
                if g.tag != 'g' or not g.text:
                    continue
                parts = g.text.strip().split(',')
                if len(parts) > 1 and parts[1].strip().upper() == 'S':
                    try:
                        vals.append(float(parts[0].strip()))
                    except ValueError:
                        pass
        sl[ax] = sorted(vals)
    results[thr] = sl
    print(f"thr={thr}: " + "  ".join(f"{ax}S={len(sl[ax])}" for ax in 'xyz'))

ref = results.get(0.1)
if ref:
    for thr, sl in results.items():
        if thr == 0.1:
            continue
        print(f"\nthr {0.1} -> {thr}:")
        for ax in 'xyz':
            a0 = np.asarray(ref[ax])
            a1 = np.asarray(sl[ax])
            gone = [v for v in a0 if not np.any(np.abs(a1-v) < 1e-6)]
            new = [v for v in a1 if not np.any(np.abs(a0-v) < 1e-6)]
            print(f"  {ax}: {len(a0)}->{len(a1)}  "
                  f"gone={[round(v,3) for v in gone][:12]}  "
                  f"new={[round(v,3) for v in new][:12]}")

out = {str(k): v for k, v in results.items()}
(workdir / 'all_thr_sweep.json').write_text(
    json.dumps(out, indent=1), encoding='utf-8')
print("saved tools/probe_work/all_thr_sweep.json")

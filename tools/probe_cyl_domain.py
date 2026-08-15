# Probe STpre COM cylindrical/axial domain gridding (P0-2).
# For each case: SetCylindricalDomain + root-block SetParam (length/limit/ratio)
# + SetGridParam + ExecuteGrid + ExecuteElement + save, then dump the
# mesh_block axis tables / analysis_region / mesh_control / element boxes.
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)

CASES = [
    # name, (r1, r2, t1, t2, z1, z2), standard_length
    ('cyl_r0_50_theta360_z0_50_std5', (0.0, 50.0, 0.0, 360.0, 0.0, 50.0), 5.0),
    ('cyl_r20_50_theta360_z0_50_std5', (20.0, 50.0, 0.0, 360.0, 0.0, 50.0), 5.0),
    ('cyl_r0_50_theta180_z0_50_std5', (0.0, 50.0, 0.0, 180.0, 0.0, 50.0), 5.0),
    ('cyl_r0_50_theta360_z0_50_std2_5', (0.0, 50.0, 0.0, 360.0, 0.0, 50.0), 2.5),
    ('axial_r0_50_z0_50_std5', (0.0, 50.0, 0.0, 0.0, 0.0, 50.0), 5.0),
]

def xml_member_data(path: Path) -> bytes:
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    raise RuntimeError('no xml member')

def axes_of(root) -> dict:
    mb = root.find('mesh_block')
    out = {}
    if mb is not None:
        for ax in ('x', 'y', 'z'):
            el = mb.find(ax)
            if el is None:
                out[ax] = None
                continue
            vals = []
            for c in el:
                if c.tag == 'grid' and (c.text or '').strip():
                    vals = [float(v) for v in c.text.strip().split(',')]
            out[ax] = vals
    return out

def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'cyldom_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    records = []
    for name, (r1, r2, t1, t2, z1, z2), std in CASES:
        session = cab_stpre_api.STpreSession()
        rec = {'name': name, 'ok': False}
        try:
            if not session.ensure_open(src):
                rec['error'] = 'open: ' + str(cab_stpre_api.last_error)
                records.append(rec)
                continue
            doc = session.doc
            mesher = session.mesher
            try:
                dom = doc.call('SetCylindricalDomain', 'Domain(cylindrical)',
                               r1, r2, t1, t2, z1, z2)
                rec['set_domain_rc'] = dom is not None
            except Exception as exc:
                rec['set_domain_rc'] = f'{type(exc).__name__}: {exc}'
            if name.startswith('axial'):
                rec['axissym_rc'] = doc.call('SetAnalysisType', 'axissymmetry', 'T')
            blk = mesher.call('GetBlock', 'root')
            if blk is None:
                rec['getblock_rc'] = None
            for key, p1, p2, p3 in (('length', std, std, std),
                                    ('limit', 0.1, 0.1, 0.1),
                                    ('ratio', 1.0, 1.0, 1.0)):
                rec[f'blk_setparam_{key}_rc'] = (
                    cab_stpre_api._invoke(blk, 'SetParam', key, p1, p2, p3)
                    if blk is not None else None)
            for key, p1, p2, p3 in (('division_method', 'detail', '', ''),
                                    ('division_type', 'minmax', '', ''),
                                    ('edge_contact', 0, '', ''),
                                    ('outer_ratio', 1.2, 1.2, 1.2)):
                rec[f'gridparam_{key}_rc'] = mesher.call(
                    'SetGridParam', key, p1, p2, p3)
            rec['grid_rc'] = mesher.call('ExecuteGrid', 'detail', 'T')
            rec['element_rc'] = mesher.call('ExecuteElement')
            out = workdir / f'cyldom_{name}.cab'
            rec['save_rc'] = session.save(out)
            root = parse_stpre(xml_member_data(out)).root
            rec['axes'] = axes_of(root)
            ar = root.find('analysis_region')
            if ar is not None:
                import xml.etree.ElementTree as ET
                rec['domain'] = ET.tostring(ar, encoding='unicode')[:800]
            mc = root.find('mesh_control')
            if mc is not None:
                rec['mesh_control'] = {
                    c.tag: (c.text or '').strip()
                    for c in mc if c.tag in
                    ('select_vertex', 'divide_method', 'divide_scale',
                     'edge_contact', 'divide_ratio2', 'domain_coordinate')}
            el = root.find('element')
            rec['has_element'] = el is not None
            rec['ok'] = True
        except Exception as exc:
            rec['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            session.close()
        records.append(rec)
        ax = rec.get('axes') or {}
        print(name, 'ok=', rec.get('ok'), 'err=', rec.get('error'))
        for k in 'xyz':
            v = ax.get(k)
            if v is None:
                print('   ', k, '= None')
            else:
                print('   ', k, 'n=', len(v), 'min=', v[0] if v else None,
                      'max=', v[-1] if v else None)
                print('       ', [round(x, 4) for x in v[:12]])
        if rec.get('domain'):
            print('    domain:', rec['domain'][:400].replace('\n', ' | '))
    out_json = workdir / 'cyldom_probe.json'
    out_json.write_text(json.dumps(records, indent=2), encoding='utf-8')
    print('wrote', out_json)

if __name__ == '__main__':
    main()
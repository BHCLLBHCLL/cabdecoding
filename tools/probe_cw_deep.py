# R8-A 探针：解包 CW 深字段相关样本 cab，导出 XML 结构（开发期分析用）。
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cab_container import CabArchive  # noqa: E402
from cabxml import parse_stpre  # noqa: E402

WORK = ROOT / 'tools' / 'probe_work'


def xml_member_data(path: Path) -> bytes:
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    raise RuntimeError('no xml member: %s' % path)


def dump_sections(path: Path, tags=('analysis_set', 'analysis_etc',
                                    'output', 'condition_wizard')):
    print('=' * 72)
    print('CAB:', path.name)
    try:
        data = xml_member_data(path)
    except Exception as exc:
        print('  !!', exc)
        return
    root = parse_stpre(data).root
    for tag in tags:
        el = root.find(tag)
        if el is None or len(el) == 0:
            continue
        print(f'-- <{tag}> --')
        for c in el:
            attrs = ' '.join(f'{k}={v!r}' for k, v in c.attrib.items())
            text = (c.text or '').strip()
            if len(c):
                sub = ', '.join(
                    f'{s.tag}={(s.text or "").strip()!r}' for s in c)
                print(f'  <{c.tag} {attrs}> [{sub}]')
            else:
                print(f'  <{c.tag} {attrs}> {text!r}')


def main():
    names = sys.argv[1:] or [
        'cwtypes2_mars.cab', 'cwtypes2_mars1.cab', 'cwtypes2_vof.cab',
        'cwtypes2_Particle.cab', 'cwtypes2_reaction.cab',
    ]
    for n in names:
        p = WORK / n
        if p.exists():
            dump_sections(p)
        else:
            print('missing:', p)


if __name__ == '__main__':
    main()

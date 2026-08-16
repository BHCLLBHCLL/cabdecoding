# WindTool 前置 COM 探针：实证 SetNorthAngle + SetFluxPower2 的 XML 落盘格式。
#
# 流程：清僵尸 STpre → 用 box.cab 建 relay → 打开 → 网格化(可选) →
#       SetNorthAngle(0) + SetFluxPower2(1 个风向入口) + 挂到 Xmin/Xmax 等
#       边界模型 → SaveCabFile → 解包 diff，记录 power-law 入口的 value type
#       与参数子元素名。结果写 tools/probe_work/windtool_probe.json。
#
# COM 不可用 / 已运行 STpre / 边界模型缺失时记录错误并退出，不阻塞。
import sys, difflib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cab_stpre_api
from cab_container import CabArchive
from stpre_probe import _fresh_model

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)


def _kill_zombie_stpre():
    """清掉残留 STpre 进程（WindTool 探针需要独占单实例 COM）。"""
    for name in ("STpre_Bx64net.exe", "STprePMesh_Bx64net.exe"):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass


def _xml_member(path: Path) -> bytes:
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    raise RuntimeError('no xml member')


def _pretty(data: bytes) -> list[str]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data.decode('utf-8'))
    out = []

    def walk(el, depth):
        attr = ''.join(f' {k}="{v}"' for k, v in sorted(el.attrib.items()))
        txt = (el.text or '').strip()
        if len(el) == 0:
            out.append('  ' * depth + f'<{el.tag}{attr}>{txt}')
        else:
            out.append('  ' * depth + f'<{el.tag}{attr}>')
            if txt:
                out.append('  ' * (depth + 1) + txt)
            for c in el:
                walk(c, depth + 1)
            out.append('  ' * depth + f'</{el.tag}>')

    walk(root, 0)
    return out


def _diff(a: list[str], b: list[str]) -> list[str]:
    return [l for l in difflib.unified_diff(a, b, 'before', 'after',
                                            n=2, lineterm='')
            if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))]


def _py(v):
    """把 COM 返回值转成可 JSON 序列化的纯 Python 值（会话关闭前调用）。"""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    try:
        return str(v)
    except Exception:
        return repr(v)


def _value_xml(path: Path):
    """提取 power-law 入口 value 的 type + 子元素名/文本。"""
    import xml.etree.ElementTree as ET
    data = _xml_member(path)
    root = ET.fromstring(data.decode('utf-8'))
    vals = []
    for v in root.findall('value'):
        name = v.attrib.get('name') or v.attrib.get('type')
        if name == 'Tool_Flux1_':
            vals.append({
                'attrib': dict(v.attrib),
                'children': [
                    {'tag': c.tag, 'attrib': dict(c.attrib),
                     'text': (c.text or '').strip()}
                    for c in v],
            })
    return vals


def main():
    record = {'ok': False}
    if not cab_stpre_api.api_available():
        record['error'] = 'STpre COM ProgID 未注册'
    else:
        _kill_zombie_stpre()
        if cab_stpre_api._stpre_process_running():
            record['error'] = 'STpre 仍在运行，拒绝探针'
        else:
            try:
                model, archive = _fresh_model('box')
                src = workdir / 'windtool_in.cab'
                if not cab_stpre_api.build_relay_cab(model, archive, src):
                    record['error'] = f'relay: {cab_stpre_api.last_error}'
                else:
                    session = cab_stpre_api.STpreSession()
                    try:
                        if not session.ensure_open(src):
                            record['error'] = f'open: {cab_stpre_api.last_error}'
                        else:
                            doc = session.doc
                            record['unit_length'] = _py(
                                doc.call('GetUnit', 'length'))
                            base = workdir / 'windtool_base.cab'
                            session.save(base)
                            prev = _pretty(_xml_member(base))

                            rc_na = doc.SetNorthAngle(0.0)
                            rc_pl = doc.SetFluxPower2(
                                'Tool_Flux1_', 5.0, 'N', 202.5, 3.7037,
                                0.0, 74.5, 0.0, 'zg', 550.0, 0.0)
                            record['SetNorthAngle_rc'] = _py(rc_na)
                            record['SetFluxPower2_rc'] = _py(rc_pl)

                            # 挂到边界模型（Xmax 为 202.5° 风向的入口）
                            for fname in ('Xmin', 'Xmax', 'Ymin', 'Ymax'):
                                try:
                                    m = session.model(fname)
                                    if m is not None:
                                        m.AppendValue('Tool_Flux1_')
                                        record[f'{fname}_append'] = 'ok'
                                    else:
                                        record[f'{fname}_append'] = 'None'
                                except Exception as exc:
                                    record[f'{fname}_append'] = str(exc)[:120]

                            out = workdir / 'windtool_out.cab'
                            session.save(out)
                            record['save'] = True
                            record['xml_diff'] = _diff(prev, _pretty(_xml_member(out)))
                            record['value_xml'] = _value_xml(out)
                            record['ok'] = True
                    finally:
                        session.close()
            except Exception as exc:
                import traceback
                record['error'] = f'{type(exc).__name__}: {exc}'
                record['traceback'] = traceback.format_exc()

    out_json = workdir / 'windtool_probe.json'
    out_json.write_text(json.dumps(record, indent=2, ensure_ascii=False,
                                   default=str), encoding='utf-8')
    print('wrote', out_json)
    print(json.dumps({k: v for k, v in record.items()
                      if k not in ('xml_diff', 'traceback', 'value_xml')},
                     ensure_ascii=False, indent=2, default=str))
    if record.get('value_xml'):
        print('value_xml:', json.dumps(record['value_xml'], ensure_ascii=False,
                                       indent=2, default=str))


if __name__ == '__main__':
    main()

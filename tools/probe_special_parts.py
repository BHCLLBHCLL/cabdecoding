# R7 探针：专用件（AC Unit / Peltier / Linear Diffuser / Card Guide / Heat Pipe）
# 经 COM Create*Model / SetHeatPipeCondition / SetAirconModel 创建后，
# SaveCabFile 解包 diff XML，实证各件参数的存储元素/属性名。
#
# 运行前先 Stop-Process 清理僵尸 STpre（单实例 COM 服务器）：
#   Get-Process STpre -ErrorAction SilentlyContinue | Stop-Process -Force
# 结果写 tools/probe_work/special_parts_probe.json 供追溯。
import sys, difflib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cab_stpre_api
from cab_container import CabArchive
from cabxml import parse_stpre

workdir = ROOT / 'tools' / 'probe_work'
workdir.mkdir(exist_ok=True)


def xml_member(path: Path) -> bytes:
    """解包 .cab 取主 XML 成员。"""
    arch = CabArchive.parse(path.read_bytes())
    arch.fill_member_data()
    for m in arch.members:
        if m.name.endswith('.xml') and not m.name.startswith('_'):
            return m.data
    raise RuntimeError('no xml member')


def pretty(data: bytes) -> list:
    """压缩成可 diff 的行列表（缩进 + 属性 + 文本）。"""
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


def diff_lines(a, b, label):
    d = [l for l in difflib.unified_diff(a, b, 'before', label, n=2,
                                         lineterm='')
         if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))]
    print(f'--- diff {label}: {len(d)} changed lines')
    for l in d:
        print(l)
    return d


def grep_cards(path: Path, keys) -> list:
    """在 .s 里找专用件相关卡片行。"""
    if not path.exists():
        return []
    txt = path.read_text(encoding='utf-8', errors='replace')
    hits = []
    for i, line in enumerate(txt.splitlines()):
        if any(k in line for k in keys):
            hits.append(f'{i+1}: {line.strip()}')
    return hits


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'special_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    results = {'steps': []}
    first_part = next((p.name for p in model.parts()), None)
    results['base_parts'] = [p.name for p in model.parts()]
    print('parts in relay cab:', results['base_parts'])
    try:
        base_out = workdir / 'special_base.cab'
        session.save(base_out)
        prev = pretty(xml_member(base_out))

        def step(label, fn):
            """执行一步 COM 调用 → 存盘 → diff → 记录。"""
            nonlocal prev
            rec = {'step': label}
            try:
                val = fn()
                rec['rc'] = repr(val)[:120]
                if hasattr(val, 'call'):
                    try:
                        rec['name'] = val.call('GetName')
                    except Exception:
                        pass
            except Exception as exc:
                rec['exc'] = str(exc)[:240]
            out_cab = workdir / f'special_{label}.cab'
            out_s = workdir / f'special_{label}.s'
            try:
                rec['save'] = session.save(out_cab)
            except Exception as exc:
                rec['save_exc'] = str(exc)[:120]
            try:
                rec['sfile_rc'] = doc.SaveSFile(str(out_s))
                rec['s_cards'] = grep_cards(out_s, (
                    'AIRCON', 'PELTIER', 'TCMDL', 'HTRC', 'OPERATION'))
            except Exception as exc:
                rec['sfile_exc'] = str(exc)[:120]
            try:
                cur = pretty(xml_member(out_cab))
                d = diff_lines(prev, cur, label)
                rec['xml_diff_n'] = len(d)
                rec['xml_diff'] = d[:220]
                prev = cur
            except Exception as exc:
                rec['diff_exc'] = str(exc)[:120]
            results['steps'].append(rec)
            print(label, '=>', {k: v for k, v in rec.items()
                                if k != 'xml_diff'})

        # 1) Peltier：name,bx,by,bz,sx,sy,sz,tc,th,parms[7],table[9]
        #    parms/table 语义手册未细列，先给可辨识的探针值再 diff 观察
        parms = [12.0, 3.3, 27.0, 47.0, 60.0, 1.5, 4.0]
        table = [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8, 9.9]
        step('peltier', lambda: doc.CreatePeltierModel(
            'Peltier1', 10.0, 10.0, 10.0, 40.0, 40.0, 4.0,
            2.0, 2.0, parms, table))

        # 2) Card Guide：name,bx,by,bz,sx,sy,sz,d1,d2,h1,h2,f1,n,axis,direc
        step('card_guide', lambda: doc.CreateCardGuideModel(
            'CardGuide1', 10.0, 10.0, 10.0, 60.0, 20.0, 12.0,
            2.0, 2.0, 3.0, 3.0, 1.5, 8, 'z', 'x'))

        # 3) AC Unit（ceil4）：name,type,bx,by,bz,sx,sy,sz,w[3],h[3],d[3],
        #    n_type,l_type。先开 aircon 分析类型（SetAnalysisType 键表）
        w3 = [80.0, 1.0, 0.0]
        h3 = [80.0, 2.0, 0.0]
        d3 = [20.0, 3.0, 0.0]

        def _ac_unit():
            try:
                rt = doc.SetAnalysisType('aircon', 'T')
            except Exception as exc:
                rt = f'exc {str(exc)[:80]}'
            last = f'SetAnalysisType rc={rt}'
            for n_type, l_type in (('-z', ''), ('z', ''), ('-z', 0),
                                   ('z', 'z')):
                try:
                    val = doc.CreateAirconModel(
                        'ACUnit1', 'ceil4', 10.0, 10.0, 60.0,
                        100.0, 100.0, 20.0, w3, h3, d3, n_type, l_type)
                    if val is not None and val.raw is not None:
                        return val
                    last = f'None with n_type={n_type!r}'
                except Exception as exc:
                    last = str(exc)[:120]
            return f'all failed: {last}'
        step('ac_unit', _ac_unit)

        # 3b) AC 条件模型 SetAirconModel + SetParam（手册 AirconModel 类；
        #     该方法未在 cab_stpre_api 包装，走 ComObject.call 通用调用，
        #     返回的裸 COM 对象需包一层 ComObject 才有 .call）
        def _aircon_param():
            ac = cab_stpre_api.ComObject(doc.call('SetAirconModel',
                                                  'ACModel1', 'ceil4'))
            rc1 = ac.call('SetParam', 'ability', 2500.0)
            rc2 = ac.call('SetParam', 'flow-rate', 15.0)
            rc3 = ac.call('SetParam', 'T-minmax_limit', 16.0, 30.0)
            gs = ac.call('GetParamString', 'ac_type')
            return f'aircon={rc1},{rc2},{rc3} ac_type={gs}'
        step('aircon_param', _aircon_param)

        # 3c) 把条件模型绑到 AC 部件（Model.SetAircon(aircon, angle)）
        def _set_aircon():
            m = session.model('ACUnit1')
            if m is None:
                return 'no model ACUnit1'
            return m.call('SetAircon', 'ACModel1', 30.0)
        step('set_aircon', _set_aircon)

        # 4) Linear Diffuser：手册 Doc 类未列参数签名。上轮实证 5 参
        #    （name,cx,cy,cz,?）可建出 air_outlet 部件，本轮补全
        #    flow/angle/temp/turb 布局并解包确认 value 字段
        def _diffuser():
            last = None
            for args in (
                ('Diffuser1', 50.0, 50.0, 80.0, 600.0, 20.0, 0.0, 27.0, 0),
                ('Diffuser1', 50.0, 50.0, 80.0, 600.0, 20.0, 27.0, 0.0, 0),
                ('Diffuser1', 50.0, 50.0, 80.0, 600.0, 20.0, 0.0, 27.0),
                ('Diffuser1', 50.0, 50.0, 80.0, 600.0, 20.0, 27.0),
                ('Diffuser1', 50.0, 50.0, 80.0, 600.0, 20.0, 0.0),
                ('Diffuser1', 50.0, 50.0, 80.0, 600.0, 20.0),
            ):
                try:
                    val = doc.call('CreateLinerDiffuserModel', *args)
                    if val is not None:
                        return f'ok {len(args)} args -> {val!r}'[:120]
                    last = f'returned None ({len(args)} args)'
                except Exception as exc:
                    last = f'({len(args)}): {str(exc)[:100]}'
            return f'all failed: {last}'
        step('diffuser', _diffuser)

        # 5) Heat Pipe：Model.SetHeatPipeCondition(cool, hot, r, qmax)
        #    （cool=放热侧部件名, hot=发热侧部件名, r=k/W, qmax=W）
        def _heatpipe():
            m = session.model('Box')
            if m is None:
                # 退回第一个部件
                names = [p.name for p in
                         parse_stpre(xml_member(
                             workdir / 'special_base.cab'))] \
                    if False else None
                return 'no model Box'
            return m.call('SetHeatPipeCondition',
                          'Box', 'Box', 0.05, 50.0)
        step('heat_pipe', _heatpipe)

        out_json = workdir / 'special_parts_probe.json'
        out_json.write_text(json.dumps(results, indent=2,
                                       ensure_ascii=False, default=str),
                            encoding='utf-8')
        print('wrote', out_json)
    finally:
        session.close()


if __name__ == '__main__':
    main()

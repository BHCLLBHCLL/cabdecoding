# R9-A 探针：FEM 真单元生成（Edit 菜单 FEM Conversion）
# 手册实证签名：Model.CreateFEM(length, scale, edge)
#   length: 单元尺寸 (double)
#   scale : "T"=length 乘以部件长度 / "F"=length 即绝对单元尺寸 (string)
#   edge  : "T"=保留棱边 / "F"=不保留 (string)
#   返回: 新建的 Model 类（FEM 模型）
#
# 流程：fresh box model → 建 cuboid 实体件 → SetGridParam+ExecuteGrid 建网格
#   → 多组合调 CreateFEM → SaveCabFile 解包 diff XML（找 FEM 单元/节点存储
#   位置）→ SaveSFile 看 .s 是否有 FEM 段。
#
# 运行前先 Stop-Process 清理僵尸 STpre（单实例 COM 服务器）：
#   Get-Process STpre* -ErrorAction SilentlyContinue | Stop-Process -Force
# 结果写 tools/probe_work/fem_probe.json 供追溯。
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


def member_names(path: Path) -> list:
    """解包 .cab 列全部成员名（找 FEM 独立数据文件）。"""
    arch = CabArchive.parse(path.read_bytes())
    return [m.name for m in arch.members]


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
    """在 .s 里找 FEM 相关卡片行。"""
    if not path.exists():
        return []
    txt = path.read_text(encoding='utf-8', errors='replace')
    hits = []
    for i, line in enumerate(txt.splitlines()):
        if any(k in line for k in keys):
            hits.append(f'{i+1}: {line.strip()}')
    return hits


def model_array_names(doc):
    """GetAllModelArray → [(name, type)]。"""
    out = []
    try:
        arr = doc.call('GetAllModelArray', 'parts')
    except Exception as exc:
        return [f'<exc {str(exc)[:80]}>']
    for m in arr or []:
        try:
            w = cab_stpre_api.ComObject(m)
            out.append((w.call('GetName'), w.call('GetModelType')))
        except Exception as exc:
            out.append(f'<exc {str(exc)[:80]}>')
    return out


def main():
    from stpre_probe import _fresh_model
    model, archive = _fresh_model('box')
    src = workdir / 'fem_in.cab'
    if not cab_stpre_api.build_relay_cab(model, archive, src):
        print('relay failed', cab_stpre_api.last_error)
        return
    session = cab_stpre_api.STpreSession()
    if not session.ensure_open(src):
        print('open failed', cab_stpre_api.last_error)
        return
    doc = session.doc
    results = {'steps': []}
    print('parts in relay cab:', [p.name for p in model.parts()])
    try:
        # 基线
        base_out = workdir / 'fem_base.cab'
        session.save(base_out)
        prev = pretty(xml_member(base_out))
        results['base_members'] = member_names(base_out)
        results['base_models'] = model_array_names(doc)

        def step(label, fn):
            """执行一步 COM 调用 → 存盘 → diff → 记录。"""
            nonlocal prev
            rec = {'step': label}
            try:
                val = fn()
                rec['rc'] = repr(val)[:160]
                if hasattr(val, 'call'):
                    for m in ('GetName', 'GetModelType', 'GetBoundingBox'):
                        try:
                            rec[m] = repr(val.call(m))[:120]
                        except Exception:
                            pass
            except Exception as exc:
                rec['exc'] = str(exc)[:240]
            out_cab = workdir / f'fem_{label}.cab'
            out_s = workdir / f'fem_{label}.s'
            try:
                rec['save'] = session.save(out_cab)
                rec['members'] = member_names(out_cab)
            except Exception as exc:
                rec['save_exc'] = str(exc)[:120]
            try:
                rec['sfile_rc'] = doc.SaveSFile(str(out_s))
                rec['s_cards'] = grep_cards(out_s, (
                    'FEM', 'VFEM', 'EFEM', 'FEMS'))
            except Exception as exc:
                rec['sfile_exc'] = str(exc)[:120]
            try:
                cur = pretty(xml_member(out_cab))
                d = diff_lines(prev, cur, label)
                rec['xml_diff_n'] = len(d)
                rec['xml_diff'] = d[:400]
                prev = cur
            except Exception as exc:
                rec['diff_exc'] = str(exc)[:120]
            results['steps'].append(rec)
            print(label, '=>', {k: v for k, v in rec.items()
                                if k != 'xml_diff'})
            return rec

        # 1) 建一个 cuboid 实体件（手册签名 name,bx,by,bz,sx,sy,sz；
        #    typed 包装是 (name, base, size) 3 参，这里走通用 call）
        step('cube', lambda: doc.call('CreateCubeModel',
                                      'FemBox',
                                      0.0, 0.0, 0.0, 20.0, 20.0, 20.0))

        # 2) 建网格（SetGridParam + ExecuteGrid，参照 stpre_probe）
        def _grid():
            ok = session.grid(
                [('division_method', 'detail', '', ''),
                 ('division_type', 'minmax', '', '')], 'detail')
            return f'grid={ok}'
        step('grid', _grid)

        # 3) CreateFEM 多组合尝试（手册签名 length, scale, edge）。
        #    每个组合用全新 cuboid，避免上一次转换污染。
        combos = [
            ('F_T', 2.0, 'F', 'T'),
            ('T_T', 0.05, 'T', 'T'),
            ('F_F', 4.0, 'F', 'F'),
            ('T_F', 0.05, 'T', 'F'),
        ]
        made = []
        for tag, length, scale, edge in combos:
            pname = f'FemBox_{tag}'

            def _fem(length=length, scale=scale, edge=edge, pname=pname):
                cube = session.model(pname)
                if cube is None or cube.raw is None:
                    return f'no model {pname}'
                return cube.CreateFEM(length, scale, edge)
            step(f'cube_{tag}', lambda pname=pname: doc.call(
                'CreateCubeModel', pname,
                -20.0, -20.0, -20.0, 10.0, 10.0, 10.0))
            rec_fem = step(f'fem_{tag}', _fem)
            # CreateFEM 经 typed 包装返回裸 COM 对象（repr 为 COMObject）
            if 'exc' not in rec_fem and 'rc' in rec_fem \
                    and 'COMObject' in str(rec_fem['rc']):
                made.append(tag)

        results['fem_ok_combos'] = made
        results['final_models'] = model_array_names(doc)

        # 3b) .xfem 成员摘要（节点/单元数量与 kind 集合）
        def xfem_summary(cab: Path) -> dict:
            import xml.etree.ElementTree as ET
            arch = CabArchive.parse(cab.read_bytes())
            arch.fill_member_data()
            xm = next((m for m in arch.members
                       if m.name.endswith('.xfem')), None)
            if xm is None:
                return {'member': None}
            root = ET.fromstring(xm.data.decode('utf-8'))
            out = {'member': xm.name, 'models': []}
            for mdl in root.iter('model'):
                nodes = mdl.find('node')
                els = mdl.find('element')
                kinds = sorted({e.attrib.get('kind') for e in els.iter('e')}) \
                    if els is not None else []
                out['models'].append({
                    'name': mdl.attrib.get('name'),
                    'temp_type': mdl.attrib.get('temp_type'),
                    'node_num': nodes.attrib.get('num') if nodes is not None else None,
                    'element_num': els.attrib.get('num') if els is not None else None,
                    'element_kinds': kinds,
                })
            return out
        for tag, _l, _s, _e in combos:
            c = workdir / f'fem_fem_{tag}.cab'
            if c.exists():
                results[f'xfem_{tag}'] = xfem_summary(c)
                print(f'xfem {tag}:', results[f'xfem_{tag}'])

        # 3c) 重开验证：OpenCabFile 保存件 → GetModel('fem_...') 应成功
        def _reopen():
            target = workdir / 'fem_fem_F_T.cab'
            rc = doc.OpenCabFile(str(target))
            got = doc.GetModel('fem_FemBox_F_T')
            name = got.call('GetName') \
                if got is not None and got.raw is not None else None
            return f'OpenCabFile rc={rc} GetModel name={name}'
        step('reopen', _reopen)

        # 4) 终局 XML 全量找 FEM 存储位置（tag/attr 含 fem 的元素）
        final_cab = workdir / 'fem_fem_F_T.cab'
        probe_target = next((workdir / f'fem_fem_{t}.cab' for t in
                             made or ['F_T']), final_cab)
        if probe_target.exists():
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_member(probe_target).decode('utf-8'))
            fem_hits = []

            def scan(el, path=''):
                p = f'{path}/{el.tag}'
                if 'fem' in el.tag.lower() or \
                        any('fem' in k.lower() or 'fem' in str(v).lower()
                            for k, v in el.attrib.items()):
                    fem_hits.append(p + ''.join(
                        f' {k}="{v}"' for k, v in el.attrib.items()))
                for c in el:
                    scan(c, p)
            scan(root)
            results['fem_xml_paths'] = fem_hits[:80]
            print('fem xml paths:', fem_hits[:40])

        out_json = workdir / 'fem_probe.json'
        out_json.write_text(json.dumps(results, indent=2,
                                       ensure_ascii=False, default=str),
                            encoding='utf-8')
        print('wrote', out_json)
    finally:
        session.close()


if __name__ == '__main__':
    main()

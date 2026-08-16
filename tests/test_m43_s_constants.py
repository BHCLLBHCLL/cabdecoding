"""M43 / R8-B: .s 导出 opaque 常量透明化测试。

锚点回归：ex4_e 基线模型的常量行与官方 tests/ex4_e.s 逐行一致，
证明常量派生化未改变基线输出。变体派生：修改 XML 状态后各常量按
R8-B 规则（295 对 (.cab,.s) 样本交叉验证，见 tools/diag_s_constants.py
与 s_export.py 模块头注释）随配置变化：

- SDAT hdr2   <- 扩散物种数 / 辐射面组数(无 0, flux 2, 其余 4) / 湍流模型号
- EQUA 8 位掩码 <- 位1-3 轴向区间数>1, 位4 恒 1, 位5 heat(0/1/mars 2),
                  位6-7 湍流, 位8 扩散物种
- HSOL        <- thermal_solver[0] / [1],[3],[4]；热分析 + 不可压 +
                  无自由面 + 无运动件才发射
- CYCS/CYCT   <- calculation 稳/瞬态 + cycle（+ time_step / courant 行）
- UNDR/STED   <- steady_param 的 under_relax / conv_check 逐条
- VFEX/HEATPATH <- radiation 非 flux 角系数法 / heat_path=1
"""

import os
import xml.etree.ElementTree as ET

from cab_container import CabArchive
from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
from s_export import SExport, build_sdat


HERE = os.path.dirname(__file__)
CAB = os.path.join(HERE, "ex4_e.cab")
S_OFFICIAL = os.path.join(HERE, "ex4_e.s")


def _models():
    arch = CabArchive.parse(open(CAB, "rb").read())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return (StpreModel(parse_stpre(members["ex4_e.xml"])),
            PropertyModel(parse_property(members["_ex4_e_property.xml"])))


def _card(sdat, keyword, n=1):
    """The ``n`` value lines following a solver-card keyword line;
    None when the keyword is absent."""
    lines = sdat.splitlines()
    for i, l in enumerate(lines):
        if l.strip() == keyword:
            return [lines[i + k].rstrip() for k in range(1, n + 1)]
    return None


def _has(sdat, keyword):
    return any(l.strip() == keyword for l in sdat.splitlines())


def _hdr_rows(sdat):
    """SDAT 头两行 12 列整数（网格计数行 + 配置计数行）。"""
    lines = sdat.splitlines()
    rows = []
    start = next(i for i, l in enumerate(lines) if l.strip() == "SDAT")
    for j in range(start + 1, start + 40):
        if len(rows) == 2:
            break
        f = [lines[j][k:k + 12].strip() for k in range(0, len(lines[j]), 12)]
        f = [x for x in f if x]
        if len(f) >= 8 and all(x.lstrip("-").isdigit() for x in f):
            rows.append([int(x) for x in f])
    return rows


def _mut(model, path, text=None, attrib=None):
    """Create-or-update ``path`` (slash separated) under the model root."""
    parent = model.root
    tags = path.split("/")
    for tag in tags[:-1]:
        el = parent.find(tag)
        if el is None:
            el = ET.SubElement(parent, tag)
        parent = el
    leaf = parent.find(tags[-1])
    if leaf is None:
        leaf = ET.SubElement(parent, tags[-1])
    if text is not None:
        leaf.text = " " + text + " "
    for k, v in (attrib or {}).items():
        leaf.attrib[k] = v
    return leaf


# ---- 锚点回归：ex4_e 基线常量与官方样本一致 -----------------------------

def test_anchor_header_rows():
    ours = build_sdat(*_models())
    official = open(S_OFFICIAL, encoding="utf-8-sig").read()
    assert _hdr_rows(ours) == _hdr_rows(official)
    # hdr1 前三列网格计数 + hdr2：diffusion=0, radiation vf=4 组, 湍流模型 0
    assert _hdr_rows(ours)[0][:3] == [98, 242, 62]
    assert _hdr_rows(ours)[1] == [0, 4, 0, 0, 0, 0, 0, 0, 0]


def test_anchor_equations_card():
    ours = build_sdat(*_models())
    official = open(S_OFFICIAL, encoding="utf-8-sig").read()
    for kw, n in (("EQUA", 1), ("HSOL", 2), ("CYCS", 1), ("UNDR", 1)):
        assert _card(ours, kw, n) == _card(official, kw, n), kw
    assert _card(ours, "CYCT") is None
    assert _card(ours, "STED") is None
    # 值内容：3D+heat+层流+无扩散 -> 11111000；steady_param T 0.99 -> UNDR 5
    assert _card(ours, "EQUA")[0].strip() == "11111000"
    assert [x.split() for x in _card(ours, "HSOL", 2)] == [["1"], ["3", "1", "1"]]
    assert _card(ours, "CYCS")[0].split() == ["1", "100"]
    assert _card(ours, "UNDR")[0].split() == ["5", "9.90000000000000e-01"]


def test_anchor_radiation_sections():
    ours = build_sdat(*_models())
    official = open(S_OFFICIAL, encoding="utf-8-sig").read()
    for sec in ("VFEX", "HEATPATH"):
        assert _has(ours, sec) == _has(official, sec) is True
    assert _card(ours, "VFEX")[0].split() == ["1", "1"]


# ---- EQUA 8 位掩码 ------------------------------------------------------

def test_equa_mask_axis_bits(monkeypatch):
    """位1-3：轴向区间数>1 才解该方向动量方程（exB11 1000x1x1 实证）。"""
    model, props = _models()
    assert _card(build_sdat(model, props), "EQUA")[0].strip() == "11111000"
    axes2d = {"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0], "z": [0.0, 1.0, 2.0]}
    monkeypatch.setattr(model, "mesh_axes", lambda: axes2d)
    assert SExport(model, props)._equa_mask() == "10111000"
    assert _card(build_sdat(model, props), "EQUA")[0].strip() == "10111000"
    axes1d = {"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0], "z": [0.0, 1.0]}
    monkeypatch.setattr(model, "mesh_axes", lambda: axes1d)
    assert SExport(model, props)._equa_mask() == "10011000"


def test_equa_mask_physics_bits():
    # heat=0：位5 清零
    model, props = _models()
    _mut(model, "analysis_set/heat", text="0")
    assert SExport(model, props)._equa_mask() == "11110000"

    # 湍流开启：位6-7（k/eps）
    model, props = _models()
    _mut(model, "analysis_set/turbulence", text="1")
    assert SExport(model, props)._equa_mask() == "11111110"

    # 根级 <diffusion> 元素每个代表一个扩散物种：位8
    model, props = _models()
    ET.SubElement(model.root, "diffusion")
    ET.SubElement(model.root, "diffusion")
    assert SExport(model, props)._equa_mask() == "11111001"

    # mars 自由面 + mars_fluid_energy=1：位5=2（两流体能量方程）
    model, props = _models()
    _mut(model, "analysis_etc/free_surf/mars_fluid_energy", text="1")
    assert SExport(model, props)._equa_mask() == "11112000"


# ---- SDAT hdr2（配置计数行）---------------------------------------------

def test_hdr2_variants():
    model, props = _models()
    assert _hdr_rows(build_sdat(model, props))[1] == [0, 4, 0, 0, 0, 0, 0, 0, 0]

    # 湍流模型号 -> col3
    model, props = _models()
    _mut(model, "analysis_set/turbulence_model", text="5")
    assert _hdr_rows(build_sdat(model, props))[1] == [0, 4, 5, 0, 0, 0, 0, 0, 0]

    # flux 法辐射：col2=2 且无 VFEX 段
    model, props = _models()
    _mut(model, "analysis_set/radiation", attrib={"type": "flux"})
    s = build_sdat(model, props)
    assert _hdr_rows(s)[1][:3] == [0, 2, 0]
    assert _has(s, "VFEX") is False

    # 无辐射：col2=0
    model, props = _models()
    aset = model.root.find("analysis_set")
    aset.remove(aset.find("radiation"))
    assert _hdr_rows(build_sdat(model, props))[1] == [0] * 9

    # 扩散物种数 -> col1
    model, props = _models()
    for _ in range(2):
        ET.SubElement(model.root, "diffusion")
    assert _hdr_rows(build_sdat(model, props))[1][:3] == [2, 4, 0]


# ---- HSOL 门控与取值 -----------------------------------------------------

def test_hsol_values_and_gating(monkeypatch):
    # 值取 thermal_solver[0] / [1],[3],[4]
    model, props = _models()
    _mut(model, "analysis_set/thermal_solver", text="2,5,2,7,9,0")
    lines = _card(build_sdat(model, props), "HSOL", 2)
    assert [x.split() for x in lines] == [["2"], ["5", "7", "9"]]

    # heat=0 / compressive / 自由面：官方样本均无 HSOL 段
    for path, text in (("analysis_set/heat", "0"),
                       ("analysis_set/type", "compressive"),
                       ("analysis_etc/free_surf", "")):
        model, props = _models()
        _mut(model, path, text=text)
        assert _card(build_sdat(model, props), "HSOL") is None, path

    # 运动件（body_move）项目：官方样本无 HSOL 段
    model, props = _models()
    monkeypatch.setattr(SExport, "_has_moving_parts", lambda self: True)
    assert _card(build_sdat(model, props), "HSOL") is None


# ---- CYCS / CYCT ---------------------------------------------------------

def test_cycle_steady_variant():
    model, props = _models()
    _mut(model, "analysis_set/cycle", text="3,200")
    assert _card(build_sdat(model, props), "CYCS")[0].split() == ["3", "200"]


def _line_after(sdat, keyword, offset):
    lines = sdat.splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip() == keyword)
    return lines[i + offset]


def test_cycle_transient_variants():
    # 无 time_step：courant 自适应（第三值 1 + init_time_step/courant 行）
    model, props = _models()
    _mut(model, "analysis_set/calculation", text="transient")
    s = build_sdat(model, props)
    assert _card(s, "CYCS") is None
    assert _card(s, "CYCT")[0].split() == ["1", "100", "1"]
    vals = _line_after(s, "CYCT", 2).split()
    assert [float(v) for v in vals] == [0.01, 0.9]

    # 固定 time_step：第三值 -1 + 步长/输出间隔行
    model, props = _models()
    _mut(model, "analysis_set/calculation", text="transient")
    _mut(model, "analysis_set/time_step", text="0.05,3")
    s = build_sdat(model, props)
    assert _card(s, "CYCT")[0].split() == ["1", "100", "-1"]
    vals = _line_after(s, "CYCT", 2).split()
    assert [float(v) for v in vals] == [0.05, 3.0]


# ---- UNDR / STED ---------------------------------------------------------

def test_undr_sted_variants():
    model, props = _models()
    sp = model.root.find("steady_param")
    ET.SubElement(sp, "under_relax", {"type": "U"}).text = " 0.7,0,0 "
    ET.SubElement(sp, "conv_check", {"type": "T"}).text = " 100,1e-3 "
    s = build_sdat(model, props)
    lines = s.splitlines()
    undrs = [lines[i + 1].split() for i, l in enumerate(lines)
             if l.strip() == "UNDR"]
    # 原有 T 0.99 保留，追加 U 0.7（类型索引 U1 V2 W3 P4 T5）
    assert undrs == [["5", "9.90000000000000e-01"],
                     ["1", "7.00000000000000e-01"]]
    steds = [lines[i + 1].split() for i, l in enumerate(lines)
             if l.strip() == "STED"]
    assert steds == [["5", "100", "1.00000000000000e-03"]]


# ---- VFEX / HEATPATH 门控 ------------------------------------------------

def test_vfex_heatpath_gating():
    # 无辐射：无 VFEX
    model, props = _models()
    aset = model.root.find("analysis_set")
    aset.remove(aset.find("radiation"))
    assert _has(build_sdat(model, props), "VFEX") is False

    # VFEX 首值 = radiation/method
    model, props = _models()
    _mut(model, "analysis_set/radiation/method", text="2")
    assert _card(build_sdat(model, props), "VFEX")[0].split() == ["2", "1"]

    # heat_path=0：无 HEATPATH 段（exA01-1 实证）
    model, props = _models()
    _mut(model, "analysis_set/heat_path", text="0")
    assert _has(build_sdat(model, props), "HEATPATH") is False

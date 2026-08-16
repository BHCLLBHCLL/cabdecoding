"""M45 / R9-B: cut-cell 网格生成器测试。

覆盖（对应验收标准）：

1. 开关+阈值持久化 —— cab_options.cutcell_settings 的 QSettings 往返
   （假 QSettings 替身，避免测试写注册表）、钳制与坏值回退，
   OptionsDialog Mesh 页控件 -> values() -> 保存 -> 读回；
2. 边界格体积分数分类 —— cell_volume_fractions 解析交（对齐盒精确解、
   守恒性）、classify_part_cells_cut 按手册 [Criteria] 判据二值化、
   classify_cells 的 cutcell=True/False 路径与分数表返回；
3. 关闭时零回归 —— cutcell=False（含显式传 criteria）与缺省调用结果
   逐位一致，网格对齐盒两种模式同盒；panel / 圆柱坐标不走 cut 路径；
4. .s 发射 —— 零件级 <cutcell> 注册后发射 CUTCELL_OPTION/CUTCELL_GAP
   段（criteria 缺省 0.05 / 样本值 0.005），取消注册后无该段。

考证依据：手册 Cutcell_Setting.html（Criteria 0<c<1，默认 0.05）与
官方样本 exA23-2b_cut_cell_e.s / exA23-2b_cut_cell.cab（详见
cab_mesh.py / s_export.py 模块注释）。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest

import cab_mesh

ROOT = Path(__file__).resolve().parents[1]
BOX_CAB = ROOT / "tests" / "box.cab"
EX4_CAB = ROOT / "tests" / "ex4_e.cab"


def _box_part(name: str = "box", lo: float = 0.5, hi: float = 5.5):
    """轴对齐立方体零件（mm 顶点 -> 米），默认错位边界 0.5..5.5 mm。"""
    from cab_parts import PrimitivePart
    # 顶点序与标准 12 三角形的面索引严格匹配（同 tests/test_e1_export
    # ._cube：每个 z 切片内 (x,y) 按 (0,0),(1,0),(1,1),(0,1) 环序）。
    # 枚举序错位会造成扭曲四边形，破坏射线分类的奇偶翻转。
    a, b = lo / 1000.0, hi / 1000.0
    pts = np.array([
        [a, a, a], [b, a, a], [b, b, a], [a, b, a],
        [a, a, b], [b, a, b], [b, b, b], [a, b, b]], float)
    tris = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], int)
    return PrimitivePart(name, pts, tris)


def _axes(n: int = 10) -> dict:
    """0..n mm 均匀 1 mm 网格（mm；classify_cells 内部转米）。"""
    return {ax: [i * 1.0 for i in range(n + 1)] for ax in "xyz"}


def _edges_m(n: int = 10) -> list:
    """米制格边界表（0..n mm，1 mm 格）。"""
    return [np.arange(n + 1.0) / 1000.0 for _ in range(3)]


# ---- 1. 阈值钳制 ---------------------------------------------------------

def test_clamp_cutcell_criteria():
    # 手册范围 [1e-10, 0.9999]，默认 0.05
    assert cab_mesh.CUTCELL_CRITERIA_DEFAULT == pytest.approx(0.05)
    assert cab_mesh.clamp_cutcell_criteria(0.2) == pytest.approx(0.2)
    assert cab_mesh.clamp_cutcell_criteria(-1.0) == pytest.approx(1e-10)
    assert cab_mesh.clamp_cutcell_criteria(2.0) == pytest.approx(0.9999)
    # 坏值回退默认
    assert cab_mesh.clamp_cutcell_criteria("abc") == pytest.approx(0.05)
    assert cab_mesh.clamp_cutcell_criteria(None) == pytest.approx(0.05)


# ---- 2. 体积分数解析交 ---------------------------------------------------

def test_cell_volume_fractions_unaligned_box():
    edges = _edges_m()
    lo = np.array([0.0005, 0.0005, 0.0005])   # 盒 0.5..5.5 mm
    hi = np.array([0.0055, 0.0055, 0.0055])
    fr = cab_mesh.cell_volume_fractions(*edges, lo, hi)
    assert fr.shape == (10, 10, 10)
    # 内部格（0-based 1..4 每轴）全满
    assert fr[1:5, 1:5, 1:5].min() == 1.0
    # 边界壳层：角格 1/2^3，棱/面格 1/2（三轴分数 0.5 的乘积）
    assert fr[0, 0, 0] == pytest.approx(0.125)
    assert fr[0, 1, 1] == pytest.approx(0.5)
    assert fr[5, 5, 5] == pytest.approx(0.125)
    # 完全在外为 0
    assert fr[6:, :, :].max() == 0.0
    # 守恒：Σ分数 × 格体积 = 盒体积（5mm 立方 = (5e-3)^3 m^3）
    assert fr.sum() == pytest.approx(125.0)
    assert fr.sum() * (1e-3) ** 3 == pytest.approx((5e-3) ** 3)


def test_cell_volume_fractions_grid_aligned_box():
    edges = _edges_m()
    lo = np.array([0.001, 0.001, 0.001])      # 盒 1..5 mm（贴格线）
    hi = np.array([0.005, 0.005, 0.005])
    fr = cab_mesh.cell_volume_fractions(*edges, lo, hi)
    # 对齐盒无部分格：内部 1.0，其余恰好 0（面接触为零测度交）
    assert set(np.unique(fr)) <= {0.0, 1.0}
    assert fr.sum() == pytest.approx(64.0)    # 4^3 全满格


# ---- 3. cut-cell 二值化分类 ----------------------------------------------

def test_classify_part_cells_cut_thresholds():
    edges = _edges_m()
    lo = np.array([0.0005] * 3)
    hi = np.array([0.0055] * 3)
    # criteria 0.05：solid 仅近满格（0-based 1..4 每轴 -> 4^3=64）
    mask, fr = cab_mesh.classify_part_cells_cut(
        *edges, lo, hi, criteria=0.05)
    assert mask.sum() == 64
    assert mask[1, 1, 1] and mask[4, 4, 4]
    assert not mask[0, 0, 0] and not mask[5, 5, 5]
    assert np.array_equal(mask, fr >= 1.0 - 0.05)
    # criteria 0.6 -> 门槛 0.4：恰一轴 0.5 的格也记 solid（近似楼梯
    # 中点二值化）。避开 criteria=0.5 的浮点刀刃（分数 0.5±1e-13 vs
    # 门槛恰 0.5）：全满 4^3=64 + 恰一轴边界 3*2*4*4=96 -> 160
    mask2, _ = cab_mesh.classify_part_cells_cut(
        *edges, lo, hi, criteria=0.6)
    assert mask2.sum() == 160
    # criteria 钳制：负值 -> 下限 1e-10（仅全满格）；>1 -> 上限 0.9999
    mask3, _ = cab_mesh.classify_part_cells_cut(
        *edges, lo, hi, criteria=-1.0)
    assert mask3.sum() == 64
    mask4, _ = cab_mesh.classify_part_cells_cut(
        *edges, lo, hi, criteria=2.0)
    assert mask4.sum() == 216                 # 门槛 1e-4：所有触碰格
    # 盒外远处的格永不占用
    assert not mask[9, 9, 9]


# ---- 4. classify_cells 开关路径（开/关/零回归） ---------------------------

def test_classify_cells_cutcell_switch():
    tess = _box_part()
    axes = _axes()
    default = cab_mesh.classify_cells(axes, [tess])
    off = cab_mesh.classify_cells(axes, [tess], cutcell=False,
                                  cutcell_criteria=0.9)
    # 关闭时零回归：显式 off（含 criteria 参数）与缺省调用逐位一致
    assert len(default) == 2 and len(off) == 2
    assert off == default
    # 开启：三元组返回，分数表按零件名索引
    on = cab_mesh.classify_cells(axes, [tess], cutcell=True,
                                 return_cutcell=True)
    assert len(on) == 3
    _a, boxes, fracs = on
    f = fracs["box"]
    assert f.shape == (10, 10, 10)
    # solid 盒只含近满格（0-based 1..4 -> 1-based 2..5）
    assert boxes["box"] == [(2, 5, 2, 5, 2, 5)]
    mask = cab_mesh.cell_mask_from_boxes(10, 10, 10, boxes["box"])
    assert np.array_equal(mask, f >= 0.95)
    # 分数表承载边界部分占用：触碰壳层 6^3 - 内部 4^3 = 152 个 cut cell
    boundary = (f > 1e-12) & (f < 1.0 - 1e-12)
    assert boundary.sum() == 152
    # 开启但不要求分数表：保持二元组返回（既有调用兼容）
    two = cab_mesh.classify_cells(axes, [tess], cutcell=True)
    assert len(two) == 2
    assert two[1]["box"] == [(2, 5, 2, 5, 2, 5)]


def test_cutcell_grid_aligned_matches_staircase():
    """格线对齐盒：cut-cell 与楼梯（射线）分类结果相同。"""
    tess = _box_part(lo=1.0, hi=5.0)
    axes = _axes()
    _a, boxes_off = cab_mesh.classify_cells(axes, [tess])
    _a2, boxes_on, fracs = cab_mesh.classify_cells(
        axes, [tess], cutcell=True, cutcell_criteria=0.05,
        return_cutcell=True)
    assert boxes_off == boxes_on == {"box": [(2, 5, 2, 5, 2, 5)]}
    assert set(np.unique(fracs["box"])) <= {0.0, 1.0}


def test_cutcell_panel_part_skips_cut_path():
    """panel（开放面）零件不走 cut 路径：仍用面薄带分类。"""
    from cab_parts import PrimitivePart
    pts = np.array([[2, 2, 5], [8, 2, 5], [8, 8, 5], [2, 8, 5]],
                   float) / 1000.0
    tris = np.array([[0, 1, 2], [0, 2, 3]], int)
    plate = PrimitivePart("plate", pts, tris)
    _a, boxes, fracs = cab_mesh.classify_cells(
        _axes(), [plate], part_kinds={"plate": "panel"},
        cutcell=True, return_cutcell=True)
    assert fracs == {}                        # panel 无 cut 分数
    assert "plate" in boxes                   # 面薄带占用仍生成


def test_cutcell_cylindrical_skips_cut_path():
    """圆柱坐标格不走 cut 路径（分数仅对笛卡尔格有解析交）。"""
    from cab_parts import PrimitivePart
    nlon = 8
    th = np.linspace(0, 2 * np.pi, nlon, endpoint=False)
    pts = []
    for z in (0.02, 0.08):
        for t in th:
            pts.append([10 * np.cos(t), 10 * np.sin(t), z])
    tris = []
    for i in range(nlon):
        j = (i + 1) % nlon
        tris.append([i, j, nlon + i])
        tris.append([j, nlon + j, nlon + i])
    cyl = PrimitivePart("cyl", np.array(pts, float) / 1000.0,
                        np.array(tris, int))
    axes = {"x": np.linspace(0, 20, 5).tolist(),
            "y": np.linspace(0, 360, 5).tolist(),
            "z": np.linspace(0, 100, 5).tolist()}
    _a, _b, fracs = cab_mesh.classify_cells(
        axes, [cyl], coordinate="cylindrical",
        cutcell=True, return_cutcell=True)
    assert fracs == {}


# ---- 5. 零件级注册（工程级 XML 标记） -------------------------------------

def _box_model():
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre
    archive = CabArchive.parse(BOX_CAB.read_bytes())
    archive.fill_member_data()
    xml_name = next(m.name for m in archive.members
                    if m.name.endswith(".xml") and not m.name.startswith("_"))
    member = next(m for m in archive.members if m.name == xml_name)
    return StpreModel(parse_stpre(member.data))


def test_part_cutcell_registration_roundtrip():
    from cabxml import StpreModel, parse_stpre
    model = _box_model()
    assert not cab_mesh.part_cutcell_enabled(model, "box")
    # 注册：样本实证格式 <parts> 下 <cutcell> T </cutcell>
    assert cab_mesh.set_part_cutcell(model, "box", True)
    assert cab_mesh.part_cutcell_enabled(model, "box")
    cc = model.find_part("box").find("cutcell")
    assert cc is not None and cc.text.strip().upper() == "T"
    # 序列化往返保持注册
    again = StpreModel(parse_stpre(model.doc.serialize()))
    assert cab_mesh.part_cutcell_enabled(again, "box")
    # 取消注册：删除子节点
    assert cab_mesh.set_part_cutcell(model, "box", False)
    assert not cab_mesh.part_cutcell_enabled(model, "box")
    assert model.find_part("box").find("cutcell") is None
    # 未知零件 -> False
    assert not cab_mesh.set_part_cutcell(model, "no_such", True)
    assert not cab_mesh.part_cutcell_enabled(model, "no_such")


# ---- 6. 应用偏好持久化（QSettings 假替身） --------------------------------

class _MemSettings:
    """QSettings 替身：进程内字典，避免测试写宿主注册表。"""
    store: dict = {}

    def __init__(self, org, app):
        pass

    def value(self, key, default=None):
        return self.store.get(key, default)

    def setValue(self, key, v):
        self.store[key] = v


@pytest.fixture()
def mem_settings(monkeypatch):
    import cab_options
    monkeypatch.setattr(cab_options, "QSettings", _MemSettings)
    monkeypatch.setattr(cab_options, "_MEM", {})
    monkeypatch.setattr(_MemSettings, "store", {})
    return cab_options


def test_cutcell_settings_persistence(mem_settings):
    cab = mem_settings
    # 缺省：开关关 + 手册默认 0.05
    assert cab.cutcell_settings() == (False, pytest.approx(0.05))
    # 持久化往返
    cab.set_setting("cutcell_enable", True)
    cab.set_setting("cutcell_criteria", 0.123)
    assert cab.cutcell_settings() == (True, pytest.approx(0.123))
    # 坏值 -> 默认阈值（开关保持）
    cab.set_setting("cutcell_criteria", "abc")
    enable, crit = cab.cutcell_settings()
    assert enable is True and crit == pytest.approx(0.05)
    # 越界 -> 钳制到手册范围
    cab.set_setting("cutcell_criteria", 5.0)
    assert cab.cutcell_settings()[1] == pytest.approx(0.9999)
    cab.set_setting("cutcell_criteria", -1.0)
    assert cab.cutcell_settings()[1] == pytest.approx(1e-10)
    # 布尔解析（QSettings 可能回读字符串）
    assert cab._to_bool("True") and cab._to_bool("t") and cab._to_bool(1)
    assert not cab._to_bool("False") and not cab._to_bool("")


def test_options_dialog_cutcell_controls(qapp, mem_settings):
    """Mesh 页控件：缺省值、范围、values() 与保存往返。"""
    cab = mem_settings
    dlg = cab.OptionsDialog()
    assert not dlg.cutcell_enable.isChecked()          # 缺省关
    assert dlg.cutcell_criteria.value() == pytest.approx(0.05)
    assert dlg.cutcell_criteria.minimum() <= 1e-10     # 手册范围
    assert dlg.cutcell_criteria.maximum() >= 0.9999
    # 修改 -> values() -> 保存 -> 读回
    dlg.cutcell_enable.setChecked(True)
    dlg.cutcell_criteria.setValue(0.2)
    vals = dlg.values()
    assert vals["cutcell_enable"] is True
    assert vals["cutcell_criteria"] == pytest.approx(0.2)
    dlg._save_and_accept()
    assert cab.cutcell_settings() == (True, pytest.approx(0.2))


# ---- 7. .s 导出 CUTCELL 段 ------------------------------------------------

def _ex4_models():
    from cab_container import CabArchive
    from cabxml import PropertyModel, StpreModel, parse_property, parse_stpre
    arch = CabArchive.parse(EX4_CAB.read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    return (StpreModel(parse_stpre(members["ex4_e.xml"])),
            PropertyModel(parse_property(members["_ex4_e_property.xml"])))


def test_s_export_cutcell_sections():
    from s_export import SExport
    model, props = _ex4_models()
    # 基线（无注册）：无 CUTCELL 段
    base = SExport(model, props).render()
    assert "CUTCELL_OPTION" not in base
    assert "CUTCELL_GAP" not in base
    # 注册首个零件 + analysis_set criteria（样本值 0.005）
    name = model.parts()[0].name
    assert cab_mesh.set_part_cutcell(model, name, True)
    model.set_analysis_set_value("cutcell_criteria", "0.005")
    lines = SExport(model, props).render().splitlines()
    i = lines.index("CUTCELL_OPTION")
    assert lines[i + 1] == "volume_min_ratio"
    assert lines[i + 2].strip() == "5.00000000000000e-03"
    assert lines[i + 3] == "thin_shape_model"
    assert lines[i + 4].strip() == "1"            # cutcell_thin_model 缺省
    assert lines[i + 5] == "/"
    j = lines.index("CUTCELL_GAP")
    assert lines[j + 1].split() == ["-1", "-1"]   # 样本唯一观测值
    assert lines[j + 2] == "/"
    # 取消注册 -> 零回归（回到无 CUTCELL 段）
    assert cab_mesh.set_part_cutcell(model, name, False)
    again = SExport(model, props).render()
    assert "CUTCELL_OPTION" not in again
    assert "CUTCELL_GAP" not in again


def test_s_export_cutcell_default_criteria():
    """analysis_set 无 cutcell_criteria 时按手册默认 0.05 发射。

    ex4_e.cab 的 analysis_set 自带样本值 0.005，先删除该子节点再验证
    缺省路径。
    """
    from s_export import SExport
    model, props = _ex4_models()
    aset = model.root.find("analysis_set")
    if aset is not None:
        el = aset.find("cutcell_criteria")
        if el is not None:
            aset.remove(el)
    name = model.parts()[0].name
    assert cab_mesh.set_part_cutcell(model, name, True)
    lines = SExport(model, props).render().splitlines()
    i = lines.index("CUTCELL_OPTION")
    assert lines[i + 2].strip() == "5.00000000000000e-02"


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app

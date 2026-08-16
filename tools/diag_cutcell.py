# -*- coding: utf-8 -*-
"""R9-B 诊断：cut-cell 设置与分类检查（离线，不依赖 STpre COM）。

用法::

    python tools/diag_cutcell.py             # options 偏好 + 合成盒演示
    python tools/diag_cutcell.py model.cab   # 追加：cab 工程的注册状态
                                            #   与首个 solid 零件的分数统计

输出：

- 应用级 cut-cell 偏好（QSettings：开关 + criteria）；
- 合成对齐盒在 10x10x10 均匀网格上的边界格分数（开启前后分类对比）；
- 指定 cab 时：零件级 <cutcell> 注册列表 + analysis_set cutcell_* 值
  + .s 发射判定（有无零件注册）。

考证依据（手册 + 官方样本）：
- HTML_STpre_Eng/Cutcell_Setting.html（Criteria 范围/默认 0.05）；
- Exercise_e/Function/exA23-2/exA23-2b_cut_cell_e.s（CUTCELL_OPTION 段）；
- exA23-2b_cut_cell.cab XML（<parts> 下 <cutcell> T 注册）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402


def demo_cutcell_classification(criteria: float) -> None:
    """合成对齐盒：域 0..10 mm，盒 0.5..5.5 mm，均匀 1 mm 格。"""
    import cab_mesh
    edges = [np.arange(11.0) / 1000.0 for _ in range(3)]   # 米制边界
    lo = np.array([0.0005, 0.0005, 0.0005])
    hi = np.array([0.0055, 0.0055, 0.0055])
    mask, fracs = cab_mesh.classify_part_cells_cut(
        *edges, lo, hi, criteria=criteria)
    interior = fracs >= 1.0 - 1e-12
    outside = fracs <= 1e-12
    boundary = (fracs > 1e-12) & (fracs < 1.0 - 1e-12)
    print(f"  criteria={criteria:g}")
    print(f"  内部格(=1.0): {int(interior.sum())}  "
          f"外部格(=0.0): {int(outside.sum())}  "
          f"边界格(0<f<1): {int(boundary.sum())}")
    vals = sorted(set(np.round(fracs[boundary], 6).tolist()))
    print(f"  边界格分数值: {vals}")
    print(f"  solid 掩码格数 (frac>=1-criteria): {int(mask.sum())} / "
          f"{fracs.size}")
    # 关闭路径对照：射线分类同一盒（对齐盒零件两者应接近）。
    # 顶点序与标准 12 三角形面索引严格匹配（同 tests/test_e1_export
    # ._cube：每个 z 切片内 (x,y) 环序）。
    from cab_parts import PrimitivePart
    a, b = 0.0005, 0.0055
    pts = np.array([
        [a, a, a], [b, a, a], [b, b, a], [a, b, a],
        [a, a, b], [b, a, b], [b, b, b], [a, b, b]], float)
    tris = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], int)
    tess = PrimitivePart("box", pts, tris)
    axes = {ax: [i * 1.0 for i in range(11)] for ax in "xyz"}
    _ab, boxes_ray = cab_mesh.classify_cells(axes, [tess])
    n_ray = sum((b[1] - b[0] + 1) * (b[3] - b[2] + 1) * (b[5] - b[4] + 1)
                for b in boxes_ray.get("box", []))
    print(f"  对照(关闭开关, 射线分类) solid 格数: {n_ray}")


def dump_options() -> None:
    try:
        import cab_options
    except Exception as exc:      # PyQt5 缺失时仅提示
        print(f"[options] 无法导入 cab_options: {exc}")
        return
    enable, crit = cab_options.cutcell_settings()
    print(f"[options] cut-cell 开关={enable}  criteria={crit:g} "
          f"(QSettings keys: cutcell_enable / cutcell_criteria)")


def dump_cab(path: str) -> None:
    import cab_mesh
    from cab_container import CabArchive
    from cabxml import StpreModel, parse_stpre

    arch = CabArchive.parse(Path(path).read_bytes())
    members = {m.name: m.data for m in arch.fill_member_data()}
    xml_name = next((n for n in members if n.lower().endswith(".xml")), None)
    if xml_name is None:
        print(f"[cab] {path}: 无 XML 成员，跳过")
        return
    model = StpreModel(parse_stpre(members[xml_name]))
    print(f"[cab] {path}")
    for v in ("cutcell_criteria", "cutcell_all_gap",
              "cutcell_wall_model", "cutcell_thin_model"):
        val = model.analysis_set_value(v, "(缺省)")
        print(f"  analysis_set/{v} = {val}")
    registered = []
    for p in model.parts():
        if cab_mesh.part_cutcell_enabled(model, p.name):
            registered.append(p.name)
    if registered:
        print(f"  cut-cell 注册零件: {registered}")
        print("  => .s 将发射 CUTCELL_OPTION/CUTCELL_GAP 段")
    else:
        print("  cut-cell 注册零件: (无)")
        print("  => .s 不发射 CUTCELL 段（对照 staircase 样本行为）")


def main() -> None:
    print("== R9-B cut-cell 诊断 ==")
    dump_options()
    print("[demo] 合成对齐盒（域 0..10mm，盒 0.5..5.5mm，1mm 格）")
    import cab_mesh
    demo_cutcell_classification(
        cab_mesh.CUTCELL_CRITERIA_DEFAULT)
    demo_cutcell_classification(0.5)      # 楼梯近似（中点二值化）
    demo_cutcell_classification(0.001)    # 几何保真（solid 仅近满格）
    for arg in sys.argv[1:]:
        dump_cab(arg)


if __name__ == "__main__":
    main()

# FEM 元素 kind 活体探针（F6 / D10）

工具：`tools/probe_fem_kinds.py`（本机 STpre 2025.2 COM 实机）。
产物：`data/fem_kind_probe.json`。

## 结论

| 源几何 | COM 创建器 | FEM 输出 | kind | 单元数 | 每单元节点 |
|---|---|---|---:|---:|---:|
| 实体立方体（length=2.0） | `CreateCubeModel` | `fem_FemBox` | 4 | 532 | 4 |
| 实体立方体（length=1.0） | `CreateCubeModel` | `fem_FemBoxFine` | 4 | 2822 | 4 |
| 实体圆柱 | `CreateCylinderModel` | `fem_FemCyl` | 4 | 296 | 4 |
| Panel（板） | `CreatePanelModel` | **无 .xfem** | — | — | — |
| Hexa | `CreateHexaModel` | 参数表未解析（7/8/9 参均报“无效的参数数目”） | — | — | — |

- 实体件 → 仅 `kind="4"`（4 节点四面体）；加密会增大单元数而 kind 不变。
- **Panel 件不产生 FEM 输出**（无 .xfem 成员），即 STpre 的 FEM 转换
  不生成壳单元。
- 无六面体单元路径可观测。

## 定档（§22.0 B 级）

本仓 `.xfem` 只写 tet4 **与 STpre 实测行为一致**——“缺壳/六面体单元”
不是能力缺口，而是 STpre 自身没有该输出路径。维度 D10 由 75% 闭合为
**A（离线 Delaunay/tet4）+ B（壳/六面体实证定档）**。

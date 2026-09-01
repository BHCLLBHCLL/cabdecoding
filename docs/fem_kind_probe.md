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

## D9：COM B 层活体探针（附带产物）

工具：`tools/probe_com_b_layer.py`（只读语义验证）。
产物：`data/com_b_probe.json`。

一次开档（ex4_e.cab）内对 VB 手册目录的每个成员做非破坏性访问：
`Get*/Is*/Has*/Count*` 无参调用、属性读取、其余（Set*/Delete*/Create*/
Open/Save/Close/Quit…）按 §22 规则跳过（破坏性成员需沙箱副本逐调用隔离）。

实测汇总（719 目录成员）：

| 状态 | 数量 | 含义 |
|---|---:|---|
| ok | 177 | 活体语义验证通过 |
| error | 45 | 需参数/上下文（记入报告，属“不可 headless 终证”） |
| skip | 440 | 破坏性或参数依赖（按计划隔离/排除） |
| no-object | 57 | 该类活对象未取得（MeshBlock/Sketch/Property/Table 等） |

这是 §22 C 级口径所需的“终证率公示”第一批数据：包装覆盖 A 层仍为
100%，B 层本批终证 177 项；no-object 的四类（MeshBlock 无手册类页、
Sketch/Property/Table 需专用获取路径）列为下一批探针目标。

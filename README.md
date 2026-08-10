# cabdecoding

decode cradle scstream cab project file decoding

解析 Cradle scSTREAM Pre 项目文件 `.cab`（Microsoft Cabinet 容器 +
MSZIP 压缩 + XML 设置 + Parasolid 几何）。完整格式说明见
[CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)；开发规划与当前状态见
[DEV_SUMMARY.md](DEV_SUMMARY.md)；功能补齐开发计划见
[DEV_PLAN.md](DEV_PLAN.md)。

## 功能（2026-08-08）

- 打开/保存/另存 `.cab`，导出 `.s` + `.xemt`；
- `File → Import…` 导入几何：`.x_t`（原生 Parasolid）、`.stl` / `.obj`
  （polygon）、`.step/.stp` 与 `.sat/.sab`（经 OpenCascade/OCC
  三角化，需 `pip install OCP`）、以及有限的 `.dxf` / `.mdl`。
  **IGES / IDF 不支持**——请改用 STEP（OCC）或 Parasolid XT，或在上游
  CAD 转出 STL/OBJ（决策见 `DEV_PLAN.md` §15.6）；
- `Edit → Reset Computational Domain` 设置计算域（坐标类型/单位/
  min-max/材料/CAD Data Size/Extend/Preview）；
- `Mesh` 菜单 6 项齐全：`Gridding`（六标签 `Mesh:Set division`）、
  `Meshing`（element 占用）、`Checking Parts Interferences`
  （Interference/Contact/Separation + Reconstruct）、`Editing Mesh`
  （I/J/K 层有效/无效编辑）、`Showing Element Cross-Section`（实时截面）、
  `Checking S-File`（S 文件部件/区域勾选显隐）；
  - 可选 `Gridding/Meshing via STpre API`（默认关闭）：开启后经
    `STpre_Bx64net.Application.2025` COM 自动化调用 STpre 原生
    gridding/meshing，结果通过临时 cab 文件中转合并回内存模型；
- `Wizard → Initial Setting`：完整 Initial Wizard（Project→Import
  CAD→Computational Domain→Analysis Type→Initial Value/Gravity→
  Purpose→Boundary→Confirm）；`Wizard → Condition Setting`：Condition
  Wizard 子集（导航树 + Analysis Types/Basic/Fluid/Flow/Heat/Initial/
  BC/Analysis Control/File/Condition List/Confirm）；
- `File`：Print（Draw 截图/系统打印）、Execute Solver/Post（启动
  `stsol` / `scPOST`——需本机 Cradle；详见 `DEV_PLAN.md` §15.6）、
  Export（`.s`/`.xemt`/STL/XT/Property）；`Edit`：Undo/Redo
  （Ctrl+Z/Y 快照栈）、Deletion of Parts、Group；`Part`：含 AC Unit /
  Diffuser 代理在内的多种部件（3D 预览，重开按 XML 参数重建）；
  `Option`：Environment/Detailed Program Settings（QSettings 持久化）；
  `Help`：Version（含 pskernel 内核版本）；
- Sketch plane：Control Window [Sketch] 页设置原点/网格（Reset Zmin /
  Fit to domain / Update），Draw 窗口显示平面网格与 U/V/W 轴；
- 3D：Part shading（光滑曲面）、Element division 网格线、域框/网格块预览、
  单元截面。

操作提示：在 Layout of Parts 树中**双击 `Domain(cuboid)`**（或右键
`Reference`）即可编辑计算域；双击 `RootBlock` 打开 Gridding。

## 操作流程

```text
（无参数启动自动创建空工程；也可 File→New… / Ctrl+N）
File→Open 打开 cab（或新建后导入）
  → File→Import… 导入 x_t
  → Edit→Reset Computational Domain（可用 CAD Data Size 自动取包围盒）
  → Mesh→Gridding（生成网格坐标）
  → Mesh→Meshing（生成部件占用）
  → Mesh→Checking Parts Interferences / Editing Mesh / Cross-Section 校验微调
  → Wizard→Initial Setting / Condition Setting 设置求解条件
  → File→Export 导出 .s / .xemt
```

依赖：Cradle CFD 2025.2 `Programs_x64`（pskernel.dll）提供 Parasolid
接收/三角化；无 Cradle 时回退 GO 路径或仅显示网格盒。STEP/SAT 另需
`OCP`。Solver/Post 仅启动外部 Cradle 可执行文件，不内嵌求解/后处理。

## 格式支持摘要

| | 支持 | 不支持 |
|---|---|---|
| Import | XT, STL, OBJ, STEP, SAT, DXF, MDL | **IGES, IDF**（用 STEP/XT） |
| Export | S, XEMT, STL, XT, Property XML | Neutral 全矩阵 |

回归：`tests/test_m38_format_matrix.py`（OBJ/STL roundtrip；XT 有
pskernel 时；IGES/IDF 显式拒绝）。

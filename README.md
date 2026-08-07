# cabdecoding

decode cradle scstream cab project file decoding

解析 Cradle scSTREAM Pre 项目文件 `.cab`（Microsoft Cabinet 容器 +
MSZIP 压缩 + XML 设置 + Parasolid 几何）。完整格式说明见
[CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)；开发规划与当前状态见
[DEV_SUMMARY.md](DEV_SUMMARY.md)；功能补齐开发计划见
[DEV_PLAN.md](DEV_PLAN.md)。

## 功能（2026-08-08）

- 打开/保存/另存 `.cab`，导出 `.s` + `.xemt`；
- `File → Import…` 导入 Parasolid `.x_t`（独立成员 + `<body_files>`
   登记），导入后自动三角化（`PK_TOPOL_facet_2` 表路径 + 自适应局部容差）
   并刷新 3D；
- `Edit → Reset Computational Domain` 设置计算域（坐标类型/单位/
  min-max/材料/CAD Data Size/Extend/Preview）；
- `Mesh` 菜单 6 项齐全：`Gridding`（六标签 `Mesh:Set division`）、
  `Meshing`（element 占用）、`Checking Parts Interferences`
  （Interference/Contact/Separation + Reconstruct）、`Editing Mesh`
  （I/J/K 层有效/无效编辑）、`Showing Element Cross-Section`（实时截面）、
  `Checking S-File`（S 文件部件/区域勾选显隐）；
- `Wizard → Initial Setting`：完整 Initial Wizard（Project→Import
  CAD→Computational Domain→Analysis Type→Initial Value/Gravity→
  Purpose→Boundary→Confirm）；`Wizard → Condition Setting`：Condition
  Wizard 子集（导航树 + Analysis Types/Basic/Fluid/Flow/Heat/Initial/
  BC/Analysis Control/File/Condition List/Confirm）；
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
接收/三角化；无 Cradle 时回退 GO 路径或仅显示网格盒。

# cabdecoding

decode cradle scstream cab project file decoding

解析 Cradle scSTREAM Pre 项目文件 `.cab`（Microsoft Cabinet 容器 +
MSZIP 压缩 + XML 设置 + Parasolid 几何）。完整格式说明见
[CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)；开发规划与当前状态见
[DEV_SUMMARY.md](DEV_SUMMARY.md)；功能补齐开发计划见
[DEV_PLAN.md](DEV_PLAN.md)。

## 功能（2026-08-06）

- 打开/保存/另存 `.cab`，导出 `.s` + `.xemt`；
- `File → Import…` 导入 Parasolid `.x_t`（独立成员 + `<body_files>`
  登记），导入后自动三角化（`PK_TOPOL_facet_2` 表路径 + 自适应局部容差）
  并刷新 3D；
- `Edit → Reset Computational Domain` 设置计算域（坐标类型/单位/
  min-max/材料/CAD Data Size/Extend/Preview）；
- `Mesh → Gridding` 生成 `mesh_control` + `mesh_block`（顶点检测、
  标准长度/几何比/目标单元数）；
- `Mesh → Meshing` 基于三角化曲面生成 `element` 占用盒表；
- 3D：Part shading（光滑曲面）、Element division 网格线、域框/网格块预览。

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
  → File→Export 导出 .s / .xemt
```

依赖：Cradle CFD 2025.2 `Programs_x64`（pskernel.dll）提供 Parasolid
接收/三角化；无 Cradle 时回退 GO 路径或仅显示网格盒。

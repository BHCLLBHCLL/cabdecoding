# cab_gui 功能补齐开发计划（逆向驱动）

> 日期：2026-08-06
> 仓库：`cabdecoding`
> 关联文档：[CAB_GUI_DESIGN.md](CAB_GUI_DESIGN.md)（UI 布局）、
> [DEV_SUMMARY.md](DEV_SUMMARY.md)（逆向档案）、
> [CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)（cab 格式规范）
> 参考手册：`C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\Pre_eng\index.html`

---

## 1. 背景与目标

当前 `cab_gui.py` 已完成 STpre 布局骨架、CAB 读写、x_t 三角化显示、`.s/.xemt`
导出，但 File→Import、计算域设置、Gridding、Meshing 等关键菜单仍是 NYI
占位。本计划的目标是把这些功能补齐为**可用闭环**：

1. **导入 x_t 文件**（File→Import，XT/STL 先行）并持久化回 cab；
2. **x_t 三角化**：导入后自动生成光滑曲面并刷新 3D（复用已逆向的
   `PK_TOPOL_facet_2` 表路径 + adaptive 局部容差）；
3. **设置 computational domain**（坐标类型/单位/范围/域材料/自动包围盒/
   3D 预览）；
4. **gridding**：按手册的顶点检测 + 粗网格 + 细网格（标准长度/几何比/
   单元数）生成 `mesh_block` 与 `mesh_control`；
5. **meshing**：基于三角化曲面生成 `element` 部件盒表与 Domain 盒表，
   打通“导入 → 网格 → 导出 S 文件”全流程。

约束：优先保证**结构/语义可用**（cab 重开一致、`.s` 可被 flddecoding 消费），
再逐步逼近与 STpre 官方输出的一致性；不依赖 STpre 的 GUI/许可进行自动化。

---

## 2. 现状盘点

### 2.1 已有能力（复用基础）

| 能力 | 位置 | 说明 |
|---|---|---|
| CAB 容器解析/写回 | `cab_container.py` | MSCF+MSZIP，round-trip 逐字节稳定 |
| XML 模型 | `cabxml.py` | `StpreModel`：parts/groups/regions/values/conditions/`mesh_axes()`/`part_boxes()`/`analysis_boxes()`；`PropertyModel`：材料库 |
| 导出 | `s_export.py` / `xemt_export.py` | `build_sdat(model, props)`、`build_emt(model, props)` |
| x_t 三角化 | `ps_facet2_nodes.py` | `PK_TOPOL_facet_2` 表路径（STpre 同源）+ `adaptive=True` 每 face 局部容差；`ps_tessellate.py` GO 回退 |
| 3D | `cab_vtk.py` | 点法线/锐边拆分/变换/域框/网格线/Element division |
| GUI | `cab_gui.py` + `cab_panes.py` | 四窗格、菜单/工具栏、属性编辑、Message/Status |

### 2.2 缺口清单（本次要补齐）

| 菜单 | 现状 | 目标 |
|---|---|---|
| File→Import… | NYI | XT/STL 导入对话框；后续扩展 MDL/DXF/OBJ/STEP |
| Edit→Reset Computational Domain | 只读显示属性 | 完整域设置对话框（见 §6.2） |
| Mesh→Gridding | 只读摘要 | Basic Settings/Parameters 子集对话框 + 网格生成 |
| Mesh→Meshing | NYI | 基于现有网格生成 element，进度/日志 |
| Mesh→Editing Mesh | NYI | 网格参数查看/编辑（一期只读+简单改坐标） |
| Wizard→Initial Setting | 只读摘要 | 接入 Import CAD Data / Computational Domain 步骤 |
| Option→Environment/Detailed Settings | NYI | 一期：网格默认参数、显示精度 |
| Part 工具栏 | NYI | 保持占位；不做 CAD 建模（长期项） |

### 2.3 数据模型现状

`StpreModel` 已能读：

- `analysis_region()`：计算域 XML（`type=cube`、`base`/`size`、材料、face_list）；
- `mesh_axes()`：`mesh_block` 的 x/y/z 坐标（mm，`g` 元素）；
- `part_boxes()` / `analysis_boxes()`：`element` 的部件盒与 Domain 盒表；
- `groups()/parts()/regions()/values()/conditions()`：模型树。

缺失（本次新增）：

- `mesh_control` 参数化读写（RootBlock 的 min/max/grid/divide、标准长度、
  几何比、阈值、顶点检测方式等）；
- `element` 的**生成器**（当前只有读）；
- 域设置写回（base/size/坐标系/单位）。

---

## 3. 参考依据

### 3.1 手册关键页面（Pre_eng）

| 功能 | 手册页 |
|---|---|
| 文件导入 | `St_pre_File-Import.html`、`St_pre_Import_Model.html` |
| 初始向导导入 CAD | `St_pre_Wizard-Initial_Setting-Import_CAD_Data.html` |
| 计算域 | `St_pre_Edit_Computational_Domain_dialog.html`、`St_pre_Wizard-Initial_Setting-Computational_Domain.html` |
| 网格菜单/流程 | `St_pre_Mesh_menu.html`、`St_pre_Flow_of_gridding.html` |
| Gridding | `St_pre_Mesh-Gridding.html`、`...-Basic_Settings.html`、`...-Parameters.html`、`...-Detail_meshing.html`、`...-Edit.html`、`...-Deletion.html`、`...-Others.html` |
| Meshing | `St_pre_Mesh-Meshing.html`、`St_pre_Meshing.html`、`St_pre_Meshing_Meshing.html` |
| 自动网格 | `St_pre_Auto_meshing_by_specifying_the_number_of_elements.html`、`St_pre_Auto_meshing_by_specifying_the_standard_length_and_geometric_ratio_length_and_target_ratio..html` |
| 块编辑 | `St_pre_Mesh_Block_dialog.html`、`St_pre_Mesh_Connected_block_dialog.html` |
| 详细网格 | `St_pre_Detailed_Meshing.html`、`St_pre_Rough_meshing.html` |

### 3.2 逆向情报（Programs_x64 导出函数定位，2026-08-06）

STpre = .NET 启动器（`STpre_Bx64net.exe`）+ 原生 C++ DLL。核心逻辑在原生层：

| DLL | 关键导出 | 用途 |
|---|---|---|
| `STpreBase_Bx64.dll` | `ImportXtFile`(RVA 0x32AAB0)、`ImportXtFile2`(RVA 0x3E6A70)、`ImportStlFile`(RVA 0xCB8C0)、`ImportDxfFile`、`ImportMdlFile`、`ImportObjFile`、`ImportIgesFile`、`ImportNFBFile` 等 | 各格式导入 |
| 同上 | `ExportAllPartsXtFile`(RVA 0x331E50)、`ExportPartsXtFile`(RVA 0x20F630) | x_t 导出/持久化 |
| 同上 | `MeshControl`/`MeshBlock`/`MeshCoord` 类全套：`Read/Write/Save/Load`(XML)、`AllocBlock`、`AllocElement`、`CalcFine`、`CalcFineCoord`、`CalcRatio1/2`、`ExecDivide`、`InnerRegionGrid`、`OuterRegionGrid`、`SetCuboid`、`SetCylinder`、`GetElementBox`、`GetInnerGrid`、`CalcTotalElementNum`、`CheckElementMax`、`SetElementNum` | 网格生成核心 |
| 同上 | C 导出：`MeshReset`、`MeshSetElementMax/Threshold`、`MeshSetCylindricalSystem`、`MeshSetDomainFace`、`MeshSetAnalysisKind`、`SetInitialLengthByDomain`、`SetupMeshBlock`、`UpdateRootMeshBlock`、`LimitRangeByRootBlock`、`ImportCabFile` | 网格全局参数 |
| `STpreTool_Bx64.dll` | `CmdControl::SetXyzDomain`、`SetCylDomain`、`SetDomainDefaultSize`、`SetDomainRange`、`PreviewDomainRange`、`UpdateDomainRange` | 计算域命令 |
| 同上 | `CmdControl::Meshing`、`CmdControl::ImportFile`、`OpenGridSetDlg`、`UpdateGridSetDlg`、`SendGridSetDlg`、`OpenMeshBlockDlg`、`OpenMeshSubBlockDlg`、`OpenMeshConnectBlockDlg`、`OpenMeshSectionDlg`、`SetMeshParam`/`GetMeshParam`、`InitialMesh` | 菜单命令层 |
| `STpreFile_Bx64.dll` | `LoadLibraryXtFile`、`LoadLibraryStlFile`、`LoadLibraryCabFile`、`Save_S_File`、`ImportCsvFile` | 文件/库导入与 S 输出 |
| `STpreParts_Bx64.dll` | `PartsAnyBody` 相关、`PartsStandardDlgOpen` | 部件创建（长期） |
| `STprePMesh_Bx64net.exe` | 字符串含 `PMesh execution: rank/size`，引用 `MeshControl/MeshBlock` | 分布式 meshing worker |
| `ParasolidGW_Bx64.dll` + `pskernel.dll` | 已逆向：`PK_PART_receive`、`PK_BODY_export`、`PK_TOPOL_facet_2`、`PK_TOPOL_render_facet` | x_t 接收/导出/三角化 |

已完成的入口级反汇编（用于后续 ctypes 封装时的签名还原参考）：

- `ImportXtFile`：rcx=宽字符路径，内部做长度扫描后转调导入主流程；
- `ExportPartsXtFile`：rcx=对象(this)，rdx=输出路径宽字符，经虚表回调
  遍历 body 后写文件；
- `ImportStlFile`：rcx=路径，edx=导入模式标志，失败时抛错误对象；
- `MeshSetElementMax`：`xmm0`=上限值，写入全局 MeshControl 实例 `+0x98`；
- `MeshReset`：返回全局 MeshControl 实例 `+0xA0` 处值。

> 结论：`MeshControl`/`MeshBlock` 是**进程级单例**（`GetMeshCtrl` 获取全局
> 指针），对象布局可通过 `MeshSet*` 系列与 `Get*` 系列逐步还原；但完整
> ctypes 调用 C++ 类方法需要重建大量内部结构，成本高。本计划以 Python
> 自研算法为主、DLL 逆向为辅（见 §4 决策）。

### 3.3 与现有代码的衔接

- 三角化已打通，导入后只需把新 body 追加进 `_all.x_t` 并重新
  `tessellate_xt(adaptive=True)`；
- `.s` 导出已打通，`CXYZ`（mesh_block）与 `PARTS`（element）是网格化
  的最终消费端，正好作为验证；
- `cab_vtk` 的 domain_frame / mesh_block_grid / element_division_lines
  可直接用于网格预览。

---

## 4. 技术路线与决策

| # | 决策点 | 方案 | 理由 |
|---|---|---|---|
| D1 | x_t 导入 | **pskernel 路径为主**：`PK_PART_receive` → 三角化预览 → `PK_BODY_export` 写回 x_t → 合并 cab 成员并新增 `<parts>`；`ImportXtFile` 仅作对照/备用 | 现有代码已打通 pskernel；不依赖 STpre 内部对象布局 |
| D2 | x_t 三角化 | 复用 `ps_facet2_nodes.tessellate_xt(adaptive=True)`；导入后自动刷新 | 已实现且与 STpre 同源 |
| D3 | 计算域设置 | XML `analysis_region` 编辑 + 3D 预览 + CAD 包围盒计算；语义对齐 `SetXyzDomain/SetDomainRange` | 域数据就是 XML，无需调 DLL |
| D4 | gridding | **Python 自研**：RootBlock + 顶点检测 + 粗/细网格算法，写 `mesh_control`/`mesh_block` | XML 格式已完全掌握；`MeshControl` C++ 布局逆向成本高 |
| D5 | meshing | **Python 自研 cut-cell**：三角化曲面做单元占用判定，生成 `element`；基本干涉检查 | 依赖几何数据（已有），不依赖网格生成器二进制 |
| D6 | DLL 封装 | 仅封装“独立、签名简单”的 C 导出（如 `MeshSet*` 作参数参照）；C++ 类方法暂不封装 | 降低风险，先保证功能闭环 |
| D7 | 一致性 | 以官方 cab（ex4_e）与官方 `.s` 做黄金对拍；结构/语义一致优先，逐项逼近 | STpre 网格算法细节不可复制，先可用后精确 |

---

## 5. 总体架构与数据流

```
File→Import x_t/STL
      │  cab_import.py
      ▼
pskernel PK_PART_receive ──► ps_facet2_nodes.tessellate_xt(adaptive=True)
      │                                    │
      │ PK_BODY_export                     ▼
      ▼                               TessPart（3D 预览）
合并 _all.x_t + 新增 <parts>
      │
      ▼
Edit→Reset Computational Domain（cab_domain.py）
      │  base/size/坐标类型/单位/材料/包围盒
      ▼
Mesh→Gridding（cab_grid.py）
      │  顶点检测 → 粗网格 → 细网格（标准长度/几何比/单元数）
      ▼
mesh_control + mesh_block（XML）
      │
      ▼
Mesh→Meshing（cab_mesh.py）
      │  三角化曲面 → 单元占用判定（cut-cell）
      ▼
element（XML）
      │
      ├─► 3D 预览（cab_vtk element_division_lines）
      └─► File→Export → .s（CXYZ/PARTS）→ flddecoding 验证
```

新增模块：

| 模块 | 职责 |
|---|---|
| `cab_import.py` | 导入对话框、x_t/STL 解析、pskernel 接收/导出、cab 成员合并、部件注册 |
| `cab_domain.py` | 计算域模型（坐标系/单位/范围/材料）、包围盒计算、XML 写回、3D 预览数据 |
| `cab_grid.py` | 网格化参数模型、顶点检测、粗/细网格算法、`mesh_control`/`mesh_block` 生成 |
| `cab_mesh.py` | 单元占用判定（cut-cell）、`element` 生成、干涉检查、统计 |
| `cab_actions.py`（可选） | 菜单/工具栏动作表，供 `cab_gui.py` 引用 |

---

## 6. 分阶段开发计划

### M1 命令框架 + x_t 导入（1–2 周）✅ 已完成（2026-08-06）

**目标**：File→Import 可用；导入的几何能显示、保存、重开一致。

任务分解：

| 任务 | 产出 | 涉及文件 |
|---|---|---|
| 1.1 导入数据模型 | `ImportedBody`（name/tag/points/triangles/xt_bytes/transform） | `cab_import.py`（新） |
| 1.2 x_t 接收 | `import_xt_file(path) -> list[ImportedBody]`：`PK_PART_receive` + `tessellate_xt(adaptive=True)`；支持 STL→polygon（`PK_TOPOL_facet_2` 可直接吃三角面） | `cab_import.py`、`ps_facet2_nodes.py` |
| 1.3 持久化 | `merge_xt_member(archive, new_bodies)`：`PK_BODY_export` 生成 x_t 文本，合并/追加 `_all.x_t`；更新 cab 成员与 CFFILE | `cab_import.py`、`cab_container.py` |
| 1.4 部件注册 | `register_parts(model, bodies, group_name, material)`：新增 `<parts type="body">`（name/name2/file/transform/property/color/volume 占位） | `cabxml.py` 新增 API、`cab_import.py` |
| 1.5 GUI 接线 | File→Import 对话框（XT/STL 过滤）；导入后 `_rebuild_scene()`；工具栏 Import 按钮 | `cab_gui.py` |
| 1.6 导入向导步骤 | Wizard→Initial Setting→Import CAD Data 简化页：文件列表、Remove、位置/缩放 Configure | `cab_gui.py`、`cab_import.py` |

验收：

- 导入 `tests/tr03/_tr03_all.x_t` 类文件 → 树新增部件、3D 显示光滑曲面；
- Save As → 重开 cab：部件、x_t 成员、曲面一致；
- 导入一个外部 x_t 到 ex4_e 项目后，`_all.x_t` 仍可被 pskernel 接收。

#### M1 实施记录（2026-08-06）

按计划完成，两处实现细节已按可行性调整：

1. **持久化方式改为“独立成员”**：导入的 x_t 原样存为
   `<project>_import_NNNN.x_t` 并在 `<body_files>` 登记，而不是字节级合并进
   `_all.x_t`（多段 PART1 头拼接的传输流无法被 `PK_PART_receive` 解析）。
   GUI 加载时遍历全部 x_t 成员逐个接收，保存/重开一致。
2. **部件注册字段**：`add_part` 按 ex4_e 官方 `<parts type="body">` 的 18
   个子字段生成（含 name2/property/attribute/color/transform 等），并保持
   字节稳定序列化器兼容（text/tail 空白对齐）。

实际接口（与 §7.1 草案一致，签名见代码）：

- `cab_import.import_xt_bytes(raw, adaptive=True, **kw) -> list[ImportedBody]`
- `cab_import.import_xt_file(path, adaptive=True, **kw) -> list[ImportedBody]`
- `cab_import.add_xt_member(archive, xt_bytes, name=None) -> CabMember`
- `cab_import.register_parts(model, bodies, *, group/material/color/transform)
  -> list[str]`
- `cabxml.StpreModel.add_part(...)` / `body_files()` / `add_body_file()`

回归：`tests/test_import.py` 3 项通过；全仓 74 通过 / 4 跳过。
文档：DEV_SUMMARY §14；CAB_FORMAT_SPEC §5.4。

### M2 计算域设置（1 周）

**目标**：Edit→Reset Computational Domain 完整可用。

任务分解：

| 任务 | 产出 | 涉及文件 |
|---|---|---|
| 2.1 域模型 | `DomainSpec`：coordinate（cartesian/cylindrical/axial）、unit、min/max（或 base/size）、material、extend、auto_y | `cab_domain.py`（新） |
| 2.2 XML 读写 | `StpreModel.set_domain(spec)`：写 `analysis_region` 的 base/size/坐标类型/单位/材料；保留 face_list 与 region 绑定 | `cabxml.py`、`cab_domain.py` |
| 2.3 包围盒 | `part_bounds(model, tess_parts)`：全部部件（含 CAD 变换后）min/max；`cad_data_size()` 供向导 | `cab_domain.py`、`cab_vtk.py` |
| 2.4 GUI | 域对话框：坐标类型、单位、min/max 输入、CAD Data Size 按钮、Extend surroundings、域材料 combo、Preview | `cab_gui.py`、`cab_panes.py` |
| 2.5 3D 预览 | 域框实时更新（含圆柱/轴对称示意线框） | `cab_vtk.py` |

验收：

- 改域范围/材料 → 3D 域框与 XML 同步 → 保存重开一致；
- “CAD Data Size”结果与 `tess_parts` 包围盒一致；
- 导出的 `.s` 中与域相关的 REGION 范围正确。

### M3 gridding（2–3 周）

**目标**：Mesh→Gridding 生成 `mesh_control` + `mesh_block`。

任务分解：

| 任务 | 产出 | 涉及文件 |
|---|---|---|
| 3.1 参数模型 | `GridSpec`：root_block（min/max/grid）、vertex_detection（all/representative/axis_plane/minmax/not_considered/uniform）、method（rough_only/rough+detail/num_elements）、standard_length/threshold/geometric_ratio（internal/external）、common、discard_existing | `cab_grid.py`（新） |
| 3.2 XML 读写 | `StpreModel.set_mesh_control(spec)`、`mesh_control()` 解析（RootBlock 属性 + 子块） | `cabxml.py` |
| 3.3 顶点检测 | `detect_rough_grids(parts, tess, detection)`：MinMax/All（顶点坐标投影）/Axis plane（法向面）/Uniform；去重排序 | `cab_grid.py` |
| 3.4 细网格 | `refine_grid(rough, spec)`：按标准长度等分 + 几何比（内/外部），阈值下限；`num_elements` 模式：按目标总数/各轴数反推 | `cab_grid.py` |
| 3.5 多块（一期） | 根块 + 简单子块（`mesh_control/RootBlock` 属性 + `mesh_block` 坐标）；Connected block 仅记录不参与生成 | `cab_grid.py` |
| 3.6 GUI | Mesh→Gridding 对话框（Basic Settings/Parameters 子集）、网格线预览（`mesh_block_grid`）、进度 | `cab_gui.py`、`cab_vtk.py` |
| 3.7 验证 | 与 ex4_e 官方 `mesh_block` 对比点数/范围/步长分布 | `tests/test_grid.py`（新） |

验收：

- 默认参数下 ex4_e 的 `mesh_axes()` 点数/范围与官方一致（或可解释的差异）；
- `.s` 的 CXYZ 段可被 flddecoding 消费；
- 修改参数后网格线预览即时更新。

### M4 meshing（2–3 周）

**目标**：Mesh→Meshing 生成 `element`，完成导入→网格→导出闭环。

任务分解：

| 任务 | 产出 | 涉及文件 |
|---|---|---|
| 4.1 单元占用判定 | `classify_cells(axes, tess_parts)`：对每个网格单元用三角化曲面做 inside/outside 判定（射线法 + 包围盒加速 + 表面容差）；返回部件盒表 | `cab_mesh.py`（新） |
| 4.2 属性优先级 | 材料/属性按“solid/obstacle 优先于 fluid”规则写入盒表；支持 panel（单层面） | `cab_mesh.py` |
| 4.3 element 生成 | `build_element(model, boxes)`：`<element>` 的 `analysis`（Domain）与每个 `<parts>` 的 `body/list`；合并连续 i/j/k 区间减少 list 数 | `cab_mesh.py`、`cabxml.py` |
| 4.4 干涉检查（一期） | 相交部件检测（盒级 + 三角面相交粗检），报告 Message | `cab_mesh.py` |
| 4.5 GUI | Mesh→Meshing 对话框：执行/进度/统计（单元数、部件盒数）；Mesh→Editing Mesh 只读网格参数页 | `cab_gui.py` |
| 4.6 验证 | tr03 导入→网格化→导出 `.s`；与 flddecoding `s_model` 消费一致；ex4_e 官方 `element` 结构对比 | `tests/test_mesh.py`（新） |

验收：

- 无 element 的 tr03 导入后可一键网格化，得到与官方 cab 同构的
  `<element>`（数量可不同，但结构/属性一致）；
- `.s` 导出后 flddecoding 能正常生成 FLD；
- 大模型（>100 万单元）有进度条且内存可控（稀疏盒表）。

### M5 验证与文档（1 周）

任务分解：

| 任务 | 产出 |
|---|---|
| 5.1 回归测试 | `tests/test_import.py`、`tests/test_domain.py`、`tests/test_grid.py`、`tests/test_mesh.py`、更新 `test_gui.py`；全仓 pytest 绿 |
| 5.2 逆向档案 | `DEV_SUMMARY.md` 新增：`ImportXtFile/ExportPartsXtFile/ImportStlFile` RVA 与签名还原、`MeshControl/MeshBlock` 对象布局（`MeshSet*`/`Get*` 偏移表）、`CmdControl::Meshing` 调用链 |
| 5.3 格式规范 | `CAB_FORMAT_SPEC.md` 补：`mesh_control`（RootBlock 属性表）、`element` 生成规范（i/j/k 盒语义、属性优先级）、导入成员合并规则 |
| 5.4 使用文档 | `README.md`/`CAB_GUI_DESIGN.md` 更新菜单功能说明与操作流程 |

---

## 7. 关键接口设计（草案）

### 7.1 cab_import.py

```python
@dataclass
class ImportedBody:
    name: str
    tag: int                    # pskernel body tag（仅会话内有效）
    xt_bytes: bytes             # PK_BODY_export 结果（持久化用）
    tess: TessPart | None       # 三角化预览
    transform: tuple[float, ...] | None = None  # 16 个值，列主序

def import_xt_file(path: str | Path,
                   *, adaptive: bool = True) -> list[ImportedBody]:
    """PK_PART_receive + tessellate_xt + PK_BODY_export。"""

def import_stl_file(path: str | Path) -> list[ImportedBody]:
    """STL → polygon body（先解析三角面，再走 pskernel 或直接 TessPart）。"""

def merge_xt_member(archive: CabArchive, bodies: list[ImportedBody],
                    xt_name: str | None = None) -> CabArchive:
    """合并/追加 x_t 成员并返回新 archive（调用方负责写文件）。"""

def register_parts(model: StpreModel, bodies: list[ImportedBody],
                   group_name: str | None = None,
                   material: str | None = None) -> None:
    """新增 <parts type="body">，写回 model.doc。"""
```

### 7.2 cab_domain.py

```python
@dataclass
class DomainSpec:
    coordinate: str = "cartesian"   # cartesian | cylindrical | axial
    unit: str = "mm"
    xyz_min: tuple[float, float, float]
    xyz_max: tuple[float, float, float]
    material: str | None = None
    extend: tuple[float, float, float] = (0.0, 0.0, 0.0)
    auto_y_for_axial: bool = False

def part_bounds(model: StpreModel, tess: list[TessPart]) -> tuple[np.ndarray, np.ndarray]
def domain_from_xml(model: StpreModel) -> DomainSpec
def apply_domain(model: StpreModel, spec: DomainSpec) -> None
```

### 7.3 cab_grid.py

```python
@dataclass
class GridSpec:
    root_min: tuple[float, float, float]
    root_max: tuple[float, float, float]
    vertex_detection: str = "minmax"   # all|representative|axis_plane|minmax|not_considered|uniform
    method: str = "rough_and_detail"   # rough_only|rough_and_detail|num_elements
    standard_length: tuple[float, float, float] | float = ...
    threshold_length: tuple[float, float, float] | float = ...
    geometric_ratio: tuple[float, float, float] | float = ...
    geometric_ratio_internal: ... = ...
    geometric_ratio_external: ... = ...
    target_elements: int | None = None
    target_per_axis: tuple[int, int, int] | None = None
    discard_existing: bool = False

def rough_grids(parts, tess, spec) -> dict[str, list[float]]
def refine_grids(rough, spec) -> dict[str, list[float]]
def apply_grid(model: StpreModel, axes: dict[str, list[float]], spec: GridSpec) -> None
```

### 7.4 cab_mesh.py

```python
def classify_cells(axes, parts: list[TessPart],
                   *, progress=None) -> dict[str, list[tuple[int, int, int, int, int, int]]]
def build_element(model: StpreModel, boxes: dict[str, list[tuple[int, ...]]]) -> None
def interference_check(parts: list[TessPart], boxes) -> list[str]
```

### 7.5 GUI 接线

- `CabViewer._on_import()`：对话框 → `cab_import` → 注册 → 保存标记 →
  `_rebuild_scene()`；
- `CabViewer._on_domain()`：`DomainDialog`（`cab_domain`）→ apply → 刷新；
- `CabViewer._on_gridding()`：`GriddingDialog`（`cab_grid`）→ apply →
  `mesh_block_grid` 预览；
- `CabViewer._on_meshing()`：`MeshingDialog`（`cab_mesh`）→ apply →
  Element division 显示 + `.s` 导出提示。

---

## 8. XML 映射规范（一期）

### 8.1 analysis_region（域）

```xml
<analysis_region type="cube" name="Domain(cuboid)">
  <base>0,0,0</base><size>0.1,0.1,0.1</size>
  <color>...</color><property>air(...)</property>
  <face_list>...</face_list>
</analysis_region>
```

写回时保留 `face_list`（6 个边界 region 绑定），只更新几何/材料字段。

### 8.2 mesh_control（RootBlock）

```xml
<mesh_control>
  <RootBlock min="..." max="..." grid="99,243,63" divide="..."
             standard_length="..." threshold="..." ratio="..."
             ... />
</mesh_control>
```

一期解析/生成字段以 ex4_e 官方 XML 实测为准；未知属性保留（forward-compat）。

### 8.3 mesh_block

```xml
<mesh_block>
  <x num="99"><g no="0">0,B</g><g no="1">0.001</g>...</x>
  <y num="243">...</y><z num="63">...</z>
</mesh_block>
```

生成规则：`g` 文本首字段为坐标（mm），`B` 标记边界点；`num` 为点数。

### 8.4 element

```xml
<element>
  <analysis name="Domain(cuboid)"><body><list>i1,i2,j1,j2,k1,k2,0,1,1</list></body></analysis>
  <parts name="part1"><body><list>...</list></body></parts>
</element>
```

生成规则：盒表为闭区间 `[i1,i2]`；连续区间合并；属性按 material 优先级写入。

---

## 9. 测试计划

| 用例 | 断言 |
|---|---|
| `test_import_xt_roundtrip` | 导入→保存 cab→重开：部件/x_t/曲面一致 |
| `test_import_stl` | STL 导入生成 polygon 部件与三角形 |
| `test_domain_apply` | 改域→XML 重解析一致；CAD Data Size=包围盒 |
| `test_grid_basic` | MinMax/Uniform 粗网格正确；细网格单调、含边界、阈值下限生效 |
| `test_grid_num_elements` | 目标单元数换算各轴点数正确 |
| `test_mesh_classify` | 已知几何（box）单元占用与手工结果一致 |
| `test_mesh_element` | tr03 导入→网格化→`<element>` 结构与官方同构 |
| `test_mesh_export_flow` | 网格化后 `.s` 被 flddecoding 消费 |
| `test_gui_menus` | Import/Domain/Gridding/Meshing 动作不抛错、日志正确 |
| 全仓回归 | 既有 64 项不回归 |

---

## 10. 风险与应对

| 风险 | 等级 | 应对 |
|---|---|---|
| meshing 与 STpre 1:1 不一致 | 中 | 先“结构/语义可用”，官方 cab 黄金对拍逐项逼近 |
| `ImportXtFile` 参数未知 | 低 | 主路线 pskernel，不依赖该函数 |
| `MeshControl/MeshBlock` C++ 布局逆向成本 | 中 | 不阻塞：Python 自研算法；布局档案逐步沉淀 |
| 大模型性能 | 中 | 稀疏盒表、包围盒加速、进度条、分块处理 |
| 单元占用判定误差（表面单元） | 中 | 表面容差 + 射线冗余方向投票；与官方 element 对比校准 |
| cab 成员合并破坏原格式 | 低 | 先做“追加新 body 到 `_all.x_t` + 重打包”round-trip 测试 |

---

## 11. 里程碑与时间线

| 里程碑 | 内容 | 预估 |
|---|---|---|
| M1 | File→Import x_t/STL + 自动三角化 | 1–2 周 |
| M2 | 计算域设置闭环 | 1 周 |
| M3 | Gridding 生成 mesh_block | 2–3 周 |
| M4 | Meshing 生成 element + 导出闭环 | 2–3 周 |
| M5 | 测试、逆向档案、格式规范更新 | 1 周 |

依赖：M1 → M2 → M3 → M4；M5 与各阶段并行。

---

## 12. 文档同步清单

| 文档 | 更新内容 | 时点 |
|---|---|---|
| `DEV_PLAN.md` | 本计划随实施进度标记完成状态 | 持续 |
| `DEV_SUMMARY.md` | 新增 §14：导入/域/网格逆向档案（RVA、签名、MeshControl 偏移） | M3/M5 |
| `CAB_FORMAT_SPEC.md` | 补 `mesh_control`/`element` 生成规范、x_t 成员合并规则 | M3/M4 |
| `CAB_GUI_DESIGN.md` | 更新菜单/对话框功能说明 | M1/M2 |
| `README.md` | 使用流程（导入→域→网格→导出） | M5 |

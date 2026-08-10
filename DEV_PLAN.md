# cab_gui 功能补齐开发计划（逆向驱动）

> 日期：2026-08-10（§15 全量对照刷新；§14 M32 D1–D7 已完成）
> 仓库：`cabdecoding`
> 关联文档：[CAB_GUI_DESIGN.md](CAB_GUI_DESIGN.md)（UI 布局）、
> [DEV_SUMMARY.md](DEV_SUMMARY.md)（逆向档案）、
> [CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)（cab 格式规范）
> 交互画布：`.cursor/projects/.../canvases/cab-gui-stpre-gap.canvas.tsx`
> 参考手册：`C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\Pre_eng\index.html`
> 对照源：Pre_eng `toc.csv` + `cab_gui.py` / `cab_edit_*` / `cab_parts` / wizards
>
> **当前主线：** §15 M35+（Control 死角 / CW Source / Library / 格式）。  
> **冻结：** Gridding/Meshing via STpre API（§14.2）。

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

### 2.2 缺口清单（一期目标 → 多已完成）

> **2026-08-09 起：** 全量 vs STpre 差距与 M24+ 计划见 **§13**（自画布刷新）。  
> 下表保留一期闭环完成记录；不再作为当前缺口的权威列表。

| 菜单 | 现状 | 目标 |
|---|---|---|
| File→Import… | ✅ 已完成（M1/M10/M26） | XT/STL/STEP/SAT + OBJ/DXF/MDL(best-effort) |
| Edit→Reset Computational Domain | ✅ 已完成（M2/M23） | Reset 与 Edit Domain 已分离（见 M23） |
| Mesh→Gridding | ✅ 已完成（M3/M5/M9+） | Basic Settings/Parameters 子集对话框 + 网格生成 |
| Mesh→Meshing | ✅ 已完成（M4） | 基于现有网格生成 element，进度/日志 |
| Mesh→Checking Parts Interferences | ✅ 已完成（M6） | Select 部件 + Interference/Contact/Separation 列表 + Confirm/Reconstruct |
| Mesh→Editing Mesh | ✅ 已完成（M6） | I/J/K 层选择 + ->Effective/->Ineffective 编辑单元属性 |
| Mesh→Showing Element Cross-Section | ✅ 已完成（M6） | Axis + 滑块 + Show/Hide fluid，Draw 窗口实时截面 |
| Mesh→Checking S-File | ✅ 已完成（M6） | Open S file + 树形列表 checkbox 控制 3D 显隐 |
| Wizard→Initial Setting | ✅ 已完成（M6/M23） | 6 步 + 冷启动自动弹出 |
| Wizard→Condition Setting | ✅ 子集（M6/M21/M28） | 核心 BC + Humidity/Porous/RadGroup |
| Option→Environment/Detailed Settings | ✅ 子集（M7-5/M29） | Folder/Color/Unit 等；未满 13 页 |
| Edit 全菜单 | ✅ UI 24/24（M23）+ M24 MVP | Boolean=CSG；真 B-rep 待绑定 |
| Part 菜单 | ✅ 14+5 种（M7–M8/M30） | 专用件为几何代理 |

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

补充（2026-08-06）：无参数启动自动初始化空工程（`cabxml.new_stpre_bytes/
new_property_bytes` + `CabViewer._new_project`），File→New（Ctrl+N）可随时
新建；空工程下可直接 Import x_t → 域设置 → Gridding → Meshing，保存后
重开一致。详见 DEV_SUMMARY §19。

### M2 计算域设置（1 周）✅ 已完成（2026-08-06）

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

#### M2 实施记录（2026-08-06）

- 新增 `cab_domain.py`：`DomainSpec`、`domain_from_xml`、`apply_domain`、
  `part_bounds`（应用 XML 列主序 transform 求世界包围盒）；
- `cabxml.StpreModel` 增加域读写与 `ensure_domain`（无域项目自动创建
  cube 域 + 6 个 face_list region，面编号对齐 ex4_e：Ymin=1/Xmax=2/
  Ymax=3/Xmin=4/Zmin=5/Zmax=6）；
- GUI `_DomainDialog`：坐标系/单位（含 mm↔m↔cm 换算）/min-max/域材料/
  CAD Data Size/Extend surroundings/轴向 Y 自动/Preview 应用不关闭/
  Cancel 回退；Edit→Reset Computational Domain 已接入；
- 一期限制：cylindrical 仅把 `analysis_region@type` 置为 cylinder 并保留
  cube 几何语义；axial 复用 cube 类型；坐标系细化留待 M5 与 STpre 对拍。

回归：`tests/test_domain.py` 5 项通过；全仓 79 通过 / 4 跳过。
文档：DEV_SUMMARY §15；CAB_FORMAT_SPEC §5.5。

### M3 gridding（2–3 周）✅ 已完成（2026-08-06）

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

#### M3 实施记录（2026-08-06）

- 新增 `cab_grid.py`：`GridSpec`/`rough_grids`/`refine_grids`/
  `build_axes`，覆盖六种顶点检测、三种网格化方法（含目标单元数反推）；
  `representative`/`axis_plane` 为一期近似（all/minmax 顶点集），
  `num_elements` 按轴长比例均匀分布，圆柱/轴对称未实现——均已在
  DEV_SUMMARY §16.2 记录，待与 STpre 黄金对拍细化；
- `cabxml.set_mesh()`：生成与 ex4_e 同构的 `mesh_control`（RootBlock
  min/max/limit/grid/subblock、select_vertex、divide_method、
  divide_ratio2、outer_range 等）与 `mesh_block`（x/y/z `<g>` 表，
  首末 `B` 标记）；
- GUI `_GriddingDialog`：Basic Settings 子集（顶点检测/方法/标准长度/
  阈值/内外部几何比/目标单元数），应用后刷新 3D 网格线并置脏；
- 后续 M4 将消费 `mesh_axes()` 生成 `element`，M5 做 `.s` CXYZ 黄金对拍。

回归：`tests/test_grid.py` 6 项通过；全仓 85 通过 / 4 跳过。
文档：DEV_SUMMARY §16；CAB_FORMAT_SPEC §5.6。

### M4 meshing（2–3 周）✅ 已完成（2026-08-06）

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

#### M4 实施记录（2026-08-06）

- 新增 `cab_mesh.py`：+X 偶数-奇数射线判定（按三角形 yz 投影切片向量化）、
  共享边扰动修正、贪心盒合并、`apply_elements` 写 `<element>`；
- `cab_gui._meshing_dialog()`：Mesh→Meshing 执行入口，状态栏进度；
  进度实现从模态 QProgressDialog 改为状态栏（offscreen 模态会阻塞）；
- 一期限制：表面单元 epsilon 判定、开放曲面未处理、盒合并非 STpre 精确
  行程编码（DEV_SUMMARY §17.2，M5 黄金对拍项）；
- 大模型性能：每三角形只处理投影覆盖的单元切片 + bbox 预过滤，仍为
  O(面数×覆盖单元)，百万单元/万面级模型需在 M5 做进一步加速评估。

回归：`tests/test_mesh.py` 5 项通过；全仓 90 通过 / 4 跳过。
文档：DEV_SUMMARY §17；CAB_FORMAT_SPEC §5.7。

### M5 验证与文档（1 周）✅ 已完成（2026-08-06）

任务分解：

| 任务 | 产出 |
|---|---|
| 5.1 回归测试 | `tests/test_import.py`、`tests/test_domain.py`、`tests/test_grid.py`、`tests/test_mesh.py`、更新 `test_gui.py`；全仓 pytest 绿 |
| 5.2 逆向档案 | `DEV_SUMMARY.md` 新增：`ImportXtFile/ExportPartsXtFile/ImportStlFile` RVA 与签名还原、`MeshControl/MeshBlock` 对象布局（`MeshSet*`/`Get*` 偏移表）、`CmdControl::Meshing` 调用链 |
| 5.3 格式规范 | `CAB_FORMAT_SPEC.md` 补：`mesh_control`（RootBlock 属性表）、`element` 生成规范（i/j/k 盒语义、属性优先级）、导入成员合并规则 |
| 5.4 使用文档 | `README.md`/`CAB_GUI_DESIGN.md` 更新菜单功能说明与操作流程 |

#### M5 实施记录（2026-08-06）

- `tests/test_workflow.py`（2 项）：box 与 tr03 全流程
  「导入→建域→Gridding→Meshing→导出 .s/.xemt→cab 往返」通过；
- 修复 `s_export._child_text` 对缺失 `radiation` 节点的容错（box/tr03
  导出不再抛 TypeError）；
- DEV_SUMMARY §18 固化逆向档案（DLL/RVA 表、MeshControl 偏移、STprePMesh
  worker、5 项黄金对拍清单）；
- README 更新使用流程（见 §14 之后新增操作说明）。

全仓 `pytest`：**92 通过 / 4 跳过**。

#### M5 补充：STpre 风格对话框框架 + Mesh:Set division 六标签对话框（2026-08-06）

- 新模块 `cab_dialogs.py`（STpre 对话框框架）：`DialogHeader`、
  `ColorButton`、`AttributePanel`、`CuboidSchematic`、`StpreDialogBase`、
  `MaterialListDialog`；
- `DomainDialog`：对齐 [Edit Computational Domain] 截图/手册（左 Scale +
  右 Attribute/Condition，逐轴 Extend、CAD Data Size、重命名修复 face_list
  引用、Cancel 回滚）；`PartDialog`：部件编辑（属性/材料/颜色/monitor/
  重命名）；树中双击部件/域/RootBlock 与右键 Reference 全部接入；
- `GriddingDialog` 重写为 **Mesh:Set division 六标签**（Basic Setting /
  Parameter / Detail meshing / Edit / Deletion / Others），底部
  [Gridding] [Meshing] [Close] + `Element #` 状态行；模型层新增
  `mesh_axis_entries/set_mesh_axis`（`<g>` 的 N/F/S/B 标记）、
  `mesh_control_value/set_mesh_control_value`、部件 `select_vertex`、
  `cab_mesh.update_part_elements/find_interferences/resolve_interferences`、
  `cab_grid.divide_interval/delete_grid_lines`；
- 已知 NYI（已记日志，不阻塞）：multiblock 创建/插入、Edit 页鼠标拾取
  （用列表选择代替）；
- 回归：`tests/test_dialogs.py`（8 项）+ `tests/test_gridding_tabs.py`
  （11 项）；清理残留 `tests/tmp*` 目录后全仓 **114 通过 / 4 跳过**。

### M6 Mesh 菜单补全 + Wizard 功能（2026-08-08）✅ 已完成

参照 Pre_eng 手册（`St_pre_Mesh_menu.html`/`St_pre_Mesh-Editing_Mesh.html`/
`St_pre_Mesh-Checking_Parts_Interferences.html`/
`St_pre_Mesh-Showing_Element_Cross-Section.html`/
`St_pre_Mesh-Checking_S-File.html`/`St_pre_Wizard*.html`）与二进制
（`STpreTool_Bx64.dll` 对话框资源串、`STpreIwiz_Bx64.dll`/`STpreCwiz_Bx64.dll`
向导页类名、`STpre_Bx64net.exe` 菜单字串）把 **Mesh 菜单 6 项全部打通**，
并把 **Wizard 两个入口从只读摘要升级为真正的多步向导**：

| 菜单 | 实现 |
|---|---|
| Mesh→Gridding / Meshing | 既有（M3/M4/M5） |
| Mesh→Checking Parts Interferences | `InterferenceDialog`（cab_dialogs）：Select 部件、Interference/Contact/Separation 三态列表、Separation only、Confirm（高亮部件）、Reconstruct（`cab_mesh.resolve_interferences`）；新增 `cab_mesh.classify_interferences`（严格 overlap=干涉、face 邻接=Contact、gap≤阈值=Separation），并修正 `resolve_interferences` 的 AABB 精确相减 |
| Mesh→Editing Mesh | `EditMeshDialog`：Active block、I/J/K 层选择 + 层内范围、`->Effective`/`->Ineffective` + Execute；新增 `cab_mesh.cell_mask_from_boxes/_boxes_from_mask/toggle_cells_effective` |
| Mesh→Showing Element Cross-Section | `SectionDialog`：Axis + Element/Face address + 滑块 + All blocks + Show/Hide/Show only fluid；新增 `cab_vtk.element_section_data/element_section_polydata/section_actor`，`CabViewer._show_section` 实时刷新 |
| Mesh→Checking S-File | `SFileCheckDialog`：Open S file（`s_export.parse_s_parts` 解析 PARTS 名）+ 树形 checkbox 控制 3D 显隐（`CabViewer._set_part_visible`） |
| Wizard→Initial Setting | `cab_wizards.InitialWizard`：Project / Import CAD Data / Computational Domain / Analysis Type / Initial Value-Gravity / Purpose of Analysis / Conditions for Computational Domain Boundary / Confirm Settings；写回 project、analysis_region、analysis_set（type/heat/turbulence/turbulence_model/grav/cycle）、condition+value（forced-convection 自动边界：inlet/outlet/side_wall+side_adiabatic）；Cancel 快照回滚 |
| Wizard→Condition Setting | `cab_wizards.ConditionWizard`：左导航树（undefined=灰/defined=橙）+ Analysis Types / Basic Settings / Fluid Region / Flow / Heat / Initial Condition / BC(Flow·Wall·Thermal·Symmetrical) / Analysis Control / File Specification / Condition List（右键 Rename/Copy/Delete）/ Setting Confirmation |

模型层新增（`cabxml.StpreModel`）：`set_project_value/project_value/set_project_name`、
`ensure_analysis_set/analysis_set_value/set_analysis_set_value`、
`set_gravity/set_cycles`、`upsert_value`（含 `<name>` 补全）、
`bind_condition`（同目标可多个条件、同值幂等）、`condition_value/remove_condition`、
`set_part_transform`。

一期近似（已记录，待与 STpre 黄金对拍）：
- Condition Wizard 覆盖 Basic-Exercise-1 页面集，其余 ~150 页未实现；
- Internal-enclosure / buildings-purpose 边界自动设置仅提示不写回；
- 截面 Face address 与 Element address 映射为同一单元层；multiblock 仍单 RootBlock；
- Editing Mesh 以列表/范围选择替代鼠标拾取。

回归：`tests/test_mesh_edit.py`（7 项）+ `tests/test_mesh_menus.py`（7 项）+
`tests/test_wizards.py`（6 项）；全仓 **132 通过 / 4 跳过**。
文档：DEV_SUMMARY §23；CAB_GUI_DESIGN §4.5/4.6。

### M7 其余菜单补齐（File/Edit/View/Part/Option/Help）（2026-08-08，规划）

目标：把 Mesh/Wizard 之外的 6 个菜单全部从 NYI/占位升级为可用功能。
依据：Pre_eng 手册各菜单/对话框页 + `STpreTool/STpreBase` 导出与资源串
（`ExecUndo/ExecRedo/ClearUndoStack`、`PartsCuboid/Cylinder/Sphere/Panel`
 类、`?Set@PartsCylinder@@...` 等部件参数接口、`OpenPrinterModelDlg`、
 `GetStringOfVersionNo`）。

计划（每项完成即 commit+push）：

| 序 | 菜单 | 实现 |
|---|---|---|
| M7-1 | File | ✅ `Print`：Draw 窗口截图（VTK→PNG）+ 系统打印；`Execute Solver`：确认后导出临时 `.s/.xemt` 并启动 `stsol_Dx64net.exe`；`Execute Post`：确认后启动 `scPOST_Dx64net.exe`（缺失时 WARN） |
| M7-2 | Edit | ✅ `Undo/Redo`：XML 快照栈（模型+属性，Ctrl+Z/Ctrl+Y，覆盖导入/域/部件/网格/向导等全部改动）；`Deletion of Parts`：多选删除对话框（移除 `<parts>`/`<element>` 盒/关联 condition）；`Group`：建组/移动部件对话框（`<group>` + 成员） |
| M7-3 | View + Help | ✅ View：`Show Message Window`/`Show Status Bar` 开关；Help：新增 `Version`（cabdecoding/Python/Qt/VTK/pskernel 版本） |
| M7-4 | Part | ✅ `Cuboid/Cylinder/Sphere/Panel` 创建对话框（`cab_parts.CreatePartDialog`：Location/Size、Center/Radius/Height、Center/Radius、Location/Size/Direction + 属性/材料）；写入 `<parts type="cube|cylinder|sphere|panel">`，生成 TessPart 3D 预览；重开时按 XML 参数重建几何（不依赖 x_t）；后续各阶段已实现 `Sketch Part` 及 `Fan`/`Axial-Flow Fan`/`Blower Fan` 等共 14 种部件（见 M8 及后续） |
| M7-5 | Option | ✅ `Environment Settings`/`Detailed Program Settings`：`cab_options.OptionsDialog`（Basic/Parts/Mesh/Message/User Interface 标签子集），QSettings+内存持久化并即时生效；facet 默认精度参与 x_t 三角化 |
| M7-6 | 回归与文档 | ✅ `tests/test_menus_other.py`（14 项）；DEV_SUMMARY §24、DEV_PLAN M7 实施记录、CAB_GUI_DESIGN §4、README 更新；全仓 **146 通过 / 4 跳过** |

### M8 Sketch plane 与 Sketch Part（2026-08-08）✅ 已完成

| 项 | 实现 |
|---|---|
| Sketch plane | `cab_sketch.py`（SketchPlane/XML 读写/Reset Zmin/Fit 计算域）+ `cab_vtk` 网格线与 U/V/W 轴 actor + Control Window Sketch 页（原点/网格/Update/Reset/Fit）+ Show/Select 开关启用 |
| Sketch Part | `cab_sketch`（Profile 点序列/矩形/圆 + Panel/Extrusion 几何）+ `SketchPartDialog` + Part→Sketch Part 接入 + XML 参数持久化与重开重建 |
| 集成 | 一并审阅并提交并行会话 WIP（`cab_materials.py` 标准材料库 + `data/standard_property_ENG.xml` + 扩展 Part 菜单）；修复 `cab_panes` QDoubleSpinBox 导入 |
| 回归 | `tests/test_sketch.py`（7 项）；全仓 **161 通过 / 4 跳过**；文档：DEV_SUMMARY §25、CAB_GUI_DESIGN、README |

### M9 更准确的 gridding / meshing 算法（2026-08-08）✅ 已完成

依据官方 ex4_e `mesh_block` golden 数据反推并实现：

| 项 | 实现 |
|---|---|
| 外区网格 | `_stpre_external`：贴部件侧几何级数（首间距=标准长度，实际比值由 `g0*(q^n-1)/(q-1)=L` 二分求解，非名义 1.2） |
| 内区网格 | `_equal_split`：按标准长度等分（阈值下限生效） |
| 真实顶点 | `PK_FACE_ask_vertices`+`PK_VERTEX_ask_point` 提取 B-rep 顶点 → `TessPart.vertices` → All/Representative 检测使用 |
| meshing 精度 | 表面样本含端点判定；`samples="corners"` 8 角点+中心多数投票（opt-in，默认中心法） |
| 回归 | test_grid/test_mesh 更新 + golden 断言；Edit 页测试改用非网格坐标；全仓 **163 通过 / 4 跳过** |

文档：DEV_SUMMARY §26；CAB_FORMAT_SPEC §5.6/5.7 算法说明更新。

### M10 Import 扩展：STEP / STL / SAT（2026-08-08）✅ 已完成

| 项 | 实现 |
|---|---|
| STL | 原生文本/二进制解析（`cab_import.parse_stl_bytes`），polygon 部件 + `.stl` 成员持久化 + 重开重建 |
| STEP / SAT | OpenCascade（`cab_occ.py`：STEPControl/SATControl + BRepMesh 三角化）→ polygon + `.stl` 成员持久化；**移除 GUI 转换器**（CADthru 无头会挂起），OCC 缺失立即报错 |
| 分派/GUI | `import_file(WithPayload)` 按扩展名分派；File→Import 过滤器扩展 |
| 回归 | `tests/test_import.py` 3 项；全仓 **170 通过 / 4 跳过** |

文档：DEV_SUMMARY §27；README/CAB_GUI_DESIGN 导入格式更新。

### M11 STpre VB/COM API 网格开关（2026-08-08）✅ 已完成

| 项 | 实现 |
|---|---|
| 开关 | Option→Mesh 复选框 + Mesh 菜单可勾选项（QSettings `use_stpre_api`，默认 False=原生） |
| STpre 调用 | `cab_stpre_api.py`：win32com `STpre_Bx64net.Application.2025` → OpenCabFile → SetGridParam → ExecuteGrid/ExecuteElement → SaveCabFile（临时 cab 文件中转） |
| 回传 | 输出 cab XML 的 mesh_control/mesh_block/element/analysis_region 合并回内存模型；失败回退原生 |
| 参数映射 | `build_grid_params`：division_method/division_type/division_num/outer_ratio/edge_contact 等 ↔ `mesh_control` |
| 回归 | `tests/test_stpre_api.py` 5 项；全仓 **181 通过 / 4 跳过** |

文档：DEV_SUMMARY §28；README/CAB_GUI_DESIGN 更新；一并提交并行
Layer/ActivePart 工作。

### M12–M22（延伸已完成，摘要）

M11 之后已陆续完成（详见 git log / DEV_SUMMARY）：Gridding 规则逼近
（auto1 / L-R / 顶点线）、Draw Window Mesh 面网格与深度遮挡、Condition Wizard
页面扩展（`cab_cwizard_pages`）、Sketch/STpre API 对齐、启动告警过滤等。
菜单 chrome 与网格表面能力已明显高于本文件早期 NYI 描述。

### M23 Initial Setting 自动弹出 + Edit 菜单 24 项（2026-08-09）✅ 已完成

| 项 | 实现 |
|---|---|
| 冷启动 / File→New | 对齐 STpre：无 CLI `.cab` 时自动弹出 Initial Setting；可 Finish / Open Existing / Cancel |
| Initial Wizard | `cab_iwizard_pages.py` + `cab_wizard_icons.py`：6 步（Project→Domain→Analysis Type→Gravity→Purpose→Confirm） |
| Edit 菜单 | Pre_eng toc **24/24** 项挂齐；`cab_edit_dialogs.py` + `cab_edit_ops.py` |
| Reset vs Edit Domain | 菜单 **Reset Computational Domain**（坐标系/重力/默认值）与树双击 **Edit Computational Domain**（Scale+Attribute）分离 |
| 回归 | `tests/test_edit_menu.py`、`tests/test_wizards.py`；提交 `779e5f3` |

**深度说明（chrome ≠ 内核）：** Edit 中 Boolean / Edit Solid / Wrap / Simplify /
Paneling / Wiring / Image 等为对话框齐全 + AABB/意图写回；真正 Parasolid B-rep
操作列入 M24。

---

## 13. cab_gui vs STpre 功能差距与改进计划（2026-08-09）

> 自交互画布 `cab-gui-stpre-gap.canvas.tsx` 刷新。  
> **总判：** 菜单表面覆盖已较高（Edit 24/24、Mesh 6/6、Wizard 2/2），但**内核忠实度**
> 明显偏低——Edit CAD、面拾取、Import/Export 广度、Condition Wizard 深度仍是主要差距。

### 13.1 覆盖速览（加权粗算）

| 指标 | 值 | 说明 |
|---|---|---|
| 菜单 UI 覆盖（加权） | **~85%** | Σ(cab UI) / Σ(STpre 叶子) |
| 可用实现覆盖（加权） | **~68%** | Σ(useful) / Σ(STpre)；chrome 不计满 |
| Edit 菜单项 | **24/24** | UI 齐全 |
| Part 种类 | **14/30+** | 缺热设计专用件 |

图例深度：`impl` 可用 · `partial` 近似 · `chrome` 对话框/意图 · `missing` 未挂菜单。

### 13.2 分区覆盖

| 区域 | STpre | cab UI | 可用 | 备注 |
|---|---:|---:|---:|---|
| File | 11 | 11 | 9 | Import/Export 格式子集；无 3DfindIT |
| Edit | 24 | 24 | 12 | 菜单齐全；半数 CAD 为 AABB/chrome |
| View | 13 | 13 | 13 | 相机/工具栏齐；缺 Setting/Dialog 项 |
| Part | 30 | 14 | 14 | 基础体+风扇+草图；缺热设计专用件 |
| Wizard | 2 | 2 | 2 | IW 强；CW 导航约 26/150+ 页 |
| Mesh | 6 | 6 | 6 | 表面齐；multiblock/cut-cell 弱 |
| Option | 10 | 4 | 4 | 缺 Distance/Cut Cell/Selection 等 |
| Help | 2 | 3 | 3 | 含 Version/About |

菜单 UI 覆盖率（%/区）：File 100 · Edit 100 · View 100 · Part ~47 · Wizard 100 ·
Mesh 100 · Option 40 · Help 150（多 About）。

可用实现覆盖率（%/区）：File ~82 · Edit 50 · View 100（已挂项） · Part ~47 ·
Wizard 100（入口） · Mesh 100（近似计） · Option 40 · Help 150。

### 13.3 深度差距（chrome ≠ 内核）

| 区域 | 能力 | 深度 | 差距说明 |
|---|---|---|---|
| File | Open / Save / New | impl | 冷启动 Initial Wizard 已对齐 |
| File | Import | partial | 有 XT/STL/STEP/SAT；缺 MDL/DXF/OBJ/IDF/主流 CAD |
| File | Export | partial | 仅 `.s`/`.xemt`；缺 XT/STL/Neutral/XML |
| File | Execute Solver / Post | partial | 能启动；Kicker/环境文件不完整 |
| Edit | Undo/Redo / Group / Deletion / Reset Domain | impl | 快照 Undo ≠ Parasolid 历史 |
| Edit | Mirror / Align / Place / Conversion / Sweep / Cutting | partial | 变换/包围盒近似，非完整 B-rep |
| Edit | Boolean / Edit Solid / Wrap / Simplify / Paneling / Wiring | chrome | 对话框齐；内核级几何未接通 |
| View | Fit / Planes / Toolbars / Message | impl | — |
| View | Clipping / Hide / Thermal Display / Part lists | missing | Setting + Dialog 子菜单缺失 |
| Part | Cuboid…Pipe / Fans / Sketch | impl | Tess 原语，非完整 Parasolid 实体编辑 |
| Part | Enclosure / Fin / Peltier / AC / Diffuser… | missing | 约 16+ 专用件未进菜单 |
| Wizard | Initial Setting | partial | 6 步可用；CAD Import/边界自动较好 |
| Wizard | Condition Setting | partial | 核心 BC 有；湿度/辐射/多孔等深度不足 |
| Mesh | Gridding / Meshing / Interference… | partial | 规则逼近中；cut-cell/multiblock 弱 |
| Option | Environment / Detailed | partial | 5 页 vs STpre ~13 Environment 页 |
| Option | Cut Cell / Distance / Reference / Selection / Viewer | missing | 未挂菜单 |
| Control | Face/Vertex/Edge 选择目标 | chrome | 多为 `_nyi`；阻塞 Edit/Measure |

### 13.4 跨切面缺口（按严重度）

| 缺口 | 严重度 | 影响 |
|---|---|---|
| Parasolid 忠实 Edit CAD（Boolean/Solid/Wrap/Simplify/Paneling） | **Blocker** | 当前 AABB/chrome，无法做真实 CAD 准备 |
| 交互式面/边拾取管线 | **High** | Face Paneling、Distance、Reference、Sweep 依赖 |
| Import/Export 格式矩阵 | **High** | 工业 CAD 进出不齐 |
| Meshing cut-cell / multiblock / 金标占用 | **High** | 求解前网格质量与 STpre 仍有差 |
| Condition Wizard 深度（~150 页） | **High** | 产品完整度；Basic Exercise 可先子集 |
| View Setting/Dialog + Option 工具菜单 | **Medium** | 显示/测量工作流缺口 |
| Part 热设计专用库 | **Medium** | 电子散热场景常用 |
| Solver/Post 产品化集成 | **Medium** | 启动可用，环境/重启选项不足 |
| Undo 与 Parasolid 会话一致性 | **Medium** | XML 快照无法回滚内核实体 |
| i18n / 3DfindIT 等 | **Low** | 非核心工作流 |

### 13.5 当前优势（保持，不宜推倒）

CAB 读写、STpre 布局 chrome、XT facet 显示、Domain/Gridding 规则逼近、Mesh
菜单表面、Initial Wizard、原语 Part 创建、快照 Undo。这些是后续里程碑的底座。

### 13.6 改进计划 M24+（优先内核与拾取）

原则：**优先打通内核与拾取 → 补格式与网格 → Wizard/Option/专用件。**  
建议下一迭代直接从 **M24**（Boolean + 面拾取 + Facet 重建）开工；完成后 Edit
从「对话框齐」跃迁到「CAD 准备可用」。

#### M24 Edit 内核脊柱 ✅（子集；Boolean= tessellation CSG，非 `PK_BODY_boolean_2`）

- [x] Boolean unite/subtract/intersect（`cab_ps_ops.mesh_boolean` + `boolean_mesh_parts`）
- [x] Facet reconstruct → `PK_TOPOL_facet_2`（有 XT + pskernel 时）
- [x] Draw 面拾取（vtkCellPicker）→ Flip 选中三角；Paneling/Sweep 仍为 chrome/代理
- 交付：`cab_ps_ops` / `cab_edit_ops`；真 B-rep Boolean 仍待内核绑定

#### M25 选择 / 测量 / View Setting ✅（MVP）

- [x] Control Target: Face / Vertices 启用拾取
- [x] Option Distance + Reference
- [x] View Hide/Display All + Clipping
- 交付：拾取管线、Message 测量输出

#### M26 Import/Export 核心格式 ✅（MVP）

- [x] Import: OBJ / DXF(3DFACE) / MDL(best-effort OBJ)
- [x] Export: XT（archive 成员）/ STL / Property XML
- [ ] 格式矩阵回归测试（后续）

#### M27 Mesh 保真 ✅（stub / MVP）

- [x] Multiblock create/insert ChildBlock XML stub
- [ ] Meshing 与金标 cab 占用差收敛
- [x] Cut Cell Option MVP（Option 菜单）

#### M28 Condition Wizard 扩展 ✅（子集）

- [x] Humidity / Porous Media 页 + 项目写回
- [x] Radiation grouping 页
- [ ] Source 细节深度 / 全物理覆盖（后续）

#### M29 Option / Environment 补全 ✅（子集）

- [x] Environment 增 Folder/File、Color、Unit（未满 13/13）
- [x] Selection Mode / Viewer Mode
- [x] 设置持久化（`cab_options`）

#### M30 Part 专用件包 ✅（几何代理）

- [x] Enclosure / Plate·Pin Fin / Peltier·2R 菜单 + tess 代理
- [ ] 专用热属性完整模型（后续）

#### M31 Solver/Post 产品化 ✅（MVP）

- [x] 环境文件路径 / 工作目录 / restart
- [x] Post 打开场数据路径
- [ ] 启动矩阵文档化（后续）

#### M32+ 抛光（后备）

i18n、3DfindIT（或明确放弃）、热条件显示、Wiring Gerber 几何、Undo 与
Parasolid 会话对齐。详见 **§14**（菜单对话框逐项核对与实施批次）。

---

## 14. 菜单对话框 vs STpre 逐项核对与实施计划（M32）

> **目标：** 把 `cab_gui.py` 各菜单项打开的设置对话框，与 Cradle STpre
> （Pre_eng / 实机 UI）逐项核对，修正**界面设计与逻辑**不一致处。  
> **硬性例外：** `Mesh → Gridding/Meshing via STpre API` 及
> `cab_stpre_api` / Option Mesh 中对应勾选的 COM 流程**保持不变**。  
> **原则：** Menu chrome ≠ 内核忠实；优先修「错布局 / 错字段 / 错启用规则 /
> 假可用」；真 B-rep 内核另列，不阻断对话框对齐。

### 14.1 总判据

| 维度 | 估计 | 说明 |
|---|---|---|
| 菜单项覆盖 | ~85% | File/Edit/View/Part/Wizard/Mesh/Option/Help 表面齐全 |
| 对话框可用度 | ~68% | 大量 Edit CAD / Wizard 深度 / Environment 页仍为子集或代理 |
| 最高债务 | Edit CAD + View Setting + Environment 满页 + Part 专用对话框 | Sketch/Fan 已部分对齐，需回归核对 |

**Fidelity：** `chrome`=壳 · `MVP`=可用子集 · `gap`=与 STpre 明显不一致或缺失

### 14.2 明确排除（冻结）

| 项 | 路径 | 规则 |
|---|---|---|
| Gridding/Meshing via STpre API | `cab_gui` 菜单勾选、`cab_stpre_api.py`、Option→Mesh 勾选 | **禁止改**开关语义、COM 调用与结果合并 |
| 原生网格算法金标收敛 | `cab_grid` / `cab_mesh` 内核 | 不在本对话框对齐批次（属 M27） |

原生 Mesh **对话框 chrome**（Interference / Edit Mesh / Section / S-File）仍可做 UI 抛光。

### 14.3 菜单库存（核对表）

#### File

| 菜单路径 | 对话框/模块 | 保真 | 核对动作 |
|---|---|---|---|
| New / Open / Save / Save As | `cab_gui` | MVP | 确认冷启动 Initial Wizard 与 STpre Finish/Open/Cancel |
| Import… | `cab_import` | MVP | 过滤器文案与扩展名矩阵对齐 Pre |
| Export… | `_export_dialog` | MVP | S/XEMT/STL/XT/Property 过滤器与扩展绑定 |
| Print / Execute Solver / Post | `_print_*` / `_execute_*` | MVP | Solver cwd/env/restart；Post 场路径 |
| Recent / Exit | — | MVP | — |
| *(STpre)* 3DfindIT | — | gap | 明确不做或占位禁用 |

#### Edit

| 菜单路径 | 对话框/模块 | 保真 | 核对动作 |
|---|---|---|---|
| Undo / Redo | 快照栈 | MVP | 文案注明非 Parasolid 会话回滚 |
| Group / Deletion / Parts Conversion | `cab_edit_dialogs` | MVP | 字段标签/多选行为 vs Pre |
| Reconstruct of Part Facet | FacetAccuracy + facet_2 | MVP | Reconstruct 启用条件（需 XT） |
| Flipping Part Face | 拾取 + flip | MVP | Face target 提示与选中三角 |
| Part Face Paneling | 信息框 | **chrome** | → 拾取/选中部件生成 Panel |
| Sweep Part Face | FaceExtrusion | chrome | 字段对齐；失败诚实提示 |
| Alignment / Place / Mirror / Connected | 各 Dialog | MVP | 坐标单位 mm、Apply/OK |
| Boolean Operation | tess CSG | MVP | 标题/操作名对齐；注明非 B-rep |
| Shape change by Boolean / Cutting / Edit Solid / Simplify / FEM / Wrapping | 各 Dialog | chrome | 控件布局对齐 + 未实现禁用或代理标注 |
| Reset Computational Domain | Reset…Dialog | MVP | 与树双击 Edit Domain **区分**保持 |
| Edit Wiring / Placement of Image | chrome | chrome | 布局对齐；几何后续 |

#### View

| 菜单路径 | 保真 | 核对动作 |
|---|---|---|
| Fit / Reset / Planes / Mouse / Bars | MVP | — |
| Display All / Hide / Clipping | MVP | — |
| *(STpre)* View Setting / Dialog（热显示、部件列表…） | **gap** | 增加 Setting/Dialog 子菜单子集 |

#### Part

| 菜单路径 | 保真 | 核对动作 |
|---|---|---|
| Cuboid…Point | MVP | Scale+Attribute 字段与启用规则 |
| Enclosure / Fin / Peltier / 2R | 代理 | 对话框字段 vs 热属性（增量） |
| Fan（Sketch UVW + Condition） | MVP→核对 | 与实机截图字段逐项回归 |
| Axial / Blower | MVP | 布局对齐 Pre |
| Sketch Part | MVP→核对 | Model Type 启用规则；Size/Attribute |
| Pipe | MVP | 多点折线或明确子集标签 |
| Parts 工具栏 | gap | 与 Part 菜单项同步（含专用件） |

#### Wizard

| 菜单路径 | 保真 | 核对动作 |
|---|---|---|
| Initial Setting | MVP/gap | 步骤数/Import CAD 分步 vs STpre；文案 |
| Condition Setting | 子集 | Source/Humidity/Porous/Rad 深度；未实现物理 chrome |

#### Mesh（API 除外）

| 菜单路径 | 保真 | 核对动作 |
|---|---|---|
| Gridding…（原生） | MVP | 6 页签标签与启用；**不改** API 路径 |
| Meshing（原生） | MVP | 对话框选项 vs Pre；**不改** API |
| Interference / Edit Mesh / Section / S-File | MVP | 按钮/过滤器文案 |
| **Gridding/Meshing via STpre API** | — | **冻结** |

#### Option / Help

| 菜单路径 | 保真 | 核对动作 |
|---|---|---|
| Distance / Reference / Cut Cell / Selection / Viewer | MVP | 拾取联动（非仅 spin） |
| Environment / Detailed | ~8/13 页 | 补 Mouse、Tree/List、Drawing、Shortcut 等 |
| Help | MVP | — |

### 14.4 实施批次（按序）

```
D1  View Setting/Dialog + Parts 工具栏同步 + Edit Paneling MVP
D2  Option Environment 逼近 13 页（保留 use_stpre_api 语义）
D3  Edit chrome 对话框布局/启用规则/诚实标注（Boolean 文案等）
D4  Part：Fan/Sketch/Axial/Pipe 字段回归与启用逻辑
D5  Wizard：Initial 步骤模型 + Condition 深度 chrome
D6  File Import/Export 过滤器与 Solver/Post 对话框抛光
D7  Part 热专用属性（Enclosure/Fin/Peltier）增量
—— 全程不触碰 STpre API Gridding/Meshing ——
```

#### D1 ✅ View / 工具栏 / Paneling

- [x] View → (Setting) / (Dialog) 子菜单（Pre_eng 结构）
- [x] Parts 工具栏补 Enclosure / Plate·Pin Fin / Peltier / Two-Resistor
- [x] Edit → Part Face Paneling：Face 拾取 + Esc → Panel（AABB MVP）
- 触点：`cab_gui.py`、`cab_edit_ops.py`、`cab_parts.py`

#### D2 ✅ Option Environment 页

- [x] 13 Environment 页名对齐 + Mouse / Tree·List / Shortcut
- [x] Detailed 与 Environment 共用页集（入口标题区分）
- [x] **未改** `use_stpre_api` 勾选行为
- 触点：`cab_options.py`、`cab_gui._apply_options`

#### D3 ✅ Edit 对话框对齐（首轮）

- [x] chrome 项：能力说明标签（Boolean / ShapeChange / Edit Solid / Simplification / Wrapping）
- [x] Boolean Seamless 禁用 + 持久 CSG 标注
- [ ] 其余 Edit 对话框字段级二次核对（后续）
- 触点：`cab_edit_dialogs.py`、`cab_gui` 包装槽

#### D4 ✅ Part 对话框回归

- [x] Fan：Sketch UVW + Condition；PQ/温度/压力/整流写回 XML
- [x] Sketch Part：Cutout Select + Attribute heat/monitor/virtual 写回
- [x] Pipe：子集说明标签已存在
- 触点：`cab_parts.py`、`cab_sketch.py`、`cab_dialogs.py`

#### D5 ✅ Wizard

- [x] Initial：文档化 Project 合并 Import CAD；Purpose 边界文案诚实标注
- [x] Condition：Humidity / Porous / Radiation Grouping 加深写回；Source Option 加载
- 触点：`cab_wizards.py`、`cab_*wizard_pages.py`

#### D6 ✅ File / Solver-Post（首轮）

- [x] Import/Export/Open/Save As 英文过滤器与标题对齐 Pre
- [x] Execute Solver/Post 对话框字段标签（Working directory / Environment / Field）
- 触点：`cab_gui.py`、`cab_import.py`

#### D7 ✅ 热专用 Part 属性

- [x] Enclosure：模式选择 + Attribute/Condition 热字段写回
- [x] Plate/Pin Fin：厚度 / 半径 UI + XML/tess
- [x] Peltier：Current / ΔT / Hot face
- [x] Two-Resistor：Rjc / Rjb / Package power
- [x] AttributePanel `condition_values()` → `<parts>`（heat/temp/emissivity/monitor/virtual）
- 触点：`cab_parts.py`、`cab_dialogs.py`、`cab_gui.py`
- 测试：`tests/test_d7_thermal_cw.py`

### 14.5 验收标准

1. 每个批次：对照 Pre_eng 对应页或实机截图，字段名/默认值/启用规则一致或有文档化子集说明。  
2. Message 窗口对 chrome/代理操作有明确 INFO/WARN，无静默假成功。  
3. 回归：`tests/test_m32_dialog_align.py`、`tests/test_d7_thermal_cw.py`、`tests/test_sketch_part_dialog.py`、`tests/test_m24_m31_mvp.py`。  
4. **回归守卫：** 切换「Gridding/Meshing via STpre API」前后行为与改前一致。

### 14.6 进度跟踪

| 批次 | 状态 | 备注 |
|---|---|---|
| D1 | ✅ | View Setting/Dialog + 工具栏 + Paneling MVP |
| D2 | ✅ | Environment ≈13 页 + Mouse/Tree/Shortcut |
| D3 | ✅ 首轮 | Edit chrome 诚实标注 |
| D4 | ✅ | Fan Condition XML + Sketch Attribute 写回 |
| D5 | ✅ | CW Humidity/Porous/Rad 加深写回 |
| D6 | ✅ 首轮 | File 过滤器英文化 |
| D7 | ✅ | 热专用 Part 属性 + Attribute 写回 |
| API 路径 | 🔒 冻结 | 不实施 |

---

## 15. 全量对照刷新：不完整项与 M33+ 计划（2026-08-10）

> 自交互画布 `cab-gui-stpre-gap.canvas.tsx` 同步（Cursor canvases）。  
> **总判：** 菜单 UI ≈**88%**、可用深度 ≈**66%**。主债是 **Edit B-rep 内核**、**Meshing 金标**、**Condition Wizard 深度**、**Control 死角** —— 不是缺顶层菜单。  
> **冻结：** Gridding/Meshing via STpre API（§14.2）。

### 15.1 图例

| 深度 | 含义 |
|---|---|
| `impl` | 端到端可用，可存回 cab |
| `partial` | 有实现但为 AABB / CSG / 子集 / 代理 |
| `chrome` | 对话框或意图写回，无真实几何/物理 |
| `missing` | 未挂菜单或永久禁用 |
| `frozen` | 明确禁止改语义 |

### 15.2 不完整功能项清单

#### File
| 功能 | 深度 | 缺口 |
|---|---|---|
| Import 格式矩阵 | partial | XT/STL/STEP/SAT/OBJ/DXF/MDL；缺 IGES/IDF/主流 CAD；CADthru 已弃 |
| Assembly XT | partial | 已展开 bodies + 调色；命名/分组/库导入仍薄 |
| Export | partial | 缺 Neutral、选择性 Export Parts 全矩阵 |
| Execute Solver / Post | partial | Kicker/产品环境矩阵不完整 |
| 3DfindIT | missing | 建议放弃或禁用占位 |

#### Edit
| 功能 | 深度 | 缺口 |
|---|---|---|
| Undo / Redo | partial | XML 快照 ≠ Parasolid 会话 |
| Conversion / Sweep / Cutting / Align / Place / Mirror | partial | 变换或 AABB，非完整 B-rep |
| Boolean Operation | partial | tess CSG；非 `PK_BODY_boolean_2` |
| Shape-change Boolean / Edit Solid / Simplify / FEM / Wiring / Image | chrome | 诚实标注；多为 intent |
| Connected Region / Wrapping / Paneling | partial | marker / hull·AABB / AABB Panel |

#### View / Part / Wizard
| 功能 | 深度 | 缺口 |
|---|---|---|
| Thermal condition distribution | chrome | 色图叠加 pending |
| Editing Part Face / Contact TR | partial | 非独立全功能编辑器 |
| Enclosure / Fin / Peltier / 2R / Fan / Sketch | partial | 代理 + 属性写回；非完整热模型 |
| AC / Diffuser / 其余专用件 | missing | ~10+ 种未进菜单 |
| By Dialog / By Mouse 创建模式 | missing | — |
| Condition Setting 深度 | partial | ~29/150 页；Source 等仍浅 |

#### Mesh / Option / Tree / Control / Draw / Domain
| 功能 | 深度 | 缺口 |
|---|---|---|
| Gridding 原生 | partial | 圆柱/轴向弱；ChildBlock stub；顶点鼠标拾取 NYI |
| Meshing 原生 | partial | panel/开面；金标占用未收敛 |
| **Gridding/Meshing via STpre API** | **frozen** | **禁止改** |
| Environment 字段深度 | partial | 页齐；字段未全驱动运行时 |
| Register to library | missing | 右键禁用 |
| Condition / Aspect ratio 层 | chrome | ON → `_nyi` |
| Detail… / Domain boundary | chrome | NYI / 未接线 |
| Library | partial | 无 Place library part |
| Draw RMB | partial | 未对齐 Layout 全量右键 |
| Cylindrical / Axial Domain | partial | 类型标志，网格偏笛卡尔 |

### 15.3 跨切面优先级

| 优先级 | 缺口 |
|---|---|
| **Blocker** | Parasolid B-rep Edit（Boolean / Solid / Simplify） |
| **High** | Meshing 金标 + panel；CW 产品子集；拾取死角清理 |
| **Medium** | 格式回归；Library/专用件；热色图；Undo↔PS |
| **Low** | i18n；3DfindIT |

### 15.4 开发计划 M33+

原则：**内核与网格保真 → Control 死角 → Wizard 子集 → Library/专用件 → 格式抛光**；不触碰 API 网格路径。

| 里程碑 | 内容 | 验收要点 |
|---|---|---|
| **M33** Edit 内核跃迁 | `PK_BODY_boolean_2`；Edit Solid/Simplify 可删面子集会；Paneling/Sweep 拾取面 | Boolean 与 STpre 同类件体积差可量化；Undo 后几何一致 |
| **M34** Mesh 原生保真 | panel/开面 face-thin；圆柱·轴向类型标志；Edit 列表选点 | ✅ panel 占用 smoke；类型写回；列表 Select |
| **M35** Control/拾取清理 | Domain boundary 接线或删；Condition/Aspect 实现或禁用；Detail；Draw RMB 对齐 | 无死复选框 / 静默 `_nyi` |
| **M36** CW 产品子集 | Source 深度；未实现物理显式禁用；Basic Exercise E2E | 写回 XML 可重载 |
| **M37** Library + 专用件 + 热显示 | Register/Place；AC/Diffuser；热色图 | 右键 Register 可用 |
| **M38** 格式与抛光 | Import/Export 矩阵测试；IGES/IDF 决策；Solver/Post 文档 | CI 绿 |

**建议下一迭代：** M35 Control 死角 → M36 CW Source → M37 Library/热 → M38 格式。

### 15.5 已完成底座（保持）

M24–M31 MVP、M32 D1–D7、Layout 多选右键、Assembly XT 展开分色、CAB 读写、facet 显示、Domain/Gridding 规则逼近、Initial Wizard、快照 Undo。

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

### 11.1 一期（已完成）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 | File→Import x_t/STL + 自动三角化 | ✅ |
| M2 | 计算域设置闭环 | ✅ |
| M3 | Gridding 生成 mesh_block | ✅ |
| M4 | Meshing 生成 element + 导出闭环 | ✅ |
| M5 | 测试、逆向档案、格式规范 + 对话框框架 | ✅ |
| M6 | Mesh 菜单补全 + Wizard | ✅ |
| M7 | File/Edit/View/Part/Option/Help 补齐 | ✅ |
| M8–M11 | Sketch / 网格算法 / STEP·SAT / STpre API | ✅ |
| M12–M22 | Gridding 规则、CW 扩展、Draw Mesh 等 | ✅ |
| M23 | Initial Setting 自动弹出 + Edit 24 项 UI | ✅ |

### 11.2 二期（§13 / §14）

| 里程碑 | 内容 | 依赖 | 状态 |
|---|---|---|---|
| **M24** | Edit 内核脊柱（Boolean / Facet / 面拾取） | pskernel | ✅ MVP（Boolean=CSG） |
| M25 | 选择 / 测量 / View Setting | M24 拾取 | ✅ MVP |
| M26 | Import/Export 核心格式 | — | ✅ MVP |
| M27 | Mesh 保真（multiblock / 金标 / Cut Cell） | M9–M11 | ✅ stub/MVP |
| M28 | Condition Wizard 扩展 | M6/M21 | ✅ 子集 |
| M29 | Option / Environment 补全 | M7-5 | ✅ 子集 |
| M30 | Part 专用件包 | M7-4/M8 | ✅ 代理 |
| M31 | Solver/Post 产品化 | M7-1 | ✅ MVP |
| **M32** | 菜单对话框 vs STpre 逐项核对（§14 D1–D7） | M24–M31 | ✅ D1–D7 |
| **M33** | Edit 内核跃迁（PK Boolean / 面删 / 拾取面 Panel·Sweep） | M32 | ✅ |
| **M34** | Mesh 原生保真（panel face-thin / 圆柱·轴向标志 / Edit 列表选点） | M33 | ✅ |
| **M35–M38** | Control / CW / Library / 格式（§15） | M34 | 📋 进行中 |
| M32+ 抛光 | i18n / 热显示 / Wiring 几何等 | 并入 §15 M37–M38 | 后备 |

依赖主线：**M35**（§15）；**冻结** Gridding/Meshing via STpre API。

---

## 12. 文档同步清单

| 文档 | 更新内容 | 时点 |
|---|---|---|
| `DEV_PLAN.md` | 本计划随实施进度标记；§13–§15 与画布同步 | 持续 |
| `cab-gui-stpre-gap.canvas.tsx` | 不完整项看板 + M33+ | 2026-08-10 |
| `DEV_SUMMARY.md` | 导入/域/网格逆向档案；Edit/Wizard 实施记录 | M3/M5/M23+ |
| `CAB_FORMAT_SPEC.md` | 补 `mesh_control`/`element` 生成规范、x_t 成员合并规则 | M3/M4 |
| `CAB_GUI_DESIGN.md` | 更新菜单/对话框功能说明（含 Edit 24 项深度） | M1/M23/M24 |
| `README.md` | 使用流程（导入→域→网格→导出） | M5 |

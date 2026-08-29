# cab_gui 功能补齐开发计划（逆向驱动）

> 日期：2026-08-14（§18 全量对照刷新至 HEAD `ac4e3e7`；§15/§16 路线图仍有效）
> 仓库：`cabdecoding`
> 关联文档：[CAB_GUI_DESIGN.md](CAB_GUI_DESIGN.md)（UI 布局）、
> [DEV_SUMMARY.md](DEV_SUMMARY.md)（逆向档案 / §39 深度审计）、
> [CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)（cab 格式规范）
> 交互画布：`.cursor/projects/.../canvases/cab-gui-stpre-gap.canvas.tsx`
> 参考手册：`C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\Pre_eng\index.html`
> 对照源：Pre_eng `toc.csv` + `cab_gui.py` / `cab_edit_*` / `cab_parts` / wizards
>
> **当前主线：** §16 L1–L7 主体完成（7.1 panel scheme / 7.3 V8 scheme 待依赖）；§18 为最新全量对照基线。  
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
| 菜单项覆盖 | ~90%（2026-08-13 复核） | 8 菜单约 100 action 全部有 handler，无 `_nyi` 死入口 |
| 对话框可用度 | ~65% | Edit B-rep 内核、Meshing 金标、CW 深度、Control 死角为主债 |
| 最高债务 | Edit B-rep 内核（2/23 触达 PK）+ Meshing 高级参数仅存标志 + CW 18/24 禁用 + Control 死开关 | 详见 DEV_SUMMARY §39 |

**Fidelity：** `chrome`=壳 · `MVP`=可用子集 · `gap`=与 STpre 明显不一致或缺失

### 14.2 明确排除（冻结）

| 项 | 路径 | 规则 |
|---|---|---|
| Gridding/Meshing via STpre API | `cab_gui` 菜单勾选、`cab_stpre_api.py`、Option→Mesh 勾选 | **禁止改**开关语义、COM 调用与结果合并 |
| 原生网格算法金标收敛 | `cab_grid` / `cab_mesh` 内核 | 不在本对话框对齐批次（属 M27） |
| P3/P7 冻结 | — | **已解冻（2026-08-12，M39-P3/P7）**：Aspect/Condition 层绘制、Draw RMB 补全、i18n、3DfindIT、Wiring Gerber 恢复为可改进项 |
| STpre API 深度审计 | 只读分析（2026-08-13） | 已记录缺失能力（Mesher 7/15、MeshBlock 1/23、SetGridParam 6/13，见 DEV_SUMMARY §39.6）；实现仍冻结，解冻候选 P0–P4 |

原生 Mesh **对话框 chrome**（Interference / Edit Mesh / Section / S-File）仍可做 UI 抛光。

> 2026-08-13 审计结论：API 路径当前只覆盖“整体 Gridding + ExecuteElement +
> 合并回传”一条窄线；Others 页参数、internal region、指定部件网格、
> edge-contact、网格线编辑/删除/Detail、multiblock、GetNumElements 回读
> 均未接入。若解冻，按 P0（参数中继）→ P1（指定部件/回读）→ P2
> （Edit/Detail/Deletion API）→ P3（multiblock）→ P4（超时/错误处理）实施。

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

## 15. 全量对照刷新：不完整项与计划（2026-08-13）

> 自交互画布 `cab-gui-stpre-gap.canvas.tsx` 同步（Cursor canvases）。  
> **总判（HEAD `c0b1442`）：** 菜单 UI ≈**93%**、可用深度 ≈**72%**。  
> M33–M39 已交付 Boolean 真体路径、panel face-thin、圆柱 R/θ 近似、Control 层绘制 MVP、CW Source→S、Library Place、格式矩阵、Import Domain 自适应、缩放线框裁剪修复。  
> **主债：** 非布尔 B-rep（§16 L6）、Meshing 金标（L2/L7）、CW 面创建（L5）、Control 死角（L1/L4）。  
> **冻结：** Gridding/Meshing via STpre API（§14.2）。

### 15.1 图例

| 深度 | 含义 |
|---|---|
| `impl` | 端到端可用，可存回 cab |
| `partial` | 有实现但为 AABB / 子集 / 代理 / PK+回退 |
| `chrome` | 对话框或意图写回，无真实几何/物理 |
| `missing` | 未挂菜单或永久禁用 |
| `frozen` | 明确禁止改语义 |

### 15.2 不完整功能项清单

#### File / Domain
| 功能 | 深度 | 缺口 |
|---|---|---|
| Import 格式矩阵 | partial | **支持** XT/STL/STEP/SAT/OBJ/DXF/MDL；**不支持 IGES/IDF**（§15.6） |
| Assembly XT | partial | 展开 bodies + 调色；命名/分组仍薄 |
| Export / Solver / Post | partial | S/XEMT/STL/XT/Property；Kicker 环境矩阵薄 |
| 3DfindIT | partial | View→web 搜索；无本地 CAD 插件 |
| Import 后 Domain 自适应 | **impl** | `fit_domain_to_parts`（`c0b1442`）；同 CAD Data Size |

#### Edit
| 功能 | 深度 | 缺口 |
|---|---|---|
| Undo / Redo | partial | XML 快照 ≠ Parasolid 会话 |
| Boolean Operation | partial | `PK_BODY_boolean_2` 真 x_t 优先 + CSG 回退；transmit 失败→STL；对话框顶部文案可能过期（L1） |
| Solid / Simplify / Paneling / Sweep / Cutting / Wrap | partial | 多为 tess；`PK_FACE_delete_2` 已绑定未调用 |
| Shape-change Boolean / FEM / Wiring / Image | chrome | 意图/元数据 |

#### View / Part / Wizard
| 功能 | 深度 | 缺口 |
|---|---|---|
| Thermal condition distribution | partial | heat/temp tint MVP |
| 专用热件 / AC / Diffuser | partial | 已进菜单；几何代理 |
| By Dialog / By Mouse | missing | — |
| Condition Setting | partial | Source→S 已深；Create Face / region Select / 长尾物理仍浅 |

#### Mesh / Option / Control / Draw / Library
| 功能 | 深度 | 缺口 |
|---|---|---|
| Gridding 原生 | partial | R/θ 轴近似；分类仍偏笛卡尔；ChildBlock stub |
| Meshing 原生 | partial | panel face-thin 有；金标未钉；Others 未入算法 |
| **Gridding/Meshing via STpre API** | **frozen** | **禁止改** |
| Register / Place | partial | Project Parts + Place Base/Size |
| Condition / Aspect 层 | partial | MVP 线框已绘；非真分色/AR 场 |
| Detail / DomainBoundary / Point | partial | Detail 文案可能过期；首 face 拾取；Point 死开关 |
| Draw RMB | partial | Property/Register 已补；未全量对齐 Layout |
| 缩放线框裁剪 | **impl** | 相机裁剪放宽 + 外框免用户 clip |

### 15.3 跨切面优先级

| 优先级 | 缺口 |
|---|---|
| **Blocker** | 非布尔 B-rep（Solid / Simplify / Cutting / Wrap） |
| **High** | Meshing 金标 + Others 入算法；CW Create Face；Control 死角 |
| **Medium** | Boolean XT 持久化/文案；圆柱分类；Undo↔PS |
| **Low** | 完整 i18n；本地 3DfindIT；Wiring 几何 |

### 15.4 里程碑状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M33–M38** | Boolean / panel / Control / CW Source / Library / 格式 | ✅ |
| **M39 P0–P7** | 真体 Boolean/STL、Rθ、Place、Source→S、i18n/3DfindIT | ✅ |
| **Domain fit + clip** | Import 包围盒自适应；缩放线框 | ✅ `c0b1442` |
| **§16 L1–L10** | 难度阶梯（文案→金标→B-rep→Meshing…） | 📋 进行中（见 §16） |

**建议下一迭代：** L1 文案/死开关 → L2 金标 pytest → L3 Others 入算法。

### 15.5 已完成底座（保持）

M24–M32、Layout 多选右键、Assembly XT、CAB 读写、facet、Domain/Gridding 规则逼近、Initial Wizard、快照 Undo、M33–M39 交付物。

### 15.6 格式决策与 Solver/Post 启动说明（M38）

#### IGES / IDF — **不支持**

- **IGES（`.igs`/`.iges`）** 与 **IDF（`.emn`/`.emp` 等板级）**：**不支持**，不会加入 Import 过滤器。
- **决策：** 放弃原生 IGES/IDF 路径；几何请先用 **STEP（OCC）** 或 **Parasolid XT** 转入，或在上游 CAD 转出 STL/OBJ。
- 理由：无 Cradle CADthru / 专用 IDF 解析器；维护成本高于收益；STEP/OCC 已覆盖中性交换主路径。

#### 已支持 Import / Export（回归见 `tests/test_m38_format_matrix.py`）

| 方向 | 格式 | 备注 |
|---|---|---|
| Import | XT / STL / OBJ / STEP / SAT / DXF / MDL | STEP/SAT 需 OCP；XT 需 pskernel |
| Export | S / XEMT / STL / XT / Property XML | OBJ 无独立 Export 菜单项（可 STL） |

#### Execute Solver / Post（简要）

1. **Solver（`File → Execute Solver`）**  
   - 先导出临时 `.s`（及配套 `.xemt`）到所选工作目录；  
   - 在 Cradle `Programs_x64` 中查找 `stsol_Dx64net.exe` / `stsol_Sx64net.exe` / `stsol.exe`；  
   - 找到则 `cwd=工作目录` 启动；找不到则 WARN 并保留已导出 S 文件路径。  
   - 对话框字段：Working directory / Restart / Environment（子集；非完整 STpre Kicker）。

2. **Post（`File → Execute Post`）**  
   - 查找 `scPOST_Dx64net.exe` / `scPOST_Sx64net.exe` / `scPOST.exe`；  
   - 可选场数据路径传入；缺失可执行文件时信息框提示。  
   - **不**内嵌后处理；仅启动外部 Cradle Post。

3. **环境：** 依赖本机 Cradle CFD 安装与 `CRADLE_PROGRAMS`（或默认安装路径）；无 Cradle 时仅能导出 S/XEMT，不能本地求解。

---

## 16. 可用深度开发路线图（2026-08-13，按难度从易到难）

> 依据 DEV_SUMMARY §39 专项审计整理。每个“大项”可拆成细项，
> 细项即最小可提交单元：实现 → 快速 review → 刷新 DEV_PLAN/DEV_SUMMARY
> → pytest → commit/push。

### 16.1 总览（难度阶梯）

| 层级 | 主题 | 预计工作量 | 前置 | 状态 |
|---|---|---|---|---|
| L1 | 文案与死开关清理 | 0.5–1 天 | 无 | ✅ 2026-08-13 |
| L2 | 金标回归钉住 | 1–2 天 | 无 | ✅ 2026-08-13 |
| L3 | Others 参数进入原生算法 | 1–2 天 | L2（有金标可测） | ✅ 2026-08-13 |
| L4 | Control 交互补深 | 1–3 天 | L1 | ✅ 2026-08-13 |
| L5 | Condition Wizard 低垂果实 | 2–4 天 | L1 | ✅ 2026-08-13 |
| L6 | Edit B-rep 真实算子 | 1–2 周 | L3（测试习惯） | ✅ 2026-08-13（核心项） |
| L7 | Meshing 金标收敛 | 2–4 周 | L2/L3 | ✅ 7.1/7.3 待依赖，其余完成 |
| L8 | STpre API 深度（若解冻） | 1–2 周 | L3 参数中继先行 | ⏸ 保持冻结 |
| L9 | CW 产品级扩展（长尾） | 按需滚动 | L5 | 🔄 滚动（L5 铺底） |
| L10 | B-rep 全面接管（架构级） | 长期 | L6 | 🔄 拾取/测量 + x_t/STL 持久化闭环 |

### 16.2 L1 文案与死开关清理（易）

- 1.1 修正 Boolean 对话框顶部过期 note（仍写 “MVP: tessellation CSG”，
  实际 M33 起 PK 优先 + CSG 回退）；
- 1.2 修正 Control Detail… 过期文案（仍称 Condition/Aspect ratio
  “not drawn”，P3 已绘制）；
- 1.3 Point 层接线（显示 `kind=point` 的 marker actor）或移除勾选框
  （二选一，不能留死开关）；
- 1.4 Detail… 打开真实 per-layer 明细（只读：当前场景各层 actor 数量/
  部件列表）；
- 1.5 顺带确认 `cab-gui-stpre-gap.canvas.tsx` 已与 2026-08-13 刷新一致
  （Boolean PK、Condition/Aspect 绘制、AC/Diffuser、Domain fit 等）。

验收：无死开关；文案与实现一致；pytest 全绿。

状态：**✅ 已完成（2026-08-13）**，见 DEV_SUMMARY §40；`cab-gui-stpre-gap
.canvas.tsx` 过期行清理留待可选处理。

### 16.3 L2 金标回归钉住（易）

- 2.1 新增自动测试：`tests/box/box_new.s` vs `box_bm.s` 的 CXYZ 逐点
  与 PARTS box 占用比对（现在只有人工对比）；
- 2.2 用 `data/stpre_probe_*` JSON 对 `stpre_rules.auto1_*` /
  `auto3` 坐标做常驻回归；
- 2.3 tr03/ex4_e 曲面件网格线数回归（all/rep/plane/minmax 层级）；
- 2.4 Others 参数（edge_eps/face_search/element_threshold/panel_block_face
  等）XML round-trip 测试。

验收：金标成为 pytest 常驻项；STpre 升级后可重跑 probe 刷新 JSON。

状态：**✅ 已完成（2026-08-13）**，见 DEV_SUMMARY §41；tr03 曲面件 native
计数（65×115×115）与 STpre 参考的差距已作为已知偏差登记，留待 L7 收敛。

### 16.4 L3 Others 参数进入原生算法（易→中）

- 3.1 `edge_eps`：`classify_part_cells` 表面容差（候选单元外扩 eps、
  边界包含判定放宽）；
- 3.2 `element_threshold`：按 STpre 语义过滤过小间隔/单元（先黑盒对照
  再实现）；
- 3.3 `face_search`：panel 带宽度由固定“半单元”改为 face_search 参数；
- 3.4 角点投票（`samples="corners"`）从 GUI 接线，或按 STpre 默认策略
  固化；
- 3.5 `panel_block_face` / `flux_face_check` / `solid_scheme` /
  `panel_scheme` 至少先影响 S/XEMT 输出字段（先语义后算法）。

验收：box/panel 占用不回归，曲面件与金标偏差缩小，参数有可测效果。

状态：**✅ 已完成（2026-08-13）**，见 DEV_SUMMARY §42；`panel_block_face` /
`flux_face_check` / V8 scheme 的 S/XEMT 语义归入 L7。

### 16.5 L4 Control 交互补深（中）

- 4.1 Vertex 拾取：cell picker 命中后吸附最近顶点，状态栏输出坐标；
- 4.2 DomainBoundary 空间拾取：按点击射线与 domain frame 求交选面
  （替换“总是选第一个 face”）；
- 4.3 Condition 层：按条件类型给域边界着色（flux/wall/heat 分色）；
- 4.4 Aspect ratio 层：逐 cell 计算 dx/dy/dz 最大比并着色/线宽；
- 4.5 Face division 层：真实面划分线（与 element 层区分）。

验收：每个 selection target 与 layer 都有可见/可测效果。

状态：**✅ 已完成（2026-08-13）**，见 DEV_SUMMARY §43；Vertex 吸附、
DomainBoundary 射线拾取、Condition 分色、Aspect ratio 分色、
Face division 表面网格线均已接线并有测试。

### 16.6 L5 Condition Wizard 低垂果实（中）

- 5.1 BC face create/edit：在 DomainBoundary 上按区域创建轴对齐矩形面，
  支持编辑（解锁 Source/Area 的 Create/Edit Face…）；
- 5.2 region Select：Source/Area 页启用多选并写回多个 region 绑定；
- 5.3 Power-law 风廓线写回（Initial Purpose external_buildings）；
- 5.4 Enclosure AENT 系数写回（external_enclosure）；
- 5.5 Source 值类型扩展（time series 等常用项）。

验收：原禁用的 Create/Edit/Select 可用；写回 XML 可重载。

状态：**✅ 已完成（2026-08-13）**，见 DEV_SUMMARY §44；BC face
create/edit、region 多选绑定、Power-law 与 Enclosure A/B/eps 写回均已
实现并有测试；局部 face 的 S/XEMT 导出映射留待后续。

### 16.7 L6 Edit B-rep 真实算子（难，按子项递进）

- 6.1 Cutting 真平面裁剪：tessellation 三角形平面裁剪 + 缝合（先 tess 级）；
- 6.2 Cutting PK 级：用 pskernel 平面/曲面分割 → x_t 持久化；
- 6.3 ShapeChangeBoolean 真布尔：复用 `boolean_mesh_parts` 应用到
  Part A（替代 intent 注解）；
- 6.4 Wrapping 真凸包：tess 点云凸包（scipy/quickhull）+ 可选偏移 →
  STL/XT 持久化；
- 6.5 Shape Simplification QEM：边坍缩简化（容差滑块）→ 预览/Apply；
- 6.6 Edit Solid 面级编辑：face pick → 移动/删除/补孔；
- 6.7 持久化回写：修改后 tess 优先 `PK_PART_transmit` 成 x_t，失败退
  STL member + 重载路径；
- 6.8 拓扑拾取：face/edge/vertex（PK_TOPOL 或 tess 拓扑），为后续算子
  铺路。

验收：每个算子有金标几何用例（体积/形状断言）且保存重开不丢几何。

状态：**✅ 核心项已完成（2026-08-13）**，见 DEV_SUMMARY §45；
6.1/6.3/6.4/6.5/6.7 已落地；6.2（PK 级平面分割）、6.6（面级移动/补孔）、
6.8（拓扑拾取）记录为后续轮次。

### 16.8 L7 Meshing 金标收敛（难）

- 7.1 panel scheme 黑盒补充（speaker/开放面）→ 规则 → native 实现；
- 7.2 run-length 精确编码：对齐 STpre box list 结构（box/tr03 金标）；
- 7.3 V8 scheme：solid_scheme/panel_scheme 改变占用合并规则；
- 7.4 边界 element face：domain boundary 面生成 + flux face 重复检查；
- 7.5 圆柱坐标元素分类（R/θ/Z cell 索引，替代“类型标志+笛卡尔分类”）；
- 7.6 multiblock native：ChildBlock 参与 gridding（Basic Setting 中
  “Consider only child-blocks” / “lower level block” 两项启用）；
- 7.7 性能：并行分类（进程池/numba）、大模型内存优化、进度可中断。

验收：简单件与 STpre 完全一致；曲面件逐 cell 占用比对；大模型可跑。

状态：**✅ 核心完成（2026-08-14）**：7.5 圆柱分类、7.2 占用金标
（20/20 box）、7.4 通量面查重、7.6 multiblock native（真实 STpre
嵌套块格式 + CS/C 合并轴）、7.7 并行分类已完成（见 DEV_SUMMARY
§46/§48/§51）；7.1/7.3 依赖外部黑盒与元素形状合并语义，已登记。

### 16.9 L8 STpre API 深度（若解冻；保持冻结则跳过）

- 8.1 P0 参数中继：`domain_type`（inner/outer）、`division_scale`、
  Others 页参数写入 relay（先行项，不依赖解冻大方向）；
- 8.2 `ExecutePartsElement` + `GetNumElements` 回读（Element # 与
  STpre 一致）；
- 8.3 `GetNumEdgeContact` / `RemoveEdgeContact`；
- 8.4 `SetSelectGrid` / `SetDivideArray` / `SetDetailGrid` / `DeleteGrid`
  （与六页 tab 对应）；
- 8.5 multiblock：`CreateBlock` / `SetRange` / `SetActiveBlock` / `Update`；
- 8.6 COM 超时与错误对话框处理；保留“已有 STpre 实例拒绝 attach”。

验收：开关开启时六页 tab 与 API 行为一致；参数回读校验通过。

状态：**⏸ 保持冻结（2026-08-13）**；P0–P4 候选见 DEV_SUMMARY §39.6 /
§47，待解冻后实施。

### 16.10 L9 CW 产品级扩展（长尾，按需）

- 9.1 常用条件：porous anisotropic、radiation grouping 细节、humidity
  深度、time series；
- 9.2 初始场/湍流初始场、总压/静压组合边界；
- 9.3 高级物理页（particle / moving object / electric / electrostatic…）
  按产品需求排序；
- 9.4 对 122 个手册对话框建立“支持/子集/禁用”矩阵并逐步解锁。

验收：每页有写回 + 重载 + 测试；禁用项保持诚实标注。

状态：**🔄 滚动**（L5 已铺底；下一批候选见 DEV_SUMMARY §47）。

### 16.11 L10 B-rep 全面接管（架构级）

- 10.1 x_t 双向持久化：所有编辑算子输出真实 body；
- 10.2 Undo/Redo 基于 PK 会话历史或快照 diff；
- 10.3 全格式矩阵扩展（MDL/DXF/OBJ/IDF…）；
- 10.4 拾取/测量/参考/距离全线打通。

验收：工业用例可从导入 → 编辑 → 网格 → 求解全程不丢几何。

状态：**🔄 续执行（2026-08-14）**：拾取/测量/参考打通（§49）；
x_t/STL 双向持久化闭环（§50：布尔 x_t 成员引用 + body_files 登记 +
重开按源成员重映射）已完成；PK Undo/Redo、全算子 x_t 输出、格式矩阵
出口为后续项。

### 16.12 推进建议

- L1–L3 收益/成本比最高，建议先做；L4–L5 可与 L3 并行；
- L6–L7 依赖金标与测试习惯（L2/L3），串行推进；
- L8 视“Gridding/Meshing via STpre API”是否解冻决定，P0 参数中继
  可先行；
- L9–L10 为长尾/架构项，滚动排期；
- 每完成一个细项，更新本路线图状态列并自动 commit/push。

---

## 17. 几何编辑 / 网格 vs STpre（2026-08-13；非 scFLOWpre）

> 画布：`cab-edit-mesh-completeness.canvas.tsx`。  
> **产品边界：** 本仓对齐 **STpre / scSTREAM**（笛卡尔结构网格）。  
> **scFLOWpre** 是 scFLOW 非结构前处理（表面网格、hex-core、棱柱层、多面体），
> 不是本仓补丁级对标对象。

### 17.1 完整度（相对 STpre）

| 切面 | 估计 | 说明 |
|---|---|---|
| 菜单入口 | ~100% | 无 `_nyi` 死菜单 |
| 分区平均可用深度 | ~72% | Edit/Wizard/Mesh 拉低 |
| Edit 算子平均保真 | ~40% | 仅 Boolean + Facet 重建触达 PK |
| 网格管线平均保真 | ~53% | 笛卡尔 Gridding/盒占用强；Others/圆柱/panel/ChildBlock 弱 |

### 17.2 几何编辑主债

- **PK：** Boolean（真 x_t 优先，transmit 常退 STL）、Facet 重建。
- **tess：** Flip / Paneling / Sweep / Edit Solid 删三角；`PK_FACE_delete_2` 未调用。
- **intent：** Cutting=AABB 切半；ShapeChangeBoolean 只写注解；Wrap/Simplify 近似。
- **XML：** Mirror/Align/Place/Group 变换级已可用。

### 17.3 网格主债

- **已齐：** box 金标 CXYZ/PARTS（L2）；Domain Import 自适应；笛卡尔 auto1 规则。
- **未齐：** Others 参数未进 `classify_*`；tr03 计数偏差（L7）；panel 半单元带；
  贪心盒合并 ≠ STpre run-length；圆柱分类仍 XYZ；ChildBlock stub；API 冻结。

### 17.4 下一步（同 §16）

L3 Others 入算法 → L6 Cutting/ShapeChange/face_delete 真几何 → L7 金标收敛。  
不要用 scFLOWpre 的八叉树/棱柱层指标衡量本仓。

---

## 18. 全量对照：代码现状 vs STpre（2026-08-14，HEAD `ac4e3e7`）

> 独立复核（代码走查 + 全仓测试实测）+ 官方手册量化基准
> （`Manuals/ST/HTML/Pre_eng/toc.csv`，717 条）+ 已有逆向/黑盒数据。
> §13/§15 为过程快照，本节为最新基线，可复现口径见 18.2/18.3。
> **产品边界不变**：本仓对齐 STpre / scSTREAM（笛卡尔结构网格），
> 不用 scFLOWpre 的八叉树/棱柱层指标衡量。

### 18.1 结论摘要

| 维度 | 评估 | 依据 |
|---|---|---|
| 菜单入口覆盖 | ~93%（无死菜单） | 8 菜单约 43+ action 全有 handler，`_nyi` 仅 4 处兜底 |
| 可用实现深度（加权） | ~70–72% | 被 Edit B-rep / CW / Part 专用件 / Meshing 金标拉低 |
| 几何编辑内核保真 | ~40% | Edit 23 项中仅 Boolean + Facet 重建触达 Parasolid 内核 |
| 网格管线保真 | ~53% | 笛卡尔 Gridding/盒占用已对齐金标；panel/V8/圆柱分类未收敛 |
| 测试 | 332 通过 / 4 跳过（`ac4e3e7`） | 本沙箱实测 284 通过 / 4 跳过 / 40 失败 / 8 错误，均为环境性 |

> 测试说明：本沙箱因 `.pytest_tmp_*` 与 `tests/tmp*` 带 deny-ACL 遗留目录、
> pskernel/STpre COM 会话不可用，纯逻辑测试 284 通过；失败/错误项全部为
> 环境性（临时目录写权限 + pskernel DLL + STpre 会话），非逻辑回归。
> 文档记录的最后全绿基线为 **332 通过 / 4 跳过**。

### 18.2 代码现状（独立核查，非仅凭文档）

- Git：HEAD `ac4e3e7`（2026-08-14），工作区干净，`main`。
- 规模：约 30 个 Python 模块、约 3.5 万行；核心
  `cab_gui.py`(5077) / `cab_cwizard_pages.py`(6219) / `cab_wizards.py`(3415) /
  `cab_dialogs.py`(3379) / `cab_parts.py`(2001) / `cabxml.py`(1675)。
- 分层（代码存在性已核实）：
  `cab_container.py`（MSCF/MSZIP 容器）→ `cabxml.py`（stpre XML 模型）→
  `cab_import.py`/`cab_occ.py`（几何导入）→ `ps_facet2_nodes.py`/`ps_tessellate.py`
  （Parasolid 面片）→ `cab_grid.py`/`cab_mesh.py`（网格）→ `s_export.py`/
  `xemt_export.py`（导出）→ `cab_gui.py` + 各对话框（GUI）。
- 菜单/死入口：`cab_gui.py` 约 43 处 `addAction/createAction`；全仓 `_nyi`
  仅 4 处（Layout context 与未知 Part kind 兜底），无死菜单。

### 18.3 STpre 全量功能面（量化基准，toc.csv 共 717 条）

| 菜单 | 手册条目 | 说明 |
|---|---:|---|
| File | 13 | Open/Save/SaveAs/Import/Export/3DfindIT/Print/Solver/Post/Recent/Exit |
| Edit | 26 | 24 项 + 菜单页 |
| View | 4 | Setting/Dialog/Toolbar（Clipping/热显示/部件列表） |
| Part | 38 | 基础体 9 + 热专用件 ~14 + Sketch 8 模型 + Pipe 等 |
| Mesh | 13 | Gridding(6 标签)/Meshing/Interference/Edit Mesh/Cross-Section/S-File |
| Option | 11 | Cut Cell/Parametric/Selection/Distance/Reference/Mouse/Detailed/Viewer |
| Wizard | 270 | Initial ~11 页 + **Condition Setting ~250+ 页** |
| Help | 3 | — |

> 量级关键：STpre 的 Condition Wizard 是 **~250+ 页物理条件长尾**，而 cab
> 条件类型约 15 组——这是最大的结构性差距来源。

### 18.4 分区覆盖对比（cab vs STpre）

| 区域 | STpre 条目 | cab 菜单覆盖 | 可用深度 | 主缺口 |
|---|---:|---:|---:|---|
| File | 13 | 完整 | 高 | Import 无 IGES/IDF、无本地 3DfindIT；Solver/Post 仅外部启动 |
| Edit | 26 | 24/24 | 低（~40%） | 见 18.5 Blocker |
| View | 4(子菜单) | 完整 | 中高 | 已挂项可用；热显示/Aspect 为 MVP 线框 |
| Part | 38 | ~14 种 | 中 | 热专用件为几何代理、缺完整热属性模型 |
| Wizard | 270 | 2 入口 | 低 | CW 仅 ~26 页、18/24 分析类型禁用 |
| Mesh | 13 | 6/6 | 中（~53%） | panel/V8/run-length 未收敛 |
| Option | 11 | ~4–5 | 中 | 缺 Cut Cell/Parametric Study/Selection 深度 |

### 18.5 深度差距（chrome ≠ 内核，按严重度）

#### 🔴 Blocker —— 非布尔 B-rep 编辑（Edit 23 项中仅 2 项触达 Parasolid 内核）

- **真实内核**：Boolean（`PK_BODY_boolean_2`）、Reconstruct of Part Facet（`PK_TOPOL_facet_2`）。
- **tess 级（改三角网、不写回 x_t body）**：Flipping / Part Face Paneling / Sweep / Edit Solid（删三角）/ Part Simplification。
- **近似/占位**：Cutting 已从 AABB 切半升级为真平面裁剪（仍 tess 级）、Wrapping=凸包、Shape Simplification=顶点抽稀。
- **意图/XML 级**：Shape change by Boolean、FEM Conversion、Wiring、Image 等仅写元数据。
- **未做**：`PK_FACE_delete_2` 已绑定未调用；PK 级平面分割；面/边/顶点**拓扑拾取**（现为 cell 拾取 + 顶点吸附）。

#### 🔴 High —— Condition Wizard 深度（~250 页中仅覆盖 ~15 组条件）

- Analysis Types 24 项中 **18 项禁用**（Diffusion/Plant canopy/Moving object/Solar/Lamp/Reaction/Ventilation/Fusion/Marangoni/Topology/Particle/Aircon/Current/Electrostatic/PCM/MSC CoSim/BCI-ROM/Thermoregulation）。
- 实际启用仅：Flow/Turbulence、Heat、Humidity、Porous、Radiation、Free surface。
- 已实现子集有**诚实禁用 + tooltip**（优点，避免假成功）；Source→S 导出已打通、BC face create/edit、region 多选、Power-law/enclosure 写回已落地。

#### 🔴 High —— Part 专用件（38 项中 cab 约 14 种）

- 已有：Cuboid/Hexahedron/Cylinder/Cone/Sphere/Panel/Point/Fan/Axial/Blower/Sketch/Pipe + Enclosure/Plate·Pin Fin/Peltier/Two-Resistor/AC/Diffuser（后两者为 cuboid/conical 几何代理）。
- 缺完整热属性模型：Delphi/HeatPipe/Multiple-Resistor/Card Guide/Slit Punching/Anemostat 等。

#### 🟠 High —— Meshing 金标

- **已对齐**：box 金标 CXYZ 逐点一致 + PARTS 占用 `20 39 20 39 20 39`；auto1 规则 13/13；占用金标 **20/20 box 用例一致**；圆柱 R/θ 分类、multiblock native（真实嵌套块 + CS/C 合并轴）、并行分类已完成。
- **未收敛**：panel scheme 黑盒语义（STpre 对开放面 `part_boxes={}`）、V8 scheme（solid/panel_scheme 合并）、run-length 精确编码（现为贪心 AABB 合并）、tr03 曲面件网格线数偏差（native 65×115×115 vs STpre 59×118×121）。

#### 🟠 Medium —— Import/Export 格式矩阵

- Import：XT/STL/OBJ/STEP/SAT/DXF/MDL 已支持；**IGES/IDF 明确放弃**（§15.6）。
- Export：S/XEMT/STL/XT/Property XML；无 Neutral 全矩阵。

#### 🟡 Medium —— STpre API 路径（已冻结）

- COM relay 仅用 Mesher **7/15**、MeshBlock **1/23**、SetGridParam **6/13** 个方法；
- Others 页参数、internal region、指定部件网格、edge-contact、multiblock、GetNumElements 回读均未接。
- 保持冻结（策略明确：检测到用户已开 STpre 时拒绝 attach，防杀用户实例）。

### 18.6 已对齐 / 优势（保持，不宜推倒）

- **CAB 容器**：MSCF + MSZIP 跨块历史解压/重打包，与 Windows `expand` 逐字节一致（md5 全同）。
- **XML 往返**：两个 XML 成员字节级稳定序列化（BOM/注释/缩进/未知元素零丢失）。
- **Parasolid 几何显示**：`PK_TOPOL_facet_2` 表路径（与 STpre 同源，经反汇编确认）为主，GO 回退，含自适应面片容差。
- **网格算法**：auto1 每轴分配公式、几何比求解器、内区 P 闭式公式均来自 DLL 反汇编（`STpreBase_Bx64.dll`），黑盒 13/13 验证。
- **Initial Wizard** 完整 6 步（含冷启动自动弹出）。
- **测试基建**：金标回归已钉住（`box_bm.s` vs `box_new.s` 自动对比）。

### 18.7 建议优先级（下一迭代）

1. **P0 环境清理**：删除带 deny-ACL 的 `.pytest_tmp_*` / `tests/tmp*` 遗留目录（当前阻塞 pytest 收集），恢复全绿基线。
2. **P1 Edit B-rep 保真**：`PK_FACE_delete_2` 接线、PK 级平面分割、拓扑拾取（face/edge/vertex）——把 Edit 从“对话框齐”推向“CAD 准备可用”。
3. **P2 Meshing 金标收敛**：panel scheme 黑盒语义还原、V8 scheme、run-length 编码。
4. **P3 Condition Wizard 扩展**：按产品需求从 18 个禁用分析类型中逐步解锁（porous anisotropic / radiation grouping / time series / 湍流初始场优先）。
5. **P4 格式矩阵出口**：MDL/DXF/OBJ 出口 + 完整往返回归。

---

## 19. 按差距程度排序的改进开发计划（2026-08-14）

> 承接 §18.7。以「差距严重度」为主序、依赖与收益/成本为次序，把
> §18.5 的差距逐条展开为可执行里程碑。每阶段含：目标 / 现状差距 /
> 任务分解 / 验收标准。状态随推进回填。

### 19.1 总览（严重度 → 阶段）

| 阶段 | 对应差距 | 严重度 | 预计工作量 | 前置 | 状态 |
|---|---|---|---|---|---|
| **A** | 非布尔 B-rep 编辑 | 🔴 Blocker | 2–3 周 | — | 📋 |
| **B** | Meshing 金标收敛 | 🟠 High | 2–4 周 | A（测试习惯）/ 金标 | 📋 |
| **C** | Condition Wizard 深度 | 🔴 High | 3–6 周（滚动） | L5 已铺底 | 📋 |
| **D** | Part 专用件热模型 | 🔴 High | 1–2 周 | D7 热字段 | 📋 |
| **E** | Import/Export 格式矩阵 | 🟠 Medium | 1–2 周 | M38 已有 | 📋 |
| **F** | STpre API 深度 | 🟡 Medium | 1–2 周（若解冻） | 冻结解除 | ⏸ |
| **G** | Undo↔PS / i18n / 3DfindIT / Wiring | 🟡 Low | 滚动 | 各阶段 | 📋 |

依赖主线：A → B → C（几何/网格/物理三层递进）；D/E/G 可并行；F 独立（冻结）。

---

### 19.2 阶段 A（Blocker）：Edit B-rep 内核补全

**目标**：把 Edit 从「对话框齐 + 少数真内核」提升到「几何准备可用」——
所有 Edit 算子的产物是**真实 Parasolid body**，且保存重开不丢几何。

**现状差距**（§18.5）：23 项中仅 Boolean（`PK_BODY_boolean_2`）与
Reconstruct of Part Facet（`PK_TOPOL_facet_2`）触达 PK；Cutting/Wrapping/
Simplify 为 tess 级；Shape change Boolean 已接真布尔（L6.3）；`PK_FACE_delete_2`
已绑定未调用；面/边/顶点**拓扑拾取**缺失；Undo 仍是 XML 快照。

| 子项 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| A1 拓扑拾取 | `PK_BODY_ask_faces/ask_edges/ask_vertices` + 屏幕射线→拓扑实体映射（替换 cell 拾取），作为 Edit Solid/Paneling 前置 | 3–5 天 | 点选面/边/顶点返回真实 PK tag；状态栏输出 |
| A2 `PK_FACE_delete_2` 接线 | Edit Solid「删面」从三角网删除改为拓扑面删除，删后 `PK_BODY_export` 写回 x_t | 2–3 天 | 删面后 body 拓扑合法、体积符合预期、可重开 |
| A3 PK 级平面分割（Cutting） | 用 pskernel 平面/曲面分割替代 tess 裁剪，结果 x_t 持久化（tess 路径保留为回退） | 3–5 天 | 平面切 box 得两闭合实体；体积守恒；重开一致 |
| A4 全算子 x_t 输出 | Cut/Wrap/Simplify/Boolean 结果统一走 `PK_PART_transmit` 写 x_t（失败退 STL + polygon，沿用 §50 重映射） | 3–5 天 | 每个算子的结果部件在 cab 重开后仍为可编辑 body |
| A5 Undo↔PS 一致性 | Undo/Redo 与 Parasolid 会话历史或快照 diff 对齐（至少：Edit 后 Undo 恢复几何与 XML 双一致） | 3–5 天 | Edit→Undo→Redo 后几何与 XML 均一致 |

**验收标准**：A1–A5 各有金标几何用例（体积/形状断言）且「编辑→保存→重开」
不丢几何；Edit 触达 PK 的算子数从 2 提升到 ≥6（Boolean/Facet/Cutting/
Edit Solid/Wrap/Simplify）。

---

### 19.3 阶段 B（High）：Meshing 金标收敛

**目标**：与 STpre 在**占用与行程编码**上达到可复现一致（不止 CXYZ 坐标）。

**现状差距**（§18.5）：box CXYZ/PARTS 已对齐、auto1 13/13、占用 20/20 box、
圆柱 R/θ 分类、multiblock native、并行分类已完成；**未收敛**：panel scheme、
V8 scheme、run-length 精确编码、tr03 曲面件网格线数偏差（native 65×115×115
vs STpre 59×118×121）。

| 子项 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| B1 panel scheme 黑盒补充 | 还原 STpre 对开放面/panel 的 `part_boxes={}` 语义：用 speaker/开放面 x_t 多实例探测，归纳「实体占用 vs 面占用」判定规则 | 3–5 天 | 新增 `data/stpre_probe_*panel*.json`；规则文档化 |
| B2 panel 占用 native 实现 | 按 B1 规则实现 `classify_panel_cells` 精确语义（替换「半单元带」近似） | 2–4 天 | panel 用例与 STpre `part_boxes` 逐 cell 一致 |
| B3 V8 scheme | 还原 solid_scheme/panel_scheme 改变占用合并的语义（依赖 multiblock 元素形状），接入 `classify_cells` | 3–5 天 | 两 scheme 开关切换后占用/导出字段符合金标 |
| B4 run-length 精确编码 | 用 PK 或贪心→RLE 改写 `_merge_boxes`，对齐 STpre box list 行程编码（box/tr03 金标） | 3–5 天 | `box_new.s` 与 `box_bm.s` 的 PARTS 行数与结构一致 |
| B5 曲面件计数收敛 | 定位 tr03 native 65×115×115 vs STpre 59×118×121 的偏差来源（顶点检测层级 + threshold 合并），逐 cell 对比 | 3–5 天 | tr03/ex4_e 曲面件网格线数与 STpre 参考一致 |

**验收标准**：新增 `test_golden_reference.py` 常驻项覆盖 B1–B5；简单件与
STpre 完全一致，曲面件逐 cell 占用比对通过；大模型可跑（并行分类已就绪）。

---

### 19.4 阶段 C（High）：Condition Wizard 深度扩展

**目标**：把 CW 从「~26 页核心子集」扩展到「覆盖主要产品物理场景」，并保持
诚实禁用（不假成功）。

**现状差距**（§18.5）：Analysis Types 24 项中 18 项禁用；STpre Condition 手册
约 250+ 页；cab 条件类型约 15 组。已落地：BC face create/edit、region 多选、
Power-law/enclosure 写回、Source→S 导出。

| 子项 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| C1 常用 BC 深挖 | porous anisotropic、radiation grouping 细节、humidity 深度、time series、初始湍流场、总压/静压组合边界 | 1–2 周 | 每页有写回 + 重载 + 测试；`.s` 导出字段正确 |
| C2 Source 全类型 | 补齐 `_SRC_VOL_TYPES/_SRC_AREA_TYPES` 到 STpre 全量（含 time series/函数） | 3–5 天 | 每个 Source 类型可往返（写回→重载→导出） |
| C3 高级物理分批解锁 | 按产品需求排序（建议：Solar→Particle→Diffusion→Ventilation→Reaction→…），每批 1–2 个分析类型 | 滚动 | 解锁项有产品页 + 写回 + 测试 |
| C4 支持矩阵 | 对 250+ 手册对话框建立「支持/子集/禁用」矩阵，作为解锁顺序与验收清单 | 2–3 天 | 矩阵入库（`docs/cw_matrix.md`），禁用项带 tooltip |

**验收标准**：C1–C2 每项可往返且 `.s` 一致；C3 每批独立提交；C4 矩阵随解锁
同步更新；未实现物理保持 `setEnabled(False)` + 诚实 tooltip。

---

### 19.5 阶段 D（High）：Part 专用件热属性模型

**目标**：把 Part 菜单从「几何代理」提升到「几何 + 完整热属性」产品级。

**现状差距**（§18.5）：已有 Cuboid…Point 基础体 + Enclosure/Plate·Pin Fin/
Peltier/Two-Resistor（含基本热字段）+ AC/Diffuser（几何代理）；缺 Delphi /
HeatPipe / Multiple-Resistor / Card Guide / Slit Punching / Anemostat 及完整
热属性模型。

| 子项 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| D1 补齐专用件菜单 | Delphi / HeatPipe / Multiple-Resistor / Card Guide / Slit Punching / Anemostat 进 Part 菜单 + 几何 + 热字段 | 3–5 天 | 与 STpre Part 菜单 38 项对齐至 ≥20 种 |
| D2 热属性完整模型 | 各专用件热参数（Rjc/Rjb/Power、PQ 曲线、Peltier ΔT、AC 制冷量等）写入 `<parts>` 并进入 `condition_values()` | 3–5 天 | 热字段写回 XML 可重载；`.s`/`.xemt` 导出正确 |
| D3 AC/Diffuser 真几何 | 按手册几何替换 cuboid/conical 代理（含 4 方向/2 方向/壁挂/便携/室外机 + 风口） | 3–5 天 | 几何与手册一致，占用/网格正确 |

**验收标准**：Part 菜单 ≥20 种、热属性往返 + 导出正确、AC/Diffuser 非代理。

---

### 19.6 阶段 E（Medium）：Import/Export 格式矩阵补全

**目标**：把格式矩阵从「smoke」提升到「全矩阵 + 往返回归」。

**现状差距**（§18.5）：Import 支持 XT/STL/OBJ/STEP/SAT/DXF/MDL；Export 支持
S/XEMT/STL/XT/Property XML；IGES/IDF 明确放弃（§15.6）。缺 MDL/DXF/OBJ 出口
与全矩阵自动化回归。

| 子项 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| E1 出口补齐 | MDL（OBJ 等价）/ DXF（3DFACE）/ OBJ 导出 | 2–4 天 | 各格式导出可被上游 CAD 打开 |
| E2 全矩阵回归 | `test_m38_format_matrix.py` 扩展：DXF/MDL/STEP/SAT 导入 + S/XEMT/XT/Property/MDL/DXF/OBJ 导出往返；GUI 过滤器联动 | 2–3 天 | 矩阵 100% 通过；OCC 相关保留 skip |

**验收标准**：格式矩阵双向往返全绿，纳入 CI；IGES/IDF 保持显式拒绝。

---

### 19.7 阶段 F（Medium）：STpre API 深度（若解冻）

> 当前**冻结**（§14.2）。下列为解冻候选，按序实施；不解除前仅文档化。

**现状差距**（§18.5）：COM relay 仅用 Mesher 7/15、MeshBlock 1/23、
SetGridParam 6/13。

| 子项 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| F1 参数中继（P0） | `domain_type`（inner/outer）+ `division_scale` + Others 页参数写入 relay | 2–3 天 | 开关开启时 Others 参数生效 |
| F2 指定部件/回读（P1） | `ExecutePartsElement` + `GetNumElements` + `GetNumEdgeContact`/`RemoveEdgeContact` | 3–5 天 | 部件网格/Elen# 与 STpre 一致 |
| F3 Edit/Detail/Deletion API（P2） | `SetSelectGrid`/`SetDivideArray`/`SetDetailGrid`/`DeleteGrid`（对应六页 tab） | 3–5 天 | 六页 tab 在 API 下行为一致 |
| F4 multiblock（P3） | `CreateBlock`/`SetRange`/`SetActiveBlock`/`Update` | 3–5 天 | multiblock 经 API 生成 |
| F5 超时/错误（P4） | COM 超时与错误对话框处理；保留「已有实例拒绝 attach」 | 1–2 天 | 无挂起 UI；策略不变 |

---

### 19.8 阶段 G（Low）：收尾项

| 子项 | 内容 | 状态 |
|---|---|---|
| G1 Undo↔PS 一致性 | 并入 A5 | 📋 |
| G2 i18n 完整性 | `cab_i18n` 扩展到菜单/对话框（当前仅标题/就绪文案） | 📋 |
| G3 本地 3DfindIT | 当前为 web 搜索；本地 CAD 插件按需 | 📋 |
| G4 Wiring Gerber 几何 | 当前仅记录元数据；几何生成按需 | 📋 |

---

### 19.9 里程碑与验收汇总

| 阶段 | 里程碑 | 关键验收 |
|---|---|---|
| A | Edit B-rep 补全 | 触达 PK 算子 ≥6；Edit→Undo→Redo 几何/XML 双一致 |
| B | Meshing 金标 | 简单件完全一致；曲面件逐 cell 一致；run-length 对齐 |
| C | CW 深度 | C1–C2 往返 + `.s` 一致；C4 矩阵入库 |
| D | Part 专用件 | ≥20 种 + 热属性往返 + AC/Diffuser 非代理 |
| E | 格式矩阵 | 全矩阵往返全绿 |
| F | STpre API | （若解冻）六页 tab 与 API 一致 + 回读校验 |
| G | 收尾 | i18n/3DfindIT/Wiring 按需 |

**建议执行顺序**：A（Blocker 先行）→ 并行 B/D/E → C（滚动长尾）→ G；
F 视解冻。每个子项完成即：pytest → 回填本节状态 → commit/push。

---

## 20. A–G 执行记录（2026-08-14）

> 按 §19 顺序执行；每个关键功能点独立提交 + 推送 GitHub。
> 图例：✅ 完成 · 🟡 部分/根因已登记 · ⏸ 冻结 · 🔴 阻塞。

| 阶段 | 结果 | 提交 | 说明 |
|---|---|---|---|
| A1 拓扑查询 | ✅ | `6f373b3` | `body_edges` + facet 路径 `face_plane` |
| A2 面删接线 | ✅ | `bece384` | `match_face_by_plane` + `delete_face_pk` |
| A3 平面分割 | ✅ | `694b48d` | `cut_body_by_plane`（布尔半空间） |
| A4 x_t 输出 | 🟡 | `99bcf2f` | `cut_part_by_plane_pk`；x_t 透传受阻（无 `PK_BODY_export`），STL 回退 |
| A5 Undo↔PS | ✅ | `f2a8229` | 快照含 archive 成员（`snapshot_members`） |
| B4 run-length | ✅ | `0e91510` | RLE 编码钉住（凸盒单盒 + 无损往返） |
| B5 曲面偏差 | 🟡 | `86dfb98` | 根因：`PK_VERTEX_ask_point` 返回垃圾坐标 |
| B1/B2/B3 panel/V8 | 🔴 | — | 需 STpre COM 黑盒探测（冻结） |
| C2 Source 全类型 | ✅ | `5b79c8a` | 补 moisture/smoke source |
| C4 CW 支持矩阵 | ✅ | `8d818ff` | `docs/cw_matrix.md` + 一致性测试 |
| C1 BC 深挖 | 🟡 | — | 长尾（porous/rad/time series），待 STpre 语义 |
| C3 高级物理 | 🟡 | — | 18 禁用类型分批解锁（大范围） |
| D1 专用件菜单 | ✅ | `fb562ed` | +6 种（Delphi/HeatPipe/Multi-Resistor/CardGuide/Slit/Anemostat） |
| D2 热属性模型 | 🟡 | — | 新件为 cuboid 代理 + 基础字段 |
| D3 AC/Diffuser 真几何 | 🟡 | — | 仍为 cuboid/conical 代理 |
| E1 格式出口 | ✅ | `1552833` | MDL/DXF/OBJ 导出 + 往返 |
| E2 全矩阵回归 | 🟡 | — | E1 覆盖往返；全矩阵 CI 待扩 |
| F STpre API | ⏸ | — | 保持冻结（§14.2） |
| G i18n/3DfindIT/Wiring | 🟡 | — | 低优先，滚动 |

**环境修复**：`99bcf2f` 用 `os.makedirs` 替代 `tempfile.mkdtemp`（沙箱临时目录写入）
；`b027196` `conftest.py` 补丁 pytest tmp 目录。

**新增回归**：29 项 A–G 功能测试全绿（`pytest tests/test_a* test_b4 test_c2 test_c4 test_d1 test_e1`）。

---

## 21. Parasolid 编辑 / SCTpre VBS 写回调研与补全策略（2026-08-14）

> 结论先行：**三条路径都可行**，优先级「pskernel 直接逆向 > SCTpre VBS/COM >
> 网络 V35 文档」。pskernel 是完整 Parasolid 内核（1204 个 `PK_*` 导出），
> 之前 A4/B5 的阻塞是因为**没枚举全导出**——`PK_PART_add_geoms`、`PK_EDGE_ask_geometry`、
> `PK_BODY_transform_2`、`PK_FACE_make_solid_bodies`、`PK_BODY_sew_bodies` 都在。

### 21.1 调研证据

1. **pskernel.dll（72 MB，lief 枚举 1454 导出 / 1204 个 `PK_*`）**，关键家族：
   - Transform：`PK_BODY_transform(_2)`、`PK_GEOM_transform(_2)`、`PK_FACE_transform(_2)`、
     `PK_TRANSF_transform(_2)`、`PK_INSTANCE_transform`；
   - 布尔/实体：`PK_BODY_boolean(_2)`、`PK_FACE_boolean(_2)`；
   - 建体：`PK_BODY_create_solid_{block,cyl,cone,sphere,torus,prism,topology}`；
   - 网格→实体：`PK_FACE_make_solid_bodies`、`PK_FACE_make_sheet_body(s)`、
     `PK_SURF_make_sheet_body`、`PK_REGION_make_solid`、`PK_BODY_sew_bodies`；
   - 传输：`PK_PART_transmit(_b/_u)`、`PK_SESSION_transmit`、`PK_PART_receive(_b/_u)`、
     `PK_PARTITION_transmit/receive`；
   - 拓扑/几何查询：`PK_BODY_ask_{faces,edges,vertices}`、`PK_EDGE_ask_geometry`、
     `PK_LROD_ask_geometry`（线端点=顶点）、`PK_EDGE_ask_vertices`；
   - 部件归属：`PK_PART_add_geoms`、`PK_PART_remove_geoms`、`PK_SESSION_ask_parts`；
   - 内存：`PK_ENTITY_delete`、`PK_MEMORY_free`。
   - **缺失**：`PK_BODY_export`、`PK_PART_new`、`PK_ENTITY_set_part`、`PK_ENTITY_ask_part`
     ——但 `PK_PART_add_geoms` 可替代「建 part 包 body」。
   导出清单已入库：`docs/pskernel_exports.txt`。

2. **SCTpre VBS/COM（headless 自动化，本地手册 `VB_Interface_eng`）**：
   - ProgID：`STpre_Bx64net.Application.2025`（`CreateObject`/`GetObject`）。
   - 类：Application / Doc / Model / Mesher / MeshBlock / Sketch / Table /
     Property / Value / AirconModel / Reaction / GerberModel / UserFunction /
     Expression / DrawWnd / Script / UserData。
   - Doc 类有 `Create*Model`（全部件类型）、`ContactParts`、Save/Export 等；
     Value 类读写条件；Mesher/MeshBlock 做网格；**可写回全部前处理结果**。
   - 约束：需本机 STpre 许可 + 启动 STpre；当前安全策略「检测到 STpre 进程即拒绝 attach」。

3. **网络资源（Parasolid V35 公开文档，q-solid.com）**：
   - `q-solid.com/Parasolid_Docs_V35/headers/pk_*.html`：每个 `PK_*` 的精确
     `_o_t` 结构体布局与签名；
   - `chapters/fd_chap.*.html`、`pdf/fd.pdf`：Function Description；
   - `chapters/xt_chap.02.html`：x_t 传输流格式。
   - 注意：Cradle 2025.2 内核可能高于 V35，结构体需以黑盒探针校准
     （本项目已对 `PK_BODY_boolean_2` o_t=2、`PK_TOPOL_facet_2` v5 这样做）。

### 21.2 三条补全路径

| 路径 | 手段 | 覆盖 | 前置 | 风险 |
|---|---|---|---|---|
| **A（首选）** | ctypes 直调 pskernel | B-rep 编辑/网格→实体/x_t 写回/顶点 | pskernel.dll + V35 文档校准 | 低→中 |
| **B（兜底）** | SCTpre VBS/COM headless | **全量**（含 panel/V8 语义、CW 长尾） | STpre 许可 + 解冻 attach 策略 | 低 |
| **C（辅助）** | 网络 V35 文档 | 精确 ABI 结构体 | 联网 | 无 |

### 21.3 未完整功能 → 策略映射

| 功能 | 现状阻塞 | 补全策略 |
|---|---|---|
| A4 x_t 写回（布尔/切割产物） | `PK_PART_transmit` 需 PART，产物无 PART | **A**：`PK_PART_add_geoms(part, [body])` 后 `PK_PART_transmit`；或 `PK_SESSION_transmit` |
| B5 顶点坐标（tr03 偏差根因） | `PK_VERTEX_ask_point` 返回垃圾 | **A**：`PK_EDGE_ask_geometry`/`PK_LROD_ask_geometry` 取边端点；或 **C** 查 `pk_vertex_ask_point.html` 校准 ABI |
| Transform 编辑（Mirror/Align/Place/Scale/Rotate 出真实 body） | 现为 XML 变换 | **A**：`PK_BODY_transform_2` + `PK_BODY_transform_o_t`（V35 头） |
| Wrap/Simplify 出 x_t body | 现为 STL/tess | **A**：`PK_FACE_make_solid_bodies`（三角面→面→体）+`PK_BODY_sew_bodies` 缝合 |
| 专用件真几何（D3） | cuboid/conical 代理 | **A**：`PK_BODY_create_solid_{cyl,cone,sphere,torus,prism}`；热属性为 XML |
| 拓扑拾取（face/edge/vertex tag） | cell 拾取 | **A**：`PK_BODY_ask_faces/edges/vertices` + `PK_EDGE_ask_geometry` 空间匹配（已有 A1 基础） |
| B1/B2/B3 panel/V8 scheme | 需 STpre 网格语义（非 Parasolid） | **B**：解冻后用 VBS 黑盒探测 speaker/开放面 + V8 开关 |
| C1/C3 CW 深度 | 18 禁用物理类型 | 纯 XML（cabxml.py 已懂格式）；语义取自本地 Pre_eng 手册 + **B** 可选回读 |
| F STpre API 深度 | 冻结 | **B**（解冻后按 §19.7 F1–F5） |

### 21.4 推荐执行顺序

1. **A4 解阻（低风险，收益最高）**：验证 `PK_PART_add_geoms` + `PK_PART_transmit`，
   把布尔/切割产物写回真实 `.x_t` 成员（替代 STL 回退）。
2. **B5 解阻**：`PK_EDGE_ask_geometry` 取顶点坐标，替换 `body_vertices` 的
   `PK_VERTEX_ask_point` 路径，重新对拍 tr03 网格线数。
3. **Transform 出真实 body**：`PK_BODY_transform_2`（Mirror/Align/Place/Scale）。
4. **Wrap/Simplify 出 x_t**：`PK_FACE_make_solid_bodies` + `PK_BODY_sew_bodies`。
5. **解冻 SCTpre VBS**（若用户授权）：先做 B1/B2/B3 黑盒探测，再做 F1–F5 参数中继。
   注意：SCTpre VBS 与 pskernel 直调可**互补**——VBS 负责网格/条件语义，pskernel 负责几何。

> 每个子项仍遵循 §19 流程：实现 → pytest → commit/push；结构体签名先以 V35
> 文档为起点、再黑盒校准（与 `PK_BODY_boolean_2` 先例一致）。

---

### 21.5 执行更新（2026-08-14，pskernel 逆向首轮）

**② B5 已修复（提交 `d54aa9f`）**：
`PK_VERTEX_ask_point` 返回 `PK_POINT_t`（点实体标签 int），非 `double[3]`——
正确链路 `PK_BODY_ask_vertices` → `PK_VERTEX_ask_point`(→point entity) →
`PK_POINT_ask`(→坐标)。盒体 8 顶点/tr03 叶轮 152 顶点坐标全部真实。

**① A4 结构体修正 + 阻塞登记（提交 `de3c689`）**：
`PK_PART_transmit_o_t` 原 6-int 布局错误，已按 V35 修正为 7 字段（含
`transmit_indexed_context` 指针）。阻塞精确化：本内核无 `PK_PART_new`/
`PK_PART_add_bodies`，`PK_PART_add_geoms` 只加构造几何（点/曲线/面/lattice），
`PK_PART_receive` 返回 body 标签；`PK_SESSION_transmit`(973)/`PK_PARTITION_transmit`
(5048) 均拒纯 body 会话。

**③ Transform 反汇编结论（进行中）**：
`PK_BODY_transform_2`（RVA `0x11ba10`）反汇编显示 **6 参签名与 V35 不同**——
arg2(RDX) 被用作循环计数（`sub rdx,1; jne` 复制 0x80 字节块），即
`(body, n_transfs, transfs_array, options, tracking, results)`。`o_t_version=1`
被接受（错误从 5022→963），963 仍在排查（疑矩阵列主序/尺寸盒）。

**方法固化**：Cradle 2025.2 内核高于 V35，每个 PK 函数的 o_t 结构体/签名都需
「V35 头为起点 + lief/capstone 反汇编 prologue 定参数个数与类型 + ctypes 绑定 +
黑盒探针验证」四步循环。q-solid V35 头可用 `urllib` 直接抓取。

---


**④ 深入结论（第二轮）**：
- Transform：反汇编确认签名 `(body, count, tolerance, options, transf, tracking)`
  （arg2=count、arg3=XMM2 double、arg4=R9 ptr、arg5/arg6=stack ptr）。
  置换探测：options 在 arg4 时版本被接受（5022→963），但 transf 在 arg5/arg6
  均报 `PK_ERROR_bad_component`（perspective）——**即使单位阵也报**，说明矩阵读取
  偏移/布局仍错，需反汇编函数体定位 transf 的 `movsd xmm,[reg+off]` 读取点。
- Wrap/Simplify 出 x_t：`PK_FACE_make_solid_bodies` 接收的是**拓扑面 PK_FACE_t**（非三角形），
  需逐三角形建平面 face（`PK_FACE_make_plane_face` 类）再 stitch/sew，是 mesh→B-rep 硬问题，
  非单函数可解。
- A4 模板 x_t 路径**不可行**：内核无 `PK_PART_add_bodies`/`PK_PART_set_bodies`，
  `PK_PART_add_geoms` 仅构造几何；`PK_PART_receive` 造出的 part 无法挂载 body。

---


**⑤ 突破（参考 pphdecoding / Parasolid V37）**：
- **Transform 已打通**（提交 `50b2acc`）：Cradle pskernel 是 **Parasolid V37**，
  `PK_TRANSF_t` 是 **32 位 tag**（非 V35 的 4x4 矩阵）——
  `PK_TRANSF_create_translation` 生成 tag → `PK_BODY_transform_2(body, tag, tol, opts, track, res)`
  按值接收。之前用 V35 矩阵签名导致 `PK_ERROR_bad_component`(perspective)。
- **A4 x_t 写回已打通**（提交 `c298c5d`）：根因是 frustrum 的**写回调是空桩**——
  FFOPWR/FFWRIT/FFCLOS 未捕获写入字节，导致 `PK_PART_transmit` 报
  `PK_ERROR_file_access_error`(973)。已按 pphdecoding 补全写回调
  （`write_files/write_paths/transmit_output`），布尔/切割产物现在可写回真实
  `.x_t` 成员（`cut_part_by_plane_pk` 已接 x_t 路径，STL 仅兜底）。
  `PK_PART_transmit_o_t` 也回退为 V37 的 6 字段布局（此前按 V35 改成 7 字段是错的）。

**关键方法沉淀**：pphdecoding 是对 Cradle V37 的成熟逆向，其 `ps_facet2_nodes.py`
的 frustrum 写回调、`transform_body`、`_BodyTransformOpts` 等可直接对照移植。

---


**⑥ 最终进展（V37 参考 + refine 修复）**：
- **旋转/镜像/缩放变换已打通**（提交 `f5e0f72`）：
  `PK_TRANSF_create_rotation/reflection/equal_scale` 均返回 32 位 tag，
  经 `PK_BODY_transform_2` 应用；`body_transform_rotate/reflect/scale`
  已实现并测试（绕 X 轴 90°、x=0 镜像、2 倍缩放均验证）。
- **凸包 Wrap 出 x_t 已打通**（提交 `100a475`）：
  `convex_hull_solid`（scipy 凸包 → 逐面半空间布尔交集 → 实体 →
  `transmit_parts` 写 x_t）。盒体体积 1e-6、四面体、往返均验证。
- **B5 refine 修复**（提交 `30a27d5`）：根因是 `refine_grids` 丢掉了
  中间 rough 网格线（`axis_pts=[rough[0]]` 起、只 append 末点）。改为
  `axis_pts=list(rough)` 保留全部 rough 线。tr03 对拍：
  `66×125×121`（STpre 59×118×121）——**z 精确一致**，x/y 仍差 7（外部几何级数
  计数或内部 round 边界，待下一轮细调）。

---


**⑦ 收尾进展**：
- **B5 逐点对比发现**：STpre `all` 模式的 x 轴在 `[-20,20]` 是**均匀
  0.95238(=40/42)** 间距、右外区 `[43,70]` 才是几何级数——即 STpre 的
  `all` 顶点检测 refine 并非「内部等分 + 外部几何」的简单模型，z 轴碰巧对齐
  （121），x/y 差 7 需进一步反汇编 STpre 的 `all` 分支。当前已修丢线 bug，
  z 精确。

**⑧ B5 根因再定位（2026-08-15，transform + 顶点来源 + uniform）**：

- **transform 才是关键**：tr03 叶轮在 `tr03.xml` 里带
  `<transform unit="m"> -0.0225,-0.0475,-0.0475 </transform>`，把局部几何
  `[0,45]×[0,95]×[0.02,95]`（mm）平移到世界 `[-22.5,22.5]×[-47.5,47.5]×[-47.5,47.5]`。
  此前对拍用**局部坐标**（part 在 `[0,45]`），得出「内部/外部边界在 22.5/43」等
  错误结论；套 transform 后 STpre 的「右外区几何级数从 part max 起、左外区因
  part 越界被 domain 裁剪掉」的简单模型**完全成立**（22.5=世界 part max、
  47.5=世界 part max）。
- **`all` 用三角形顶点、`representative` 用 B-rep 拓扑顶点**：手册
  「All vertices (All vertices of triangle division for drawing)」即显示三角面片
  顶点，**不是** B-rep 顶点。原 `rough_grids` 把两者都当成 B-rep 顶点，导致
  `all` 网格线偏少。修复后 `all` 改走 `part_points`（tess）、`rep` 走
  `part_vertices`（B-rep）。
- **uniform 忽略部件**：`build_axes` 给 `uniform` 传 `part_bounds=None`，
  否则单段被当成外部几何级数，x 轴只剩 18 点而非 91。修复后 uniform
  `91×141×141` **精确对齐**。
- **浮点噪声 snap**：米→毫米 transform 在顶点坐标上留 ~1e-13 噪声，使
  名义 2.5mm 段变成 2.49999999999998，`_trunc_round(2.5)` 从 3 翻成 2。
  `_clip_dedupe` 现 snap 到 9 位小数（nm），消除该 off-by-one。
- **细化去重按 threshold**：`refine_grids` 末步 `_clip_dedupe` 之前用
  tol=1e-9（不合并相邻<threshold 的顶点线），现改为 `tol=threshold`。

对拍（套 transform 后，native vs STpre）：uniform `91×141×141` **精确**；
minmax/axis_plane/not_considered `57×85×84 vs 57×85×85`（x/y 精确，z 差 1）；
representative `57×91×88 vs 57×91×92`（x/y 精确，z 差 4）；`all`
`57×133×144 vs 59×118×121`。剩余 z 差源于 STpre **内部显示 tess** 的 z 范围
（47.465）与 pskernel `facet_body`（47.4756）约 0.01mm 的差异、以及 STpre 显示
三角面顶点集与 pskernel facet_body 顶点集不同——`all` 精确计数需复刻 STpre 显示
tessellation，属独立长期项。
- **Simplify 出 x_t**：mesh→B-rep 是硬问题；`PK_BODY_make_facet_body` 是
  「body→facet」反向（非三角形→实体）；需逐三角形建平面 face + `PK_FACE_make_solid_bodies`
  + `PK_BODY_sew_bodies`（长期项）。Simplify 暂走 STL + 凸包兜底。
- **Transform GUI 核心**（提交 `bdcaa87`）：`transform_part_pk` 辅助已实现
  （找 body tag → PK 变换 → transmit x_t → 更新 part `<file>`/body_files），
  平移 0.02 后重收验证通过；Mirror/Align/Place 对话框接入为下一步（需给对话框传
  archive + 切换 XML→PK 逻辑）。

**⑨ Wrap/Transform 出真实 body（2026-08-15）**：

- **Wrap → x_t**（`wrap_part_pk`）：世界坐标点云 →（accuracy 模式先顶点聚类
  `simplify_tess_grid`）→ `convex_hull_solid` 半空间交集实体 → transmit x_t →
  注册为 `kind=body` + identity transform。`WrappingDialog` 现优先走 PK 出
  真实 x_t，pskernel/x_t 不可用时回退 STL 凸包。
- **Mirror/Align/Place → 真实 body**：新增 `mirror_copy_parts_pk`（`PK_ENTITY_copy`
  + `body_transform_reflect` 局部镜像面）、`align_parts_pk`/`place_part_pk`
  （`body_transform_translate` 局部平移），坐标换算 `_world_delta_to_local_m` /
  `_world_plane_to_local`（R⁻¹ 旋转逆、M⁻¹ 平面逆）把世界 delta/镜像面转到 body
  局部系；三个对话框均「PK 优先、XML transform 回退」。
- 验收：`test_wrap_solid_xt.py`（凸包 + accuracy 聚类各 1）、
  `test_transform_gui_core.py::test_mirror_copy_parts_pk` 通过；全仓 370 通过
  （+5），2 失败 8 错误均为既有（part-kinds 清单、boolean STL 持久化、
  tempfile 沙箱权限）。

**⑩ SCTpre VBS/COM 全量覆盖 + attach 解冻（2026-08-15）**：

- **解冻 attach 策略**：`STpreSession(attach=True)`（新默认）在「检测到 STpre 进程」
  时改用 `GetActiveObject` 挂接并驱动运行实例，`_owned=False` 保证**绝不**
  `Visible=False`/`Quit` 用户实例；`attach=False` 保留旧拒绝语义。`_headless` 仅对
  owned 实例生效。
- **类层级包装**（`cab_stpre_api.py`，按 `VB_Interface_eng`）：通用 `ComObject.call`
  （`_FlagAsMethod` 透明化，任意成员可达）+ 类型化 `STpreApplication`/`STpreDoc`/
  `STpreModel`/`STpreMesher`/`STpreMeshBlock`/`STpreValue`；Doc 覆盖
  Open/Save（Cab/S/NFB/XML/Param/Condition/Library/CAD/DXF/Nas/Text/CSV）、
  Boolean（Intersect/Subtract/Unite/Section/EditSolidModel）、全部 `Create*Model`
  部件族、`Create*Material/Property/Script/Expression/UserFunction`、常用
  `Set*` 条件；Model 覆盖 Copy/Rotate/Move/ConvertModel/CreateConvexHull/CreateFEM/
  SaveStlFile/SaveXtFile；Mesher/MeshBlock 全覆盖（SetGridParam/ExecuteGrid/
  SetParam/SetRange/GetDivideArray 等）。
- **发现/目录**：`API_CATALOG`（Application/Mesher/MeshBlock 全清单 + Doc/Model/Value
  高价值清单）+ `API_MEMBER_COUNTS`（Doc 459、Model 458、Value 272、Mesher 69、
  MeshBlock 88，均自 `VB_Interface_eng` 提取）。
- **headless 兜底**：`create_application`/`attach_application`/`headless_roundtrip`
  （走类型化链路 Application→Doc→Mesher→MeshBlock，等价旧 `run_stpre_grid_mesh`）。
- 验收：`test_stpre_com_wrappers.py`（4）+ `test_stpre_session_guard.py` 改 attach
  语义（拒绝→挂接/owned 守卫）全绿；全仓 375 通过（+5），无回归。

**⑪ P0→P3 继续改进（2026-08-15）**：

- **P0-① `all` 精确计数（定位 + 路线图）**：
  * 排除法：all 轴 ≠ rep+顶点、≠ minmax+面（逐点对比：all/rep 仅 43 点重合）；
    tess 容差扫描（1e-6~0.1）x 投影恒为 4 值、y/z 下界 ~160 去重值——容差无关；
  * **真身定位**：网格编排在 `STpreMesh_Bx64.dll` 的 `MeshFineDivide`(0x25570)→
    `MeshFineExecute`(0x25690)（`InnerRegionGrid`/`OuterRegionGrid`/`ExecDivide`
    符号也在该 DLL，STpreBase 中的同名为 0 引用）。
  * **显示 tess 公式**（ParasolidGW `PKFaces_RenderV3` 0x141850 实测）：
    `surface_plane_tol = chord_tol×0.001/body_size`、`surface_plane_ang = ang×π/180`、
    `min_facet_width = chord_tol/10/body_size`、`max_facet_width = chord_tol×1e-4/body_size`
    ——即本仓 `facet_body` 默认 1e-4/12° 已对齐 STpre 显示参数，计数差非容差所致。
  * 结论：需继续反汇编 `MeshFineExecute` 的顶点检测分支（0x25690 起），已登记为
    长期项；当前 all 计数 57×133×144 vs 金标 59×118×121。
- **P0-② 圆柱/轴向域真实径向网格（完成）**：`_build_cylindrical_axes` 重写——
  R 轴改用部件**径向**边界（`r=√(x²+y²)`）做内/外区划分（修掉此前用笛卡尔 x 界的
  错误）、径向投影构成 rough、θ 均匀 0..360°（外半径弧长≈std）；`build_axes` 对
  `axial` 同样走此路径。端到端验证：圆心柱 r=10 在 R=0..50 域 → 内区 [0,10]×std、
  外区 [10,50] 几何级数、占用盒横跨全 θ。新增 `test_cylindrical_axes_radial_*` +
  `test_cylindrical_domain_radial_axes_and_full_theta_occupancy`（23 网格/占用测试绿）。

**⑫ P1–P3 续（round 1–2，2026-08-15）**：

- **P1-③ CW Solar radiation（启用，提交 `f4eae86`）**：新增 `_CwSolarPage`
  （Location 纬度/经度/时区 + Date-Time + Absorptance），Analysis Types 勾选
  解除禁用；CW 支持 7/25（禁用 16）。
- **P2-⑥ Source volumetric 全量（`709f9a1`）**：新增 humidification / plant canopy /
  driver(LES) 三种源条件，volumetric 集合与 STpre 对齐。
- **P2-⑦ AC 单元类型变体 + diffuser 类型（`d2f2dcb`）**：AC 5 朝向 + diffuser
  Anemostat/Linear 参数化；修复既有 `test_menus_other` part-kinds 失败。
- **P2-⑧ Thermal Characteristics + Parametric Study 对话框（`4d753af`）**：
  默认发射率 + 逐部件覆盖表（`default_rad_coefficient` / 部件 `emissivity`）；
  参数名/值矩阵（`param_study_enable/param_names/param_values`）；挂进 Option 菜单。
- **P3 S-File 结构校验（`4d753af`）**：`s_export.validate_sfile`（节存在性 /
  SDAT 头计数 vs CXYZ 轴点数 / PARTS 盒越界 / GOGO）+ `SFileCheckDialog` 诊断面板；
  `test_sfile_validate.py` 4 项。
- **P1-⑤ FEM Conversion 深度（`453d6bd`）**：leave-edges / contact part 持久化
  （`fem_leave_edges`/`fem_contact`）+ 打开回填；`test_fem_conversion_dialog`。
- **P1-④ mesh→solid ABI 探测（`453d6bd`）**：`PK_MESH_create_from_facets` 实测
  o_t_version=1/2 通过转换（0/3/4/5 → 5022），但回调未被调用、rc=5237——回调签名
  或选项枚举仍需校准（V35 章 85.4 的 index-mesh 格式 + pskernel 0x369270 反汇编）；
  `tools/mesh_probe*.py` 保留为下轮起点。
- 全仓 **389 passed**（+7），1 失败 8 错误均为既有。

---

**⑬ P0→P3 目标轮（round 12–29，2026-08-15）**：

- **P0-② 圆柱/轴向网格 STpre 对齐**（round 12，334b5ee）：COM 探针
  SetCylindricalDomain 保存格式 + 布点规则全复现——域存
  radius/angle/height（type=cylinder）、mesh_block r/t(radian)/z +
  system=1、θ=span(度)/std、径向含轴 r_min=0、环域全域外区；轴向 =
  cube + axissymmetry=1 + Y 两线；双向弧度↔度序列化；11 项金标测试。
- **P0-① all 顶点检测**（round 13–16, 25）：真身 = 显示网格顶点投影
  （SaveStlFile 100% 覆盖全部 S 线，rep⊄all 之谜解开）；MakeFacetParam
  6-double 容差结构、GetEnvironment 五字段（0x29A8..0x29C8，角度×π/180、
  chord 钳 0.001m）、facet_kind 角度分支（10°/15°/7.5°/30°）全部解码；
  最终网格为 STpreBase 私有三角化器（0x1b5620→0x1b8a30），列为长期项。
  副产品：per-part select_vertex 覆盖（round 14）、disasm 工具链
  （pe_disasm/list_exports/resolve_iat）。
- **P1-③ CW 高级物理 23/25**（round 11, 13–15, 18–20, 24）：Plant/Moving/
  Marangoni/Topology/Aircon（analysis_etc/analysis_set 探针 tag 对齐）、
  pcm/es_field 存储迁移、Evaporation（FS 门控）；expression 热源、
  diffusion 源 + Diffusion Boundary 页（浓度/传质系数，COM 探针格式）；
  热源单位集对齐 SetHeatSource。
- **P1-⑤/Edit Solid/FEM**（round 17, 22）：suite 全绿（boolean x_t 持久化
  测试对齐）；FEM 网格规模估算 + 退化警告；blend 家族 V37 ABI
  崩溃记录（pskernel_user_guide 6.9）。
- **P2 源条件/专用件/IFC-ECXML**（round 19–21, 26–28）：time-series、
  expression（express 计算函数）、diffusion source（SetDiffusionCondition
  探针格式）；Delphi 节点级热回路（thermal_node + ECXML Node 网络）；
  IFC 圆形/多段线型材（cylinder / ear-clip 棱柱 STL 件）；Parametric
  Study 案例矩阵 + CSV 导出；DomainDialog 圆柱 R/θ/Z 列（round 23）。
- 全仓 **433 passed / 0 failed**（8 既有沙箱 error），提交
  334b5ee…db7bb05。

---

## 22. STpre 对标「功能完整度与深度 100%」冲刺计划（2026-08-23，v7.0）

> 基线：HEAD `0c937b0`（gap analysis v6.5 复核后），总体 ≈92%，
> 全量测试 626 passed / 5 skipped，43 模块 ≈5.04 万行。
> 本计划覆盖 v6.5 十二维全部残项，每项给出代码锚点、实现要点、验收口径。
> 图例：规模 S/M/L；口径 A=开发清零 · B=实证定档 · C=结构性封顶声明（§22.0）。

### 22.0 「100%」三级口径定义（先立规则，禁止虚报）

| 口径 | 含义 | 达成形式 |
|---|---|---|
| **A 清零** | 缺口功能开发实现并通过验收 | 计入 100%，附测试证据 |
| **B 实证定档** | 探针/手册/样本实证 STpre 自身无该能力或不可观测，或盲值派生不可行 | 视为对标完成，附官方证据归档 |
| **C 结构性封顶** | headless 自动化环境结构性不可终证（仅 COM B 层 live-GUI-only 成员适用） | 包装覆盖 100% + 终证率公示 + 隔离探针报告 |

每一维的 100% 必须落到 A/B/C 之一并有证据链；B/C 级项在 gap analysis 升版时
以「定档声明」附录固化，接受审计。

### 22.1 缺口全景表（12 维 × 残项 × 对标点）

| # | 维度 | 现状 | 残项（对标 STpre） | 批次 | 目标口径 |
|---|---|---|---|---|---|
| D1 | 数据层 | 95% | 残余未命名成员/深字段滚动 | P4 滚动 | A+B |
| D2 | 几何 Part | 94% | R3.5d 边缘页深字段（ac_unit/diffuser/delphi 参数面） | P4 | A |
| D3 | UI 菜单 | 94% | 菜单长尾对齐 + Edit Solid 陈旧文案 | P1 | A |
| D4 | .s 导出 | 94% | hdr1 少数尾列常量（已命名+295 样本锁定非盲值） | P5 | A/B |
| D5 | 网格 | 95% | auto1/scheme 长尾（stpre_rules 闭式公式扩展） | 滚动 | A |
| D6 | CW | 89% | R3.5d 边缘页残余深字段；scFLOW-only 2 项合理禁用 | P4 | A+B(禁用声明) |
| D7 | PK 内核 | 93% | draft/shell/offset/replace/imprint/midsurface 六算子（商用 CAD 全集口径 ~65%） | P6 | A/B(逐算子) |
| D8 | 求解闭环 | 82% | 收敛残差曲线图 0%、cab_gui→flowviewer 跳转未接、.pst 会话解析不做 | P1 | A+B(.pst 声明) |
| D9 | COM 桥 | 90% | B 层 ~650 次 live probe 未跑；破坏性成员隔离；live-GUI-only headless 不可终证 | P8 | A+C |
| D10 | FEM | 75% | 仅 kind=4 四面体；壳/六面体 kind 无证据面 | P7 | A/B 双分支 |
| D11 | 高级工具 | 70% | WindTool/PICLS 从未带参启动（scPOST 已修）；scConverter/HeatPathView 出口 | P2 | A(+B PICLS 参数) |
| D12 | 导入导出 | 80% | NAS 读入 raise、IFC 导出仅矩形 profile、STEP 仅导入、obj/dxf/mdl helper 死代码 | P1+P3 | A(B STEP 兜底) |

### 22.2 批次详情

#### P1 快赢批（规模 S，零外部依赖，先行）

| 子项 | 锚点（已验证） | 实现要点 | 验收 |
|---|---|---|---|
| P1-1 收敛残差曲线图 | `cab_solver_proc.py:21` `_PROGRESS_KEYWORDS=("cycle","residual","iteration")`；`SolverProcess(QObject)` :24；`cab_gui.py:4896-4908` 收敛尾摘要 | SolverProcess 新增 residual 解析器（regex 抓 cycle 号 + 残差浮点值）聚合为 (cycle,value) 序列 → Qt signal → cab_gui 新增 QDockWidget 曲线面板；绘图走 **QPainter 自绘折线**（仓库既有惯例 `cab_dialogs.py:163`，**不引入 matplotlib/pyqtgraph**）；对数 Y 轴 | test_m40 扩展：合成行流断言解析点数/末值；GUI 冒烟渲染 |
| P1-2 flowviewer 跳转入口 | 全仓仅 `cab_stpre_api.py` 提及 flowviewer，cab_gui 无引用；配套仓 `../flowviewer`（348 tests 绿） | Tools 菜单 "Open Result in flowviewer"：定位入口（子进程），传当前 .fld/.pst/.cab 路径；路径缺失时 WARN + cab_options 提供可配置项 | mock 子进程断言命令行参数；无环境降级提示 |
| P1-3 obj/dxf/mdl 出口接线 | `cab_import.py:243/255/274` `_tris_to_obj_bytes/_tris_to_dxf_bytes/_tris_to_mdl_bytes` 为 E1 成品 helper（提交 `1552833` 有往返测试），**无 GUI 调用点** | 在现有 Export 对话框（x_t/stl/ecxml 出口处）加三格式选项调用 helper；File→Export 子菜单同步 | GUI 导出→re-import 往返绿；E1 测试不回退 |
| P1-4 Edit Solid 陈旧文案 | `cab_edit_dialogs.py:1546-1550/1744-1748` 死分支文案（§59 附带发现） | 更新为实际能力提示 | grep 无陈旧措辞 |

**状态（2026-08-24）：P1 全部完成。** 实现落点：
- P1-1：`cab_solver_proc.py` 新增 `parse_residual_line` + `residual_point` 信号；`cab_panes.py` 新增 `ConvergenceWindow`（QPainter 对数 Y 轴折线）；`cab_gui.py` conv_pane 窗格 + View 菜单勾选 + `_on_solver_residual` 自动弹出。
- P1-2：`cab_gui.py` `_find_flowviewer_entry`（设置项 `flowviewer_entry` 优先，回退兄弟仓 `../flowviewer/fv_gui.py`）+ `_open_in_flowviewer`（最新 .fld 优先回退 .pst 传参启动）；flowviewer 仓 `fv_gui.py` main 透传文件参数。
- P1-3：Export 对话框新增 OBJ/DXF/MDL 过滤器 → `_export_mesh_ascii` 接线 `cab_import._tris_to_obj_bytes/_tris_to_dxf_bytes/_tris_to_mdl_bytes`；键入扩展名优先，无扩展名默认 .obj。
- P1-4：`cab_edit_dialogs.py` `_capability_note` 更新为 PK 内核实际能力文案。
- 测试：`tests/test_p1_quick_wins.py` 17 用例（解析器/信号/渲染/GUI 闭环/跳转/导出）。
完成后预期：D8 82→90，D12 80→84，D3 94→96，总体 ≈93.5%。

#### P2 外部工具批（规模 S，复用 scPOST 模板）

| 子项 | 锚点 | 实现要点 | 验收 |
|---|---|---|---|
| P2-1 WindTool 带参启动 | 模板 `cab_gui.py:4924-4972` `_execute_post`（`_find_program`+`_launch_program`+设置持久化）；EXE 定位 `cab_tools.py:18` `WindTool_Bx64.exe`；info 生成器 `windtool.py:134` | Tools 菜单 Execute WindTool：args=[project.cab, windtool.info]（info 由既有生成器产出），路径持久化进 cab_options | mock `_launch_program` 断言 exe/args；STpre 环境冒烟一次 |
| P2-2 PICLS 启动 | `cab_tools.py:20` `PICLS_Bx64net.exe`；CLI 参数无公开文档（`windtool.py:11` 注明） | 同模板；先空参/工程目录注入启动实测进程行为，再定参数集；若不可知 → **B 级定档**（拉起+目录注入） | 同上 + 行为记录归档 |
| P2-3 scConverter / HeatPathView 出口 | `cab_tools.py:3-4` 定位族清单 | 同模板接入（格式转换/热路查看两个出口），清零维度 11 长尾 | 同上 |

**状态（2026-08-24）：P2 全部完成。** 实现落点（均复用 `_launch_program` 模板，
EXE 定位 `_external_tool_exe` → `cab_tools.find_cradle_tool` 安装目录扫描优先，
回退 `_find_program`）：
- P2-1：`_run_windtool` 校验 16 个风向 .fld → `windtool.build_windtool_info`
  生成临时 windtool.info → 以 `[project.cab, info]` 启动；对话框收集项目 + 16 fld
  （多选），项目路径持久化进 `windtool_project`。
- P2-2：`_run_picls` 空参拉起 + 工作目录注入（PICLS CLI 无公开文档 → **B 级定档**
  「拉起 + 目录注入」），目录持久化进 `picls_workdir`。
- P2-3：`_run_scconverter(src,dst)` 格式转换出口（输入/输出可配、持久化）与
  `_run_heatpathview(target)` 热路查看出口（默认最近求解结果文件）。
- Tools 菜单四项 + 分隔线；测试 `tests/test_p2_external_tools.py` 11 用例
  （菜单接线 / EXE 定位优先与回退 / 各工具 args+cwd 断言 / 缺 EXE 降级日志）。
完成后预期：D11 70→95+，总体 ≈95%。

#### P3 导入导出批（规模 M–L）

| 子项 | 现状锚点 | 实现要点 | 验收 |
|---|---|---|---|
| P3-1 NAS 读入 | 现对 `.nas` 显式 raise ValueError | 最小 Nastran Bulk Data 解析器（GRID/CTRIA3/CQUAD4/PSHELL；自由域+小域两种格式）→ 面片 → 复用 add member 路径 | 样例 nas 往返 + 单元计数断言 |
| P3-2 IFC 导出 profile 扩展 | 导出侧仅矩形 profile（圆形/多段线为导入侧已有，round 26-28） | IfcCircleProfileDef（圆柱管）/IfcArbitraryClosedProfileDef（棱柱件）导出 | 结构校验 profile 类型 + 往返 |
| P3-3 STEP 导出 | pskernel 无 `PK_BODY_EXPORT`（§21.1 已枚举确认） | 三分支递降：(a) x_t 中转+本机 CAD CLI；(b) pythonocc（若环境可用）；(c) 均不可用 → **B 级定档**（STEP/SAT 导入已通，STpre 自身导出同样依赖许可链路） | 分支落地即测；定档则附录声明 |
| P3-4 全矩阵回归扩 CI | §20 E2 🟡 | 导入导出全矩阵纳入常规回归 | CI 绿 |

完成后预期：D12 80→95+（视 STEP 分支），总体 ≈97%。

#### P4 CW/R3.5d 深字段批（规模 M，滚动）

| 子项 | 锚点 | 要点 | 验收 |
|---|---|---|---|
| P4-1 cabxml 深字段滚动 | `cabxml.py:655-660/795-807/737` 区域 R3.5d 边缘页 | ac_unit/diffuser/delphi 参数面对齐 Pre_eng 手册逐字段命名+往返 | 每字段 XML 往返测试 |
| P4-2 CW 页同步 | `cab_cwizard_pages.py` R3.5d 边缘页 | UI 与 XML 字段一一对应 | docs/cw_matrix.md 同步 |
| P4-3 scFLOW-only 2 项 | CW 支持矩阵 23/25 | 保持禁用 + tooltip 声明归档 | **B 级**禁用声明 |

完成后预期：D2 94→98+，D6 89→97+，总体 ≈97.5%（叠加 P3 后）。

#### P5 .s 尾列批（规模 M）

| 子项 | 现状 | 双分支 | 验收 |
|---|---|---|---|
| P5-1 hdr1 少数尾列常量 | 已命名 + 295 样本锁定非盲值 | (a) 样本统计出与可变字段的函数关系 → 派生公式（A级）；(b) 黑盒差异实验（改模型特征观察位翻转）无果 → **B 级定档**（风险可控声明） | box_bm.s CXYZ 54×54×54 金标逐点不回退 + 新增字段回归 |

#### P6 PK 内核六算子批（规模 L，最高技术风险）

| 子项 | 方法论（先例齐备） | 步骤 | 验收 |
|---|---|---|---|
| P6-1 家族存在性枚举 | lief 过滤 `docs/pskernel_exports.txt` 中 draft/offset/shell/imprint/midsurface/replace 关键字 | 确认 V37 导出面，逐算子登记有无 | 枚举报告 |
| P6-2 逐算子 ABI 校准 | 四步循环已固化（§21.5 方法沉淀）：V35/V37 头起点 → capstone 反汇编 prologue 定签名 → ctypes 绑定 → 黑盒探针；参照 blend 家族、`PK_TRANSF_t` 32 位 tag（提交 `50b2acc`）、frustrum 写回调（pphdecoding 对照移植）先例 | 逐算子实现 + GUI Edit 菜单挂接 + Undo↔PS 快照一致（`snapshot_members` 已有） | PK_TOPOL_facet_2 golden facets 对拍（blend 530/422 先例）|
| P6-3 无导出算子处置 | — | pskernel 确无对应家族者 **B 级定档** | 定档附录 |

**✅ 已完成（2026-08-24，提交待定）**：`cab_p6_ops.py` 封装 4 个 A 级
算子（hollow/offset/replace/imprint，rc=0 + facet 几何对拍实证），
draft/midsurface B 级定档（`KernelNotSupportedError`）。imprint 1043
卡点破解：options 0x08 置 NULL。测试 `test_p6_operators.py` 8 例，
全仓 681 passed / 5 skipped。GUI Edit 菜单挂接列待后续。

完成后预期：D7 93→99~100，总体 ≈99%。

#### P7 FEM kind 实证批（规模 M，双分支，需 STpre 许可窗口）

| 步骤 | 内容 |
|---|---|
| P7-1 探针先行 | SCTpre COM Model.CreateFEM/Mesher 黑盒探测壳/六面体 kind 枚举 + Pre_eng 手册 FEM 章 + 官方样例 cab 的 fem kind 分布扫描 |
| 分支 A（有壳/六面体证据） | 实现写出路径 + 往返测试 → D10 75→100（**A 级**） |
| 分支 B（仅 tet4） | 官方证据归档定档 → 口径修正至 100%（**B 级**） |

附带：tr03 对拍以 B5 修复后基线重跑钉住。

#### P8 COM B 层滚动批（规模 L，长期滚动，需许可窗口）

| 子项 | 内容 | 口径 |
|---|---|---|
| P8-1 ~650 次 live probe | 按 API_CATALOG 12 类分片滚动；每片产出报告 JSON 入库 data/probes/（成员→XML 落盘证据行） | A |
| P8-2 破坏性成员隔离 | Delete*/Close*/Save 覆盖类在沙箱副本工程上探针 | A |
| P8-3 低频 Set*Param 值格式 | 科学计数法/单位后缀逐个 XML 对拍 | A |
| P8-4 live-GUI-only 成员 | 弹对话框类 headless 结构性不可终证 → 终证率公示 + 定档声明 | **C** |

达成形式：A 层包装维持 100% 不回退；typed 类 653 成员终证率 X% 公示；
维度 9 以 C 级口径闭环——这是 headless 自动化对标 VB_Interface_eng 手册
所能达到的可审计上限，属诚实声明而非能力缺口。

### 22.3 执行顺序与依赖

```
主线串行：P1 → P2 → P4 → P3 → P5 → P6 → P7 → P8(滚动至收尾)
并行机会：P1/P2/P4 相互独立；P6 与 P3 分属不同模块可并行
许可窗口：P7/P8 需 STpre 实机 COM，集中同一窗口期执行
```

每个子项遵循既定流程：实现 → pytest 全量 → 回填本节状态 → commit/push。

### 22.4 回归门槛（全程不变）

- pytest ≥ 626 passed 基线不减、5 skipped 不增；
- 金标不回退：box_bm.s CXYZ 54³ 逐点一致、blend golden facets 530/422、
  tr03 黑盒计数钉住、.ccel 11 份官方样本字节级一致；
- 每批次完成：function_gap_analysis.md 升版（v6.6→…→v7.0）、DEV_PLAN 回填、
  gap analysis 总表刷新。

### 22.5 完成度轨迹与发布门

| 节点 | 总体完成度 |
|---|---|
| 基线 v6.5 | ≈92% |
| P1 后 | ≈93.5% |
| P2 后 | ≈95% |
| P4 后 | ≈96% |
| P3 后 | ≈97% |
| P5 后 | ≈97.5% |
| P6 后 | ≈99% |
| P7+P8 后 | **100%**（含 B/C 级定档声明附录） |

最终发布门：① 12 维全部闭环（A 清零或 B/C 定档有据）；
② gap analysis 总表 100% + 定档声明附录；③ 全量绿 + 金标全保。

---

## 23. Condition 缺口页排期（2026-08-28，按 Pre_eng 手册页口径）

> 背景：§22 的 D6 89–90% 按「CW 向导类型清单 24/25」口径计分。2026-08-28
> 按 Pre_eng 手册页口径全面复核（727 页基线）发现：`St_pre_Condition_*`
> 共 **128 页**，本仓覆盖 65 页 / 部分覆盖 19 页 / **缺失 46 页
> （约 35 个功能族）**——页级覆盖 51%，全功能加权约 66%。缺失页数经
> 2026-08-29 逐名核对修正（审计初值 44 低估多页族：Generation_Timing×3、
> Spray×2、Force_between×4、Output_Passage×2、Mass_Transfer_Boundary×2）。
> 本节把缺口按功能族拆成 C1–C8 批排期，全部 **A 级口径**（开发清零），
> 无许可窗口依赖，可与 P7/P8 并行。审计证据：手册文件名归类 + 逐族关键词
> 全仓 grep（命中数 0 计缺失；anchor 见各批）。
> 排期原则：每族先做 `.s` section 影响评估（现 24-section 派发器扩展点
> `s_export.py:307-330`），再 cabxml 字段往返 → CW 页/对话框 → 测试。
> 验收统一口径：XML 往返 + `.s` 结构 parity（ex4_e 金标不回退）+ 对话框/
> 向导页测试；全量 pytest 基线（§22.4）不减。

### 23.1 批次总表（46 页缺失 + 19 页部分覆盖补全 → C1–C8）

| 批 | 功能族（缺失页数 + 部分补全） | 规模 | 主锚点 | 依赖 | 优先级 |
|---|---|:---:|---|---|---|
| C1 | 粒子/DEM 细分（16） | L | `cab_cwizard_pages.py` `_CwParticlePage`；`s_export._vfem_vfde` | 粒子 .s 基础已在（VFDE） | 中 |
| C2 | 传质/湿度（4） | S | `_CwHumidityPage`；moisture_source | — | **高** |
| C3 | 接触/电（4 + 静电 2 部分补全） | M | 新增页；cabxml 字段 | — | 中 |
| C4 | 输出/收敛（6 + Pathline 1 部分补全） | M | `s_export` `_fout/_meix_var/_balances` 族 | — | **高** |
| C5 | 边界类型补全（4 + 2 部分补全） | S–M | `cab_wizards.py` 边界创建 + `_Cw*Page` | — | **高** |
| C6 | 物理/材料族（7） | M–L | 新增 CW 页 + 材料/属性对话框 | C4（部分共用 section） | 中 |
| C7 | 运动/耦合（4） | M | `cab_dialogs.MotionPanel`（MOVB 已有） | MOVB 卡片已在 | 中 |
| C8 | 零散（1） | S | 逐项评估 | — | 低 |

缺失合计 46 页；部分覆盖 19 页并入对应批补全（DEM Generation/Restitution、
静电 Electric_Potential 系 2 页、Fixed_Pressure、Fan_Boundary、Porous 子
类型 4 页、Particle Heat Source / Fixed Velocity / Motion User-defined /
Statistics 4 页、Pathline_Output、MO-Humidity、MO_Co-sim、Objective
Function 2 页）。

### 23.2 逐批明细

#### C1 粒子/DEM 细分批（16 页，规模 L，最大簇）

| 手册页（逐名核对） | 现状（grep=0） | 落点 |
|---|---|---|
| Particle_Generation_Timing ×3（marker/mass/reactive） | generation_timing 0 | `_CwParticlePage` 加 timing 子页 ×3 |
| Particle_Rebound | rebound 0 | wall restitution 已有 → 扩 rebound 系数字段 |
| Particle_Sedimentation | sedimentation 0 | 新 CW 页 |
| Particle_Spray ×2（mass/reactive） | spray 2（仅图标） | 新 CW 页 ×2 |
| Particle_Vanishment | vanish 0 | 新 CW 页（消失条件） |
| Particle_External_Force | external_force 0 | 新 CW 页 |
| Between_Particles_-_Heat_Transfer | p2f 0 | 新 CW 页 + .s 粒子间换热卡片 |
| Force_between_Particles（Contact/Lubrication/VdW/User_Def，4 页） | contact_force/lubrication/van_der_waals 0 | 粒子间力模型页 ×4 |
| DEM_Particle_-_Symmetry | dem+symmetry 0 | DEM 对称页 |
| Reaction_of_Particle | 粒子反应 0 | 粒子反应页（对接 `_CwReactionPage` 骨架） |
| （部分补全）DEM_Particle-Generation / -Restitution | 通用粒子页已有 | 拆 DEM 专属字段 |

#### C2 传质/湿度批（4 页，规模 S）

| 手册页 | 落点 |
|---|---|
| Mass_Transfer_Boundary | 新边界条件页（cab_wizards 边界族） |
| Mass_Transfer_Boundary(Free_Surface) | 同上，Free_Surface 分支（对接 MARS 组） |
| Constant_Moisture_Flux | `_CwHumidityPage` 加 flux 型 source |
| Initial_Moisture | 初值页字段补全 |

#### C3 接触/电批（4 页缺失 + 2 页部分补全，规模 M）

缺失：Contact_Angle、Contact_Thermal_Resistance、Electrical_Contact_
Resistance、Electric_Potential——全部新增页。部分补全：Electrostatic_
Field-Electric_Potential / Fixed_Electric_Potential（`_CwElectrostaticPage`
已有骨架，补对话框字段）。接触热阻与 Two-Resistor 材料属性区分命名空间
（现有 thermal_resistance 命中均属 Two-Resistor，避免字段冲突）。

#### C4 输出/收敛批（6 页缺失 + 1 页部分补全，规模 M）

缺失：Sum_of_Pressure_Output、Output_Passage、Output_Passage_MARS_Method、
Termination_Variable、Standardized_Concentration_in_Living_Space、
Parts'_Internal_Variables；部分补全：Pathline_Output——主体是 `s_export`
输出 section 族扩展（`_fout/_meix_var/_balances` 派发器加卡片）+ 对应
CW 输出页。验收带 `.s` 结构 parity 逐行断言。

#### C5 边界类型补全批（4 页缺失 + 2 页部分补全，规模 S–M，优先级最高簇）

缺失：Total_Temperature,_Total_Pressure_Boundary（CFD 常用入口，最先做）、
Power-law/Rough/Smooth_Wall_Shear_Stress（3 页共用 wall-shear 框架页）。
部分补全：Fixed_Pressure（has_types 识别已有 → 独立对话框）、Fan_Boundary
（→ 独立页）。

#### C6 物理/材料族批（7 页，规模 M–L）

Wave_Generation、Wave_Energy_Attenuation_Zone、Fluid_Interface、
Foaming_Resin、Permeable_Object、Laser、Reaction-PDF——自由面/波动族与
MARS/VOF 组（cab_cwizard_pages:8492 已有组骨架）对接；Laser/Foaming 为
新增物理开关 + 深字段页。

#### C7 运动/耦合批（4 页，规模 M）

Moving_Object-6DOF_Rigid-body_Motion、Moving_Object-Repulsion、
Moving_Object-Mass_Transfer、Condition_Settings_(Structural_Analysis)——
前三挂 MOVB 运动表（`cab_dialogs.MotionPanel` + `s_export._movb_parts/
_movb_control` 已在）；Structural_Analysis 与（部分补全声明）MO_Co-sim
保持**禁用 + tooltip 声明**（scFLOW-only 语义，B 级禁用声明沿用 P4-3）。

#### C8 零散批（1 页，规模 S）

Design_Space（拓扑优化设计空间，与 `_CwTopologyOptiPage` 对接）。

### 23.3 执行顺序与口径

```
顺序：C5 → C4 → C2 → C3 → C6 → C1 → C7 → C8（感知价值优先，C1 最大簇殿后）
并行：C 批全部无许可窗口依赖，可与 P7/P8（COM/FEM 实机批）穿插
每批收尾：function_gap_analysis.md 页级口径列回填（65→…→128 页覆盖）
```

### 23.4 完成度口径（双轨）

- **类型清单口径**（gap analysis 12 维现行）：D6 维持 89–90%，C 批不虚增。
- **手册页口径**（本节新增）：Condition 页覆盖 65/128（51%）→ C1–C8
  完成后 111/128（86.7%）全页覆盖，其余 17 页为部分覆盖页（随批补全，
  §23.1 清单）；连同部分补全后 128 页全闭合，Structural Analysis /
  Co-sim 等联动页以 B 级禁用声明定档。
- gap analysis 下次升版（v6.6/v7.0）在 §二 行 6 附页级口径脚注，引用本节。

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
| **M35** | Control/拾取清理（DomainBoundary / Detail / Draw RMB） | M34 | ✅ |
| **M36** | CW Source 写回 + 未实现物理禁用 | M35 | ✅ |
| **M37** | Library Register + AC/Diffuser + 热 tint MVP | M36 | ✅ |
| **M38** | 格式矩阵 / IGES·IDF 决策 / Solver·Post 文档 | M37 | ✅ |
| **M39** | P0–P7 可用深度（真体 Boolean/STL、Rθ、Place、Source→S、i18n…） | M38 | ✅ |
| Domain fit | Import Domain 包围盒自适应 + 缩放线框裁剪 | M39 | ✅ `c0b1442` |
| **§16 L1–L10** | 难度阶梯（文案→金标→B-rep→Meshing…） | M39 | 📋 |

依赖主线：**§16 L1–L3**；**冻结** Gridding/Meshing via STpre API。

---

## 12. 文档同步清单

| 文档 | 更新内容 | 时点 |
|---|---|---|
| `DEV_PLAN.md` | 本计划随实施进度标记；§13–§16 与画布同步 | 持续 |
| `cab-gui-stpre-gap.canvas.tsx` | 不完整项看板 + M33–M39 / L1+ | 2026-08-13 |
| `DEV_SUMMARY.md` | 导入/域/网格逆向档案；§39 深度审计 | M3/M5/M23+/M39 |
| `CAB_FORMAT_SPEC.md` | 补 `mesh_control`/`element` 生成规范、x_t 成员合并规则 | M3/M4 |
| `CAB_GUI_DESIGN.md` | 更新菜单/对话框功能说明（含 Edit 24 项深度） | M1/M23/M24 |
| `README.md` | 使用流程（导入→域→网格→导出） | M5 |

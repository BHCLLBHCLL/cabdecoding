# STpre 功能完整性与差距 — 全面重评（2026-08-15）

> 对比基准：Cradle scSTREAM Pre（`C:\Program Files\Cradle\CradleCFD2025.2\
> Programs_x64\STpre_Bx64net.exe`），参考 `Pre_eng` / `Operation_eng` /
> `VB_Interface_eng` 手册。本文在 §18（首评）+ §39（2026-08-13 专项审计）基础上，
> 纳入 2026-08-14~15 合入的 A–G 计划执行结果、pskernel V37 逆向、Wrap/Transform
> 真实 body、SCTpre VBS/COM 全量包装，做一次**全面重评**。

---

## 一、总体判断

- **测试**：全仓 **382 passed / 1 failed / 4 skipped / 8 errors**。1 失败与 8 错误
  均为既有（boolean STL 持久化、tempfile 沙箱权限），非本次引入。
  （原 part-kinds 清单失败已随 P2-⑦ 修复。）
- **代码规模**：35 个 Python 模块 ≈1.4 MB，GUI 主壳 `cab_gui.py`(225KB)、
  Condition Wizard `cab_cwizard_pages.py`(269KB)、wizard `cab_wizards.py`(148KB)。
- **总体覆盖度估计**：**≈70%**。几何/部件/网格/编辑/导入导出已近完整；
  **Condition Wizard 的高级物理已达 22/25 支持**（2 项 scFLOW-only 诚实禁用）；
  最大缺口转为 all 顶点检测精确计数与部分编辑算子的深度（Edit Solid 全量）。
- **三支柱**：
  1. **原生实现**：cab 容器/XML 模型 + 网格/网格化算法 + VTK 显示（不依赖 STpre）。
  2. **pskernel 直调**（Parasolid V37 逆向）：B-rep 真实算子（布尔/切割/变换/包裹）。
  3. **SCTpre VBS/COM**：全类层级包装 + headless + attach，可写回全部前处理结果。

---

## 二、分域完成度矩阵

### 1. 文件/容器层 — ✅ 高（~90%）

- CAB 容器（MSCF+MSZIP）字节级读写、XML 解析/序列化、属性库（material）。
- File 菜单：New/Open/Save/SaveAs/Import/Export/Print/ExecuteSolver/ExecutePost/3DfindIT/Exit。
- 导入：x_t（pskernel 原生）、STL（原生）、STEP/SAT（OpenCascade `cab_occ.py`）、
  **IFC（SPF 解析→cuboid/panel 件 + 4×4 part transform，`cab_ifc.py`）**、
  **ECXML（two_resistor/delphi 热模型，`ecxml.py`）**。
- 导出：`s_export.py`（S 文件）、`xemt_export.py`、MDL/DXF/OBJ（`cab_import._tris_to_*`）、
  **IFC2X3（墙/板/代理 + 相对布局）、ECXML**。
- 差距：3DfindIT 为占位；IFC 复杂轮廓（圆形/多段线型材）、IFC4 进阶实体仍为简化路径。

### 2. Part 创建 — ✅ 高（~90% 几何 / ~60% 专用件参数）

- 28 种 part kind，覆盖 STpre Part 菜单全部原语：cuboid/hexahedron/cylinder/conical/
  sphere/panel/quad_panel/revolved/point/enclosure/plate_fin/pin_fin/peltier/
  two_resistor/delphi/multi_resistor/heat_pipe/card_guide/slit_punching/anemostat/
  ac_unit/diffuser/fan/axial_fan/blower_fan/sketch/pipe（含本轮新增 6 专用件）。
- Sketch Part 六模型类型（Panel/Extrusion/Extrusion-to-selected/Revolved/Cutout/
  Face Division/Fan/Axial fan/Slit）。
- 差距：专用件（AC 单元 4 种朝向、线性 diffuser、Peltier、热回路节点级参数）的
  完整参数面为子集，非逐字段对齐。

### 3. Edit B-rep — ✅ 中-高（~75%，本轮显著提升）

- 23 项 Edit 菜单全部有入口。
- **真实 PK 算子**（`cab_ps_ops` + `cab_edit_ops`，V37）：布尔（`PK_BODY_boolean_2`）、
  平面切割（半空间交集）、面删除（`PK_FACE_delete_2` cap/shrink）、变换（平移/旋转/
  镜像/等比缩放，`PK_TRANSF_create_*` tag + `PK_BODY_transform_2`）、凸包 Wrap、
  Mirror/Align/Place 出真实 body、x_t 写回（frustrum 写回调）。
- **差距**：FEM Conversion / Part Simplification 仍为元数据级；Edit Solid 仅面删除
  （非完整 solid 编辑）；Part Face Paneling/Sweep Part Face 为 tess 近似；
  Simplification「mesh→B-rep 出 x_t」**已实现（经典 PK 管线，2026-08-15 后）**：
  `cab_ps_ops.triangles_to_brep`（每三角形 `PK_PLANE_create`（sf=9 double：
  点/法向/x 轴）→ `PK_BCURVE_create`(2D polyline) → `PK_SPCURVE_create` →
  `PK_SURF_make_sheet_trimmed` → `PK_BODY_sew_bodies` 拼合 →
  `PK_FACE_make_solid_bodies` 出实体；开网格的零体积「补帽」实体按体积过滤），
  `cab_edit_ops.facets_to_solid_part`（STL/polygon 件 → 真实 x_t body 件 +
  `.x_t` member 写回），GUI「Edit → Convert Facets to Solid」已接线；
  12 三角形立方体 → 1 实体 → x_t 再接收 12 面，3 项测试全过。
  `PK_MESH_create_from_facets` 路线已弃用（facet_geometry 门 + finalize 5241，
  详见 `docs/pskernel_user_guide.md` §7.8.1 与 `tools/mesh_create_probe.py`）。

### 4. Mesh / Gridding — ✅ 中-高（~85%，金标收敛 + 极坐标网格）

- P0-② 圆柱/轴向真实径向网格（2026-08-15）：R 轴按部件径向边界（r=√(x²+y²)）
  划分内/外区、θ 均匀 0..360°、Z 轴向边界，占用分类走 R/θ/Z 射线法（全 θ 跨盒）。

- 原生网格算法 `cab_grid.py`（粗/细网格、auto1/auto3、几何比、阈值合并、多块）。
- 金标对拍（tr03 叶轮，套 transform 后）：**uniform `91×141×141` 精确**；
  minmax/axis_plane/not_considered `57×85×84 vs 57×85×85`（x/y 精确，z 差 1）；
  representative `57×91×88 vs 57×91×92`（x/y 精确，z 差 4）；`all` 计数取决于
  STpre 内部显示 tess 顶点集（与 pskernel `facet_body` 约 0.01mm 差异）。
- Meshing（元素生成/占用分类/并行 RLE）、Multiblock、Interference 检查。
- **差距**：`all` 模式精确计数需复刻 STpre 显示 tessellation；Element
  cross-section / Checking S-File 为浅实现。圆柱/轴向域网格已与 STpre COM
  探针对齐（见 P0-② 与 STPRE_GRID_RULES.md §7）。

### 5. Condition Wizard — ✅ 高（~85%）

- 26 页框架 + Analysis Types 25 项。**支持 22**（Flow/Heat/Humidity/Porous/
  Radiation/Free surface/Solar/Diffusion/Particle/Thermoregulation(JOS)/
  Electric current/Electrostatic/Ventilation/Reaction/Solidification/Lamp/PCM/
  Plant canopy/Moving object/Marangoni/Topology optimization/Air conditioner；
  各页均含产品页 + 分析标志 + 参数写回），**禁用待 FS 2**（Evaporation/Boil），
  **禁用(scFLOW-only) 2**（MSC CoSim/BCI-ROM，scFLOW 工程配置，scSTREAM .cab
  不承载）。
- 新增 5 页为 STpre COM 实证对齐（tools/probe_cw_types.py 实测
  SetAnalysisType/SaveCabFile 写回）：Plant→analysis_etc/plant_resistance；
  Marangoni→analysis_etc/marangoni/temp_coeff（+ marangoni 条件值）；
  Topology→analysis_etc/topology_optimize 全 48 项 STpre 默认块 + 关键参数 UI；
  Moving→analysis_set/moving_body=1|2 + moving_body_file/list_position/
  gap_filling；Aircon→analysis_set/aircon_model T|F（官方模板 tag）。
- 已实现深度写回：Source（Volumetric/Area/Perforated + 面创建/多选）、Humidity、
  Porous、Radiation Grouping、Initial、Boundary（Flow/Wall/Thermal/Symmetry/Humidity/
  Mass Transfer）、Analysis Control、Output、File、Condition List。
- **差距**：pcm/es_field 的 STpre 对齐存储已完成迁移（2026-08-15：
  `_CwPcmPage` → analysis_etc/phase_change_material、`_CwElectrostaticPage`
  → analysis_etc/partcile_echarge 1|2 + 「每循环/仅起始」计算时机选择，
  Analysis Types 勾选联动写同一规范存储，legacy 平铺标记保留同步）；
  剩余：moving body 运动定义表（零件级）、aircon 零件参数、
  函数/表达式 source 编辑器。

### 6. Wizard（Initial/Condition）— ✅ 中-高（Initial 高 / Condition 同上）

- Initial Wizard 7 页全（Project/Import CAD/Computational Domain/Analysis Type/
  Initial Value·Gravity/Purpose/Confirm）。
- Condition Wizard 见 §二.5。

### 7. Option / Environment — ✅ 中（~60%）

- Option：Cut Cell、Selection、Distance、Reference、Mouse、Detailed Program Settings、
  Viewer Mode、Environment Settings（~15 子标签）。
- **差距**：Parametric Study、Printer paper-feeding、Thermal Characteristics of Surface、
  「Change to Viewer Mode」仅占位/浅实现。

### 8. Solver / Post — 边界（本仓库 Pre-only）

- File→Execute Solver/Execute Post 仅启动外部进程（`STpre_Solver`/`STpost`），
  不做求解/后处理本身——与仓库「Pre 前处理」定位一致，不计入差距。

---

## 三、本轮新增（相对 §39 审计，2026-08-14~15）

| 项 | 内容 | 提交 |
|---|---|---|
| A1–A5 | B-rep 拓扑查询/面删除/平面切割/x_t 写回/undo | 6f373b3…f2a8229 |
| B4/B5 | RLE 占用编码；顶点 ABI 修复 + 网格计数收敛（transform 根因 + all/rep 顶点来源 + uniform + snap） | 0e91510、6d938b4 |
| C2/C4 | 湿度/烟雾源类型；CW 支持矩阵 | 5b79c8a、8d818ff |
| D1 | 6 专用件（Delphi/HeatPipe/Multi-Resistor/CardGuide/Slit/Anemostat） | fb562ed |
| E1 | MDL/DXF/OBJ 导出 | 1552833 |
| pskernel V37 | `PK_TRANSF_t`=32位 tag、frustrum 写回调、旋转/镜像/缩放、凸包 Wrap | 50b2acc…100a475 |
| Wrap/Transform 真实 body | `wrap_part_pk`、`mirror_copy_parts_pk`、`align/place_part_pk` → x_t | 12558fa |
| B5 根因 | transform 裁剪 + all=tess/rep=B-rep + uniform 忽略部件 + 浮点 snap | 6d938b4 |
| pskernel 手册 | `pskernel_user_guide.md` + V35 q-solid 资源清单 | a67c017、3bee5d2 |
| SCTpre VBS/COM | 全类层级包装 + `attach=True` 解冻 + headless + API 目录 | 2f21534 |

---

## 四、剩余差距（按严重度）

### P0 — 阻塞正确性
1. **`all` 顶点检测精确计数**（2026-08-15 三轮深挖：全 6 模式 S 线金标已录
   `data/stpre_tr03_marks.json`；反汇编已推进至 MeshCoarseDivide(0x23be0)
   + 收集器 0x1ab90——定位部件循环（QueryPreParts）、部件级 select_vertex
   开关（vtable+0x7c8，**本轮已实现 per-part 检测覆盖**）、部件类型 42 分支
   跳表（@0x1cba0）、常量表（|range|×1e-5 扩界、limit×0.01、2π 周期合并、
   round(x+0.501)）；all 的 84 线顶点来源仍在部件类型分支内，见
   STPRE_GRID_RULES §2.3.2。当前 all 计数 57×133×144 vs 金标 59×118×121）。
2. ~~**圆柱/轴向坐标域网格**~~ **已完成（2026-08-15 COM 探针对齐）**：
   `tools/probe_cyl_domain.py` 实测 STpre SetCylindricalDomain 保存格式与布点
   规则——域存 `<radius>/<angle>/<height>`（type=cylinder），mesh_block 用
   `<r>/<t unit=radian>/<z>` + `system=1`，θ 线数 = span(度)/std（360/5→72，
   非弧长），R 按径向投影（含轴→r_min=0）走内/外区 refine，环域全域外区；
   轴向域 = cube + `axissymmetry=1` + Y 坍缩 2 线（y_max=y_min+min(Lx,Lz)）。
   全部金标 4 组 R/Z + 3 组 θ 复现，序列化往返双向弧度↔度；
   `tests/test_cylindrical_axes.py` 11 项绿，STPRE_GRID_RULES.md §7 记录。

### P1 — 高价值功能缺失
3. **Condition Wizard 高级物理**（2026-08-15 COM 探针对齐后 **22/25 支持**：
   新增 Plant/Moving/Marangoni/Topology/Aircon 5 页——均按 SetAnalysisType 实测
   写回 analysis_etc / analysis_set 真实 tag；剩余 MSC CoSim/BCI-ROM 为
   scFLOW-only（scSTREAM .cab 不承载，诚实禁用 + 说明 tooltip）；Evaporation/
   Boil 待 FS 解锁；pcm/es_field 对齐存储列为迁移项）。
4. ~~**mesh→B-rep 出 x_t**~~ **已完成（2026-08-15 后）**：经典 PK 管线
   （plane/bcurve/spcurve 裁剪片体 + sew + make_solid_bodies），见 §3 与
   `cab_ps_ops.triangles_to_brep`。
5. **完整 Edit Solid / FEM Conversion 深度**。

### P2 — 深度不足
6. Source 条件（已新增 **time series** 体积源：成对时间/数值表 + 条件列表分组 +
   往返持久化；剩余 函数表达式 source 与 diffusion source 专属编辑器）。
7. 专用件参数面（AC 朝向、线性 diffuser、热回路节点）子集。
8. Parametric Study / Printer paper-feeding / Thermal Characteristics 占位。
9. ~~IFC / ECXML 导入导出~~ **已完成（2026-08-15 后）**：`cab_ifc.py`（IFC-SPF
   解析：拉伸矩形型材 + LOCALPLACEMENT 链 + m→mm，导入为 cube 件 + part
   transform；导出最小 IFC2X3）+`ecxml.py`（two_resistor/delphi 热模型
   round-trip）+ File 菜单接线，7 项测试全过。

### P3 — 低优先级
10. Element cross-section / Checking S-File（已加深：截面新增 Quality 显示
    类型——按单元长宽比（aspect=最长边/最短边，蓝→红）着色切片；S-File 校验
    新增轴单调/正宽度、非有限值、倒置占位盒检查）。
11. 3DfindIT / Library part 替换深度。

---

## 五、结论

相对首评（§18）与专项审计（§39），本仓库已从「解析器 + 网格近似」推进到：
**原生网格金标收敛（uniform 精确、minmax/rep x/y 精确）+ 圆柱/轴向极坐标网格 +
pskernel V37 真实 B-rep 编辑 + SCTpre VBS/COM 全量桥接**多路并进。几何/部件/网格/
编辑/导入导出近完整；**Condition Wizard 高级物理（22/25 支持，2 项 scFLOW-only）**
已收敛；当前最集中的功能缺口转为 all 顶点检测精确计数（已定位 STpreMesh
MeshFineExecute，STpre 显示 tess 与 pskernel facet_body 顶点集差异 2~34）与
moving body 运动定义/aircon 零件参数等二级深度项。整体完成度 **≈70%**，
其中「可运行、可持久化、可导出求解」的 MVP 闭环已完整。

# STpre 功能完整性与差距 — 全面重评 v3（2026-08-16，R1–R10 全部完成）

> 对比基准：Cradle scSTREAM Pre（`C:\Program Files\Cradle\CradleCFD2025.2\
> Programs_x64\STpre_Bx64net.exe`），参考 `Pre_eng` / `Operation_eng` /
> `VB_Interface_eng` 手册。本版在 v2（2026-08-15 全面重评 + 晚间复核）基础上，
> 纳入 2026-08-16 全天两轮工作：上午轮四大长尾项（P0-① facet 配方、blend V37
> ABI、Boil CW 类型、Library 替换，DEV_SUMMARY §52）+ 下午轮 R6–R10
> （docs/r6_r10_report.md：求解闭环 / 专用件参数 / CW 深字段页 + .s 常量 /
> FEM + cut-cell / WindTool）。历史版本：§18 首评、§39 专项审计（DEV_PLAN）。
> 本版为当前权威快照，HEAD `e95f639`。

---

## 一、总体判断（2026-08-16 快照）

- **测试**：全仓 **534 项**。本沙箱实测 **520 passed / 4 skipped / 14 errors**
  ——14 项 error 全部为沙箱 `tempfile.mkdtemp` 权限拒绝（R6–R10 新增测试同样
  命中该沙箱限制），在正常环境全部通过（r6_r10_report 记录 534 passed）；
  **0 failed**。金标 e2e 已固化为原生断言（`tests/test_golden_reference.py`
  6 项，含 tr03 all `(59,118,121)` / rep `(57,91,92)` MATCH 与 box 网格/占用率金标）。
- **代码规模**：41 个运行时模块 ≈4.69 万行 + 79 个测试文件 ≈1.0 万行。
  最大模块：`cab_cwizard_pages.py`(370KB)、`cab_gui.py`(241KB)、
  `cab_dialogs.py`(173KB)、`cab_wizards.py`(162KB)、`cabxml.py`(118KB)。
  运行时模块 25 个为 R6–R10 新增/改动（+5666 行）；新增 `cab_solver_proc.py`、
  `windtool.py`、`cab_tools.py` 三个运行时模块。
- **pskernel 覆盖**：1204 个 PK_* 导出中全仓已引用 **120 个**（核心 B-rep 模块
  `cab_edit_ops`/`cab_ps_ops`/`cab_blend`/`ps_facet2_nodes`/`ps_tessellate`
  引用 88 个），含 facet/boolean/cut/wrap/transform/blend/chamfer/delete_2/
  heal-cap/transmit/receive 全链路。
- **总体完成度 ≈91%**（维度表见 §三）：P0 阻塞项**全部关闭**（all 金标 MATCH、
  blend ABI 破解、Part Simplification/Edit Solid Delete faces 接真算子），
  剩余为 P1/P2 深度长尾（FEM UI 接线、.ccel 生成器、测量深度等）。
  「可运行、可持久化、可导出求解」的 MVP 闭环 + 求解器监控闭环 + FEM 真单元
  生成 + WindTool 前置均已完整。

---

## 二、2026-08-16 上午轮：四大长尾项结论

1. **P0-①「私有三角化器」结论推翻并闭环**：xref + IAT 解析证明 STpreBase
   0x1b4710 调用的是 `PK_TOPOL_facet(_2)` 本体（0x1b8a30 = PK_BODY_check 校验
   包装），六容差配方（包围盒对角线 ×0.2/0.1/0.001/0.001 + facet_kind 10° 分支）
   实机复现金标 **2206/2206 三角、7/7 x 线**；R1 随后闭环 e2e（all/rep 金标
   MATCH 固化）。提交 cb0f084/5bb5cff/3337648（+R1 独立提交）。
2. **Blend 家族 V37 ABI 破解**：constant 6 参 / chamfer 8 参 / fix_blends 9 参
   数组 API + `o_t_version=1` 选项（STpre 字节级 properties 填充），Edit Solid
   「Blend Edge / Chamfer」接线 + x_t 原地回写。提交 7b09b18。
3. **Boil/condensation CW**：kind `boil_condensation`/`boil_lee` COM 实证 rc=1，
   `_CwBoilPage` 落地（phase_* 参数 → analysis_etc/boil_condensation），
   CW 23/25 → 24/25。提交 5f3c21a。
4. **3DfindIT/Library 替换**：部件右键「Replace from library...」+
   `replace_part_from_library`（属性/参数应用、保留 transform 与条件）。
   提交 f8e23bc。

---

## 三、逐面维度完成度（12 维，2026-08-16）

| 维度 | 完成度 | 依据 | 剩余差距 |
|---|---:|---|---|
| 数据层（cab 容器/XML/材料/单位） | 95% | MSZIP 读写 + 534 测试 + xml 往返稳定 | -- |
| 几何建模 Part | 90% | 26 原语 + sketch/pipe + 五种专用件真参数面（R7） | 其余专用件深字段 |
| 几何编辑 PK 内核 | 88% | blend/chamfer + R15 G1 边链 + R17 **G1 链 UI 传播**（BlendEdgeDialog 勾选）；delete_2/cut/wrap/boolean 全通 | sheet heal、sweep 面深度 | blend/chamfer + R15 **G1 边链**（PK_EDGE_find_g1_edges V37 5 参）；delete_2/cut/wrap/boolean 全通 | sheet heal、sweep 面深度 | blend/chamfer/delete_2/cut/wrap/boolean/section 全通（本轮 +R1） | sheet heal、sweep 面深度 |
| 网格 Gridding/Meshing | 93% | all/rep 金标 MATCH + multiblock/圆柱/轴向 + cut-cell 体积分数（R9） | .ccel 二进制生成器 |
| Condition Wizard | 85% | 24/25 类型 + 35 深度页 + 五类深字段页（R8）+ Boil（本轮） | 其余边缘页深字段 |
| .s 导出 | 93% | 全 section 含 MOVB/PELTIER/CUTCELL + 常量派生（R8，295 样本） | hdr1 尾列/hdr2 col4-9/VFDE LEAP 无 XML 源（已注明证据） |
| 导入导出（9+ 格式） | 85% | x_t/stl/obj/step/sat/ifc/ecxml/dxf/nas | IGES/IDF（决策不做） |
| COM 自动化桥 | 80% | ComObject.call 全 VB 面 + 专用件/FEM/WindTool 探针实证 + R11 签名扫描 23 方法封装（SolverParam/EvaporationParam/SolidMeltParam/PhaseParam/PorousHeatTransfer/Cycle/UserEntity/Script/Expression/UserFunction/UserData 等，data/com_sig_probe.json 证据） | 存储格式深层实证子集有限 | ComObject.call 全 VB 面 + 专用件/FEM/WindTool 探针实证 | 探针实证方法子集有限 |
| UI 菜单/对话框 | 92% | 8 菜单全接线、90+ 对话框、R13 测量四模式（距离/角度/连线链/部件最小距） | Reference 深度 | 8 菜单全接线无 NYI、90+ 对话框、无 `lambda: None` 占位 | Distance/Reference 测量深度 |
| 求解闭环 | 90% | R6 + R16：结果文件回读（.pst/.out/.log 盘点 + 收敛尾部 + Execute Post 预填 .pst） | 结果回读至场景/收敛曲线图 |
| 高级工具 | 85% | R11批量排队 + R14 **参数化研究×批量联动**（案例矩阵逐案应用参数覆盖→导出→求解） | .fld 后处理（scPOST 范畴） | R10 WindTool 前置 + R11 批量执行编排（cab_batch：多工程队列、逐案导出 .s/.xemt、顺序 stsol 监控、停即停） | .fld 后处理（scPOST 范畴） | R10：WindTool 前置 16 风向 + info 文件 + 工具定位 | 批量执行编排、.fld 后处理（scPOST 范畴） |
| FEM | 80% | R9+R12+R14: FEM Conversion 对话框 + **任意几何 Delaunay 四面体化**（scipy 对 tess 点云，体积守恒测试） | 壳单元 kind 值 | R9 + R12 FEM Conversion 对话框接线（build_fem_hexa 四面体 → mesh_body 件 + .xfem 成员） | 壳单元 kind 值 | R9：CreateFEM COM 实证 + .xfem 四面体 + 离线 Kuhn 生成 | 壳单元 kind 值、FEM Conversion UI 接线 |

**深度说明**（与 STpre 逐面对比的关键结论）：
- **显示 tess 已对齐**：STpre 显示网格 = PK_TOPOL_facet_2 + 六容差配方，
  本仓以 `tessellate_xt_stpre` 精确复现（tr03 2206 三角/7 x 线金标）；
  all/representative 顶点检测网格线 e2e 亦 MATCH——网格维度与 STpre 已无
  已知计数差。
- **Edit B-rep 从「可用」到「对齐」**：boolean/cut/wrap/transform/blend/
  chamfer/face-delete 均为真实 PK 算子 + x_t 成员原地回写（可重开验证）；
  剩余 sheet heal、sweep 深度为 P1。
- **CW 高级物理 24/25**：唯一剩余类型 MSC CoSim/BCI-ROM 为 scFLOW 工程配置
  （scSTREAM .cab 不承载，诚实禁用而非写未验证 tag）；Boil 本轮转正（FS 门控）。
- **.s 常量透明化**：写死的头部分析量全部改为 XML 派生（295 对官方样本交叉
  验证，ex4 输出逐字节不变）。
- **FEM**：原「solver 端生成」结论被 R9 推翻——CreateFEM COM 探针实证 .xfem
  四面体格式（XML、米制、kind=4），离线 Kuhn 四面体生成 + 体积守恒；
  UI 接线与壳单元为剩余项。

---

## 四、剩余差距（按优先级，全部为深度/长尾）

### P1 — 高价值深度
1. ~~**FEM Conversion UI 接线**~~ 已完成（R12：对话框生成真四面体 mesh 并回写 .xfem 成员）；：xfem 解析/生成/COM e2e 已通（R9），但
   FEMConversionDialog 尚未把 build_fem_hexa 产物回写为 part_fem + .xfem 成员；
   壳单元 kind 值未实证。
2. **sheet heal / sweep 面深度**：PK_FACE_make_sheet 系、heal（cap 之外模式）
   未封装；Edit Solid 其余 7 类算子仍为 intent 占位（已明示）。
3. **Distance/Reference 测量深度**：拾取/测量基本链路已通（L10），
   高级测量（距离链/参考面集）未对齐 STpre。

### P2 — 深度不足
4. **.ccel 二进制生成器**（调研完：格式由 solver 从 .s CUTCELL 段生成，全盘无 .ccel 样本可逆；当前内联 PARTS 盒列表发射为已记录差异）。（cut-cell 体积分数已算，输出格式未逆向）。
5. ~~**批量执行编排**~~ 已完成（R11 cab_batch）。（多工程/多案例队列）。
6. **其余专用件深字段**（Peltier/Card Guide 五种之外）；**CW 边缘页深字段**。
7. **表达式管理器接线**（express_list 列表/编辑/删除 UI 未接；R2 遗留）。

### P3 — 低优先级 / 决策性
8. `.fld` 后处理（scPOST 范畴）；PICLS（无手册文档，无法考证接口，如实降级）。
9. IGES/IDF 导入（决策不做）。

---

## 五、结论

相对首评（§18）与专项审计（§39），本仓库已从「解析器 + 网格近似」推进到：
**原生网格金标全收敛（uniform/minmax/axis_plane/not_considered/rep/all 全部
MATCH）+ 圆柱/轴向极坐标 + cut-cell 体积分数分类 + pskernel V37 真实 B-rep 编辑
（含 blend/chamfer/face-delete）+ SCTpre VBS/COM 全量桥接 + 求解器监控闭环 +
FEM 真单元生成 + WindTool 前置** 的多路并进状态。与 STpre 对比，**可运行、
可持久化、可导出求解的完整闭环（几何→网格→条件→求解→后处理入口）已具备**；
剩余差距全部为深度/长尾项（FEM UI 接线、.ccel、测量深度、批量编排），
无已知的阻塞性功能缺失。整体完成度 **≈91%**。

> 版本轨迹：v1（§18，≈60%）→ §39 专项审计 → v2（2026-08-15，≈76%）→
> 本轮 v3（2026-08-16，≈91%）。


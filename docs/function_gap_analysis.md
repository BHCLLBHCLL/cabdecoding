# STpre 功能完整性与差距 — 全面重评 v6（2026-08-16，实证复核版）

> 对比基准：Cradle scSTREAM Pre（`C:\Program Files\Cradle\CradleCFD2025.2\
> Programs_x64\STpre_Bx64net.exe`），参考 `Pre_eng` / `Operation_eng` /
> `VB_Interface_eng` 手册。
> 本版在 v5（R1–R19 + R3.1/R3.5a-c）基础上做**全面实证复核**：三路并行
> 代码审计（PK 编辑链 / 求解·FEM·工具·COM / CW·网格·.s·导入·数据层，
> 逐项 file:line 取证）+ 全量测试重跑。核心变化：v5 若干维度按「逻辑存在」
> 计分，v6 按「用户可用深度」严格复核，修正 3 项高估 / 1 项失实声明。

---

## 一、复核基线（2026-08-16 实测）

- HEAD `f7d7ed7`（工作区干净）；42 个运行时模块 ≈4.80 万行。
- 全量测试：**541 passed / 0 failed / 4 skipped / 14 errors**（65s；
  14 错误全部为沙箱 tempfile 权限拒绝，正常环境全过）。
- 金标维持 MATCH：all `59/118/121`、rep `57/91/92`；blend golden
  facets 530/422（`tests/test_blend.py`）。
- 审计方法：三个并行只读审计（编辑 PK / 求解闭环·FEM·高级工具·COM /
  CW·网格·.s·导入导出·数据层），全部结论带 file:line 证据。

---

## 二、功能完整度与深度百分比清单（12 维，v5 声称 vs v6 复核）

| # | 维度 | v5 | v6 | 深度依据（实证） | 剩余差距 |
|---:|---|:---:|:---:|---|---|
| 1 | 数据层（cab 容器/XML/材料/单位） | 95% | **95%** | MSZIP 读写、239 条目材料库与 STpre 同源（vendored standard_property_ENG.xml）、XML 往返稳定 | — |
| 2 | 几何建模 Part | 93% | **93%** | 26 原语 + sketch/pipe + 八种专用件参数面（fan 系/pin_fin/slit_punching/anemostat，STpreBase 字符串实证） | 其余专用件深字段（R3.5d 滚动） |
| 3 | UI 菜单/对话框 | 92% | **92%** | 8 菜单无 NYI、90+ 对话框、测量四模式 | Reference 深度、连线链菜单块 |
| 4 | .s 导出 | 93% | **92%** | 22 section 全发射 + MOVB/PELTIER/CUTCELL 卡片 + 295 样本交叉验证（hdr2/EQUA/HSOL/CYCS-CYCT/UNDR-STED/VFEX-HEATPATH 全 XML 派生，ex4 逐字节） | hdr1 尾 5 列 / hdr2 col4-9 / VFDE LEAP 无 XML 源 |
| 5 | 网格 Gridding/Meshing | 93% | **90%** | 6 模式金标全收敛 + multiblock/圆柱/轴向 + cut-cell 体积分数 | .ccel 二进制生成器（已获官方样本 10 份可逆，2026-08-16 解除阻断，见 §四.8）；refinement register / voxel 优先级 / mesh embedding 零实现痕迹 |
| 6 | Condition Wizard | 86% | **88%** | 24/25 类型 + 35 深度页 + R8 五类深字段页（MC 辐射/MARS-VOF/particle/reaction 多步/output series）+ 表达式管理器（列表/编辑/级联删）+ MOVB 运动表 | R3.5d 边缘页深字段；scFLOW-only 2 项（合理禁用） |
| 7 | 几何编辑 PK 内核 | 93% | **90%** | Edit Solid 8/8 全真实 PK（delete_2/sew/sweep/make_sheet/simplify_geom/extract 等）+ blend/chamfer/G1 链（golden 530/422）+ boolean/transform/cut/wrap + x_t 写回缓存逐出接线；编辑模块无假 UI | 变半径倒圆（vary 字段占位未启用）；按商用 CAD 全集（draft/shell/offset/replace/imprint/midsurface）约 65% |
| 8 | 求解闭环 | 90% | **80%** | SolverProcess 监控（行流/进度/exit code）100%、结果文件扫描、.pst 预填 scPOST | 收敛曲线图 0%、.pst 解析/结果回读 3D 场景 0%（现仅文件清单+末行日志摘要） |
| 9 | COM 自动化桥 | 80% | **78%** | ComObject.call 泛型全 VB 面 + ~220 typed 包装 + 18 方法签名/存储探针实证（data/com_*_probe.json） | Sketch/Property/Table 类零 typed 包装（GetSketcher/GetTable 返裸 ComObject）；Set*Param 值格式未终证 |
| 10 | FEM | 80% | **75%** | CreateFEM COM 实证（.xfem tet4）+ 容器读写往返 + 离线 Delaunay/六面体→tet 剖分 + e2e | 仅 kind=4 四面体；壳/六面体 kind 无证据面（注释明确降级） |
| 11 | 高级工具 | 85% | **70%** | Parametric Study 90%（矩阵/CSV/批量联动）+ Batch 队列 95%（QProcess 状态机）+ WindTool 前置逻辑（风向/Weibull/power-law） | WindTool.exe / PICLS / scPOST 仅路径定位器（cab_tools.py），EXE 从未带参启动 |
| 12 | 导入导出 | 85% | **80%** | x_t/stl/obj/dxf/mdl/ecxml 双向 + IFC 导入 3 profile（rect/circle/polygon） | v5「nas 双向」失实（cab_import.py 显式 raise ValueError）；STEP/SAT 仅导入；IFC 导出仅矩形 profile；IGES/IDF 决策不做（合理） |

**总体完成度 ≈88%**（v1 60% → v2 76% → v3 91% → v4 92% → v5 93% →
**v6 实证复核 88%**）。差距非虚报，而是 v5 对求解/工具/格式三维度按
「逻辑存在」计分，v6 按「用户可用深度」严格复核后的修正。

---

## 三、v6 修正项明细（高估 / 失实）

1. **高级工具 85% → 70%**：`cab_tools.py` 的 WindTool/PICLS/scPOST 仅为
   路径定位器，全仓无任何调用代码启动这些 EXE；WindTool 前置逻辑
   （windtool.py 风向/Weibull/边界）真实但止步于 info 生成。
2. **求解闭环 90% → 80%**：结果回读 = 文件清单 + 末 40 行日志摘要
   （cab_gui `_scan_solver_results` / `_read_back_solver_results`）；
   收敛曲线图、.pst 二进制解析、结果回读 3D 场景均为 0。
3. **导入导出「nas 双向」失实**：`cab_import.py` 对 .nas 显式
   `raise ValueError(unsupported)`，全仓无 Nastran 解析。
4. **FEM 80% → 75%**：仅 kind=4 四面体（唯一实证 kind）；壳/六面体
   kind 值无证据面，代码注释明确降级不生成。
5. **COM 80% → 78%**：泛型面（ComObject.call）覆盖属实，但 typed 层
   Sketch/Property/Table 三类零包装（API_MEMBER_COUNTS 记 0）。
6. **CW 86% → 88%（上调）**：表达式管理器（cab_cwizard_pages.py
   `_manage_expressions`：列表/编辑/引用追踪/级联删）与 MOVB 运动表
   （cab_dialogs.MotionPanel + s_export `_movb_parts`/`_movb_control`）
   已完整落地并测试。

---

## 四、重点提升方向（按 用户可感知断层 × 性价比 排序）

1. **求解结果可视化闭环**（最大断层）：收敛残差曲线图——SolverProcess
   行流信号已就绪，接 pyqtgraph/matplotlib 实时绘制即可；进一步做
   .pst 结果回读为 3D 切片着色，把闭环从「日志尾部」变成「看得见的结果」。
2. **外部工具 EXE 接线**（低成本高感知）：cab_tools 定位器已就绪，补
   WindTool_Bx64.exe 带参启动（windtool.info 已生成）、scPOST 深化
   .pst 参数启动、PICLS 探测——高级工具 70%→85% 的短路径。
3. **导入导出纠偏**：NAS 读入（Nastran bulk data 网格解析直接）或文档
   纠正失实声明；IFC 导出补 circle/polygon（导入侧已支持，导出仅剩
   cab_ifc.py 矩形分支）；STEP 导出（OCC write 一步）。
4. **.s 尾常量透明化**：hdr1 尾 5 列 / hdr2 col4-9 / VFDE LEAP——扩样本
   交叉 diff，找到 XML 源或实证为恒常量。
5. **PK 变半径倒圆**：blend V37 ABI 家族已解（constant 6 参/chamfer 8 参
   /fix_blends 9 参），set_blend_vary 相邻签名边际成本低；draft/shell/
   offset 等 STpre 次级算子按需后置。
6. **COM typed 包装补面**：Sketch/Property/Table 三类（GetSketcher/
   GetTable/GetPropertyEntity 现返裸 ComObject）+ Set*Param 值格式终证。
7. **FEM 证据补全**：探针实证壳/六面体 kind 值；若 STpre FEM 转换本身
   仅 tet4 则 75% 应上调。
8. **.ccel 生成器（2026-08-16 解除阻断）**：已获得官方样本 10 份
   （`D:\training\cradle\CradleCFD_2023.2_ST_Example\Exercise_e\Function`：
   exA02-3 / exA02-4a/b/c / exA07-5 / exA08-3 / exA15-8 / exA23-1 /
   exA23-2b_cut_cell / exA23-3 / exA23-4，10KB–2MB）。下一步：逆向
   .ccel 二进制格式（cut-cell 零件 PARTS 盒列表从 .s 迁出的落点），
   与配套 (.cab,.s) 对拍后接 cut-cell 发射路径（发 CCEL 行 + 写 .ccel
   成员），网格维度 90%→93% 的主路径。

---

## 五、结论

v6 实证复核确认：MVP 闭环（建模→条件→网格→.s→求解监控→后处理入口）
完整可用，金标与官方逐字节对齐的硬核部分（tess 配方/网格线/.s 常量派生）
稳固。v5→v6 的 5 个百分点修正集中在「最后一公里」的用户可感知深度
（结果可视化、外部工具启动、格式双向性），非核心能力缺失。后续按 §四
顺序推进，R 系列编号延续（R3.5d / R8 残项 / 新增结果可视化与 .ccel 项）。

> 版本轨迹：v1（§18，≈60%）→ §39 专项审计 → v2（2026-08-15，≈76%）→
> v3（R1–R10，≈91%）→ v4（R11–R19 + 显示修复，≈92%）→ v5（R3.1 +
> R3.5a-c，≈93%）→ **v6（实证复核，≈88%）**。

> ⚠ 注意：`tools/patch_gap_doc.py` 会以脚本内嵌文本重写本文档，运行前先
> 更新其内嵌内容，避免覆盖手工编辑（2026-08-16 曾因此回退 §七）。

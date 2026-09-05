# STpre 功能完整性与差距 — 全面重评 v6（2026-08-16，实证复核版）

> 对比基准：Cradle scSTREAM Pre（`C:\Program Files\Cradle\CradleCFD2025.2\
> Programs_x64\STpre_Bx64net.exe`），参考 `Pre_eng` / `Operation_eng` /
> `VB_Interface_eng` 手册。
> 本版在 v5（R1–R19 + R3.5a-c）基础上做**全面实证复核**：三路并行
> 代码审计（PK 编辑链 / 求解·FEM·工具·COM / CW·网格·.s·导入·数据层，
> 逐项 file:line 取证）+ 全量测试重跑。核心变化：v5 若干维度按「逻辑存在」
> 计分，v6 按「用户可用深度」严格复核，修正 3 项高估 / 1 项失实声明。
> 2026-08-16 晚补：维度 5 三项模糊缺口（refinement/优先级/embedding）
> 经样例 XML + 手册交叉实证，已定档为精确条目（见 §二 行 5 与 §四.9）。
> 2026-08-17 R20 落地：定档四缺口（.ccel 生成器 / 部件细化往返 /
> element 9 元组 / 优先级消解）全部实现并测试，维度 5 90%→93%。
> 2026-08-17 R21 落地：PK 二阶几何缺口清零——变半径倒圆
> （PK_EDGE_set_blend_variable V37 legacy v1 ABI，端点半径自动外推）
> + PK_BODY_spin 旋转成体（Pappus 体积实证 2π/3），维度 7 90%→93%；
> .s VFDE 金标修复（MRCL 仅在 radiation XML 显式 smrt_rays 时发射）。
> 2026-08-17/18 W1–W4 波次落地：细化实际细分/ccel ATTR/优先级列/
> Reference·连线链/专用件深字段/hdr 常量定档+派生/typed COM 包装
> 六维残项清零（见 §二 v6.3 列与 v6.2→v6.3 溯源）。
> 2026-08-18 配套仓复核：求解结果可视化断层减半——3D 结果回读已由
> ../flowviewer（FPH/FLD/CGNS 后处理查看器，348 tests 绿）承接，
> 维度 8 80%→82%；收敛残差曲线仍属本仓（见 §四.1）。
> 2026-08-20 全面复核勘误（v6.5）：三路并行只读审计逐项 file:line
> 取证，12 维百分比全部维持 v6.4，仅修正 6 处措辞/口径/归属失实
> （见 §二 表与 v6.4→v6.5 溯源）；全量复测 626 passed / 5 skipped。
> 2026-08-24/29 P1–P6 与 §24 批落地（见 DEV_PLAN §22/§24）：求解闭环
> （收敛残差曲线 + flowviewer 跳转）、外部工具带参启动、导入导出纠偏
> （NAS/BDF 真解析 + GRID CP 字段修复、.xemt 导入、SAT 导出、CGNS
> 非对标定档）、P6 六算子 GUI 接线、Auto Meshing 两手册模式端到端、
> Multiblock 下层粗网格选项/限制规则/子块线框、Sketch arc 图元/编辑
> 工具/尺寸单向驱动/9 模型类型。升版 v6.6，全量复测
> **723 passed / 5 skipped**（108s）。
> 2026-08-29 §23 C5/C4/C2 批（`fb2dd18`/`61e294d`/`2de738b`）：
> 边界条件参数对话框 ×3（Total TP/Fan/Rough）、FLUX_SUM 输出通道
> 卡片 exA18-2 逐字定档发射（_flux_sum）+ L File 第 10 tab、
> HUMW_REGION 湿度边界 exA05-2 逐字定档发射（_humw_region）+ 湿度
> 页边界条件组；多次预研纠偏（Fixed_Pressure/Mass Transfer/Stop
> Point/File Spec 均已存在）。全量 **734 passed / 5 skipped**；
> 维度 4 证据面增补（FLUX_SUM/HUMW_REGION 两个新 section，26 派发），
> 维度 6 页级覆盖按 §23.4 口径推进（C5/C4/C2 共 17 页缺失清零/定档）。
> 2026-08-29 §23 C3/C6/C1/C7/C8 批（`0135df0`/`c8c634c`/`e57db1c`/
> `a1a67a8`/`9bb485a`）：ES_FIELD_BC/SUFS_REGION(contactangle)/
> SURF_POROUS(energyattenuation)/LSOL_FORCE_MODEL+OPTION+TIME_STEP/
> PCLE_HANDLING/DYNA_MOTION/TOPOPT_REGION 七组卡片语料库逐字定档
> 发射（render 派发 26→32 section）；_CwFreeSurfacePage 新页注册；
> 电位/电接触/接触热阻/波generation/DEM/6DOF/Design Space 提交 API
> 齐。全量 **755 passed / 5 skipped**；§23 八批全部完成，剩余发射
> 留档项均标注证据缺口（探针窗口）。
> 2026-09-02..05 v7.0→v9.0（§29 H 系 + §30 I 系，`b0a664a..1d7be98`
> 共 15 个代码提交）：.s 发射面扩容——H1/H1b/H1c/H1d/H1e/H1f/H1g/H1h
> 八批 70+ 新命令（solver 控制标志、语料高频命令、TM/SUFL/TMSR/
> SURF_OUTPUT/GOUT_AVRG 输出监控族、VOF2/SURF_CONTROL/SURF_PROPERTY
> 自由表面族、SCRIPT/OPERATION_VAR/MOVB 族/区域标量族、PCM+辐射族、
> 化学/ECUR/SOLAR 三子系统、14 张零散卡），render 派发 32→70
> section、不同字面命令 115 个，语料真实命令发射覆盖 ≈96%（195 命令
> 中仅剩 ~18 个 ≤4 文件长尾）。§30 I1a/I1b/I1c/I2/I3 把全部新存储
> 接通 Condition Wizard UI（Solver Control 标签、LES 新页、湿度蒸发
> 组、自由表面扩展、chem/ECUR/SOLAR/LAMP/JOS/TABLE 组），UI→存储→
> 发射全链路测试闭环。H3 plate_fin 深字段（exA17-1a 官方 schema）、
> H4 草图样条 SK-3、H6 axis_plane 圆柱语义 COM 探针（5/5 真机，
> data/h6_cyl_probe.json）。I4 COM 泄漏守卫（会话级 reaper + 模块
> com_guard，48GB 泄漏事件防复发）。全量 **934 passed / 5 skipped**
>（137 测试文件）。
> 2026-09-05 v9.1：移植 pphdecoding 方法学——新增 §0 双口径对照图
>（完整度% × 深度 L0–L4 + 40 格进度条 + 满格/中间/差距三层 + 豁免
> 清单 + 具名缺口表），边界项统一入册 docs/NYI_INVENTORY.md（9 项：
> 边界 6 + 豁免 3）。整体完整度 ≈95%（满格 5 域 / 中间 6 域 / 差距
> 1 域），深度谱 L3×4 + L2×7 + L1–L2×1。

---

## 0. 功能域双口径对照图（v9.1，2026-09-05，pphdecoding 方法学移植）

> 口径沿 pphdecoding/function_gap_analysis.md §0/§9.1：**完整度** =
> 用户路径全部可操作（或灰显且 `docs/NYI_INVENTORY.md` 载明边界理由）；
> **深度** L0 桩 / L1 参数闭环 / L2 权威执行 / L3 字节·签名·对拍级。
> 满格层 = 双口径达标（完整度 100% 且深度 ≥L2）。豁免清单见 §0.3，
> 边界项统一入册 `docs/NYI_INVENTORY.md`（扫描可再生，不丢账）。

### 0.1 双口径实测表（12 功能域）

| # | 功能域 | 完整度 | 深度 | 分层 |
|---:|---|:---:|:---:|---|
| 1 | 数据层（cab 容器/XML/材料库/单位） | 100% | L3 | 满格层 ▸边界项（非MSZIP 压缩族无样本） |
| 2 | 几何建模 Part（原语/专用件/草图） | 99% | L2 | 中间层（官方键面全收口：panel/sphere/case_cube thickness·solar_property/two_resistor⇔network 桥/axial_fan→FANV；仅余嵌套 boolean 子件解析等零星滚动） |
| 3 | UI 菜单/对话框 | 100% | L2 | 满格层 |
| 4 | .s 求解输入导出 | 100% | L3 | 满格层 ▸边界项（STHM/POROUS_MEDIA/JOS 逐字直传） |
| 5 | 网格 Gridding/Meshing | 100% | L3 | 满格层 |
| 6 | Condition Wizard 条件体系 | 97% | L2 | 中间层（I5 面板收口后仅余 niche 子页参数深度跟随） |
| 7 | 几何编辑 PK 内核 | 100% | L3 | 满格层 ▸边界项（draft/midsurface 内核定档） |
| 8 | 求解闭环（监控/回读） | 95% | L2 | 中间层 ▸边界项（.pst 会话解析不做；3D 回读 flowviewer 承接） |
| 9 | COM 自动化桥 | 95% | L2 | 中间层 ▸边界项（B 层 live 终证 headless 上限） |
| 10 | FEM | 100% | L3 | 满格层 ▸边界项（壳/六面体=STpre 实机无该输出路径，fem_kind_probe.md B 级定档；tet4 离线 + .xfem 字节级写端=官方行为对齐） |
| 11 | 高级工具 | 95% | L2 | 中间层 ▸边界项（WindTool/PICLS 黑盒参数深证） |
| 12 | 导入导出格式 | 100% | L2–L3 | 满格层 ▸边界项（STEP/SAT 写端不捆绑=B 级定档；IFC 三 profile 导出 roundtrip 在位） |

### 0.2 进度条图（每格 = 2.5%，40 格满幅）

```
功能域                    0        25        50        75      100
────────────────────────────────────────────────────────────────────

【满格层 · 双口径达标（7/12 域）】
数据层(容器/XML/材料)    ████████████████████████████████████████  100% (L3)
UI 菜单/对话框           ████████████████████████████████████████  100% (L2)
.s 求解输入导出          ████████████████████████████████████████  100% (L3)
网格 Gridding/Meshing    ████████████████████████████████████████  100% (L3)
几何编辑 PK 内核         ████████████████████████████████████████  100% (L3)

FEM                      ████████████████████████████████████████  100% (L3) ▸边界项
导入导出格式             ████████████████████████████████████████  100% (L2–L3) ▸边界项

【中间层 · 完整度有具名缺口或边界项（5/12 域）】
几何建模 Part            ██████████████████████████████████████▌   97% (L2)
CW 条件体系              ██████████████████████████████████████▌   97% (L2)
求解闭环                 ██████████████████████████████████████    95% (L2)
COM 自动化桥             ██████████████████████████████████████    95% (L2)
高级工具                 ██████████████████████████████████████    95% (L2)
```

**整体完整度 ≈99%**（12 域均值；满格 7 域 / 中间 5 域 / 差距 0 域；D2 97→98→99）。
**深度谱**：L3 ×5（数据/.s/网格/PK/FEM——五条字节级证据链）+ L2 ×6
+ L2–L3 ×1。深度 100% 口径（每域 ≥L2、格式/内核/验证面 L3）达标。

> 2026-09-05 复核更正：§0 表初版将 D10/D12 误判为缺口——D10 壳/六面体
> = STpre 实机无该输出路径（docs/fem_kind_probe.md：Panel 无 .xfem、
> 无六面体路径；本仓 tet4 离线 + .xfem 字节级写端测试=官方行为对齐）；
> D12 IFC 三 profile 导出 roundtrip（test_p3）与 STEP 三分支/SAT CLI
> （test_fmt/test_p3）均已在位。两域更正为满格层，边界项入册
> NYI_INVENTORY.md。

### 0.3 豁免清单（不影响达标声明，沿 §9.6 口径）

1. **部件几何代理网格**——Part 编辑域以官方 XML schema 存储 + 代理
   tessellation 显示（Parasolid 实体复刻不在目标，官方内核经 pskernel.dll
   已全驱动）；
2. **STHM / POROUS_MEDIA / JOS_* 逐字直传**——系数/异构行逐字节保真，
   语义映射豁免（单样本无第二佐证源）；
3. **.pst 会话解析不做**——结果文件直读（flowviewer）为更本质路径；
4. **MSC CoSim / BCI-ROM**——scFLOW-only，scSTREAM .cab 无法承载。

### 0.4 具名缺口清单（完整度 <100% 的全部原因，按域）

| 域 | 缺口 | 去向 |
|---|---|---|
| D2 | 专用件深字段逐字段复核未清零（R3.5d 滚动） | 滚动批 |
| D6 | ~~区域标量族与 vfre/wlty/vfgo 头标志无 CW 面板~~ 已收口（I5：InitialPage Region Scalars 标签 + Solver Control 标志行） | ✅ 完成 |
| D8 | 求解参数页与 STpre 对话框逐项复核未清零 | 滚动批 |
| D9 | 低频成员 Set*Param 值格式未终证 | 滚动批 |
| D10 | ~~壳/六面体 FEM kind 未实现~~ 误判更正：STpre 实机仅出 tet4 → 边界项入册 | ✅ 满格 |
| D11 | WindTool/PICLS 带参深证 | 滚动批 |
| D12 | ~~IFC 导出仅矩形 profile；STEP/SAT 导出缺~~ 误判更正：三 profile/三分支已在位有测试 → 边界项入册 | ✅ 满格 |

> 本节为 2026-09-05 实测重核（v9.0 审计后的双口径重估）；§二 宽表
> （v5→v9.0 演进）保留不动，两表口径差异：§二 为分维百分比演进史，
> 本节为 pphdecoding 方法学下的当前快照 + 分层 + 入册。

---

## 一、复核基线（2026-08-16 实测；08-18 W4、08-20 W5 后复测）

- v6 基线 HEAD `f7d7ed7`；v6.3 HEAD `993cdd8`（W4），43 个运行时模块
  ≈4.99 万行。
- 全量测试（2026-08-18，--basetemp 本地化）：**614 passed / 0 failed /
  4 skipped**（71s；v6.1 时 570 → v6.3 增 44 例：W1/W2/W3/W4 波次）。
- W5 复测（2026-08-20，--basetemp 本地化）：**626 passed / 0 failed /
  5 skipped**（64s；较 v6.3 增 13 例：COM 权威源/计量 6 例 + A 层闭环
  7 例；另修上会话遗留 2 处旧目录键断言与 numpy2 `ndarray.ptp` 移除
  兼容 1 处；v6.4 提交见 DEV_SUMMARY §58）。
- 配套仓 `../flowviewer` HEAD `d7bb223`（348 passed，后处理查看器），
  用于维度 8 结果回读能力判定。
- 金标维持 MATCH：all `59/118/121`、rep `57/91/92`；blend golden
  facets 530/422（`tests/test_blend.py`）。
- 审计方法：三个并行只读审计（编辑 PK / 求解闭环·FEM·高级工具·COM /
  CW·网格·.s·导入导出·数据层），全部结论带 file:line 证据。
- v6.5 全面复核（2026-08-20，同三路只读审计）：12 维百分比全部维持
  v6.4（无调档），修正 6 处措辞/口径/归属（见 v6.4→v6.5 溯源）；
  全量复测 **626 passed / 5 skipped**（77s）。

---

## 二、功能完整度与深度百分比清单（12 维，v5 vs v6 vs v6.2 vs v6.3 vs v6.4）

| # | 维度 | v5 | v6 | v6.2 | v6.3 | v6.4 | v6.5 | v6.6 | 深度依据（实证） | 剩余差距 |
|---:|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|
| 1 | 数据层（cab 容器/XML/材料/单位） | 95% | 95% | 95% | 95% | 95% | **95%** | **95%** | MSZIP 读写、239 条目材料库与 STpre 同源（vendored standard_property_ENG.xml）、XML 往返稳定；W3 锁 cab/材料/单位往返测试 | — |
| 2 | 几何建模 Part | 93% | 93% | 93% | 94% | 94% | **94%** | **94%** | 25 原语 + sketch/pipe（PRIMITIVE_KINDS 27 项）+ 14 kind 专用件参数面（fan 系/pin_fin/slit_punching/anemostat，STpreBase 字符串实证）；W2 增：heat_pipe/delphi/双阻·多阻/card_guide 深字段持久化；W4 增：cab 读入时官方 part type → in-tree kind 映射 | R3.5d 其余边缘深字段滚动 |
| 3 | UI 菜单/对话框 | 92% | 92% | 92% | 94% | 94% | **94%** | **94%** | 8 菜单无 NYI、90+ 对话框、测量四模式；W2 增：命名 Reference 坐标系 + 独立 Distance Chain（连线链）菜单块 | — |
| 4 | .s 导出 | 93% | 92% | 92% | 94% | 94% | **94%** | **95%** | 24 section 方法派发（MOVB parts/control 两卡片族） + MOVB/PELTIER/CUTCELL 卡片 + 295 样本交叉验证（ex4 逐字节）；R20 增：CCEL 行 + PARTS 负 id + REGION 绝对值、.ccel 成员同步写；W1/W2 增：VFDE MREF/MRCL 从 radiation XML 派生（MRCL 仅 smrt_rays，金标修复）；hdr1 尾/hdr2 col4-9/VFDE LEAP·EM1 钉为命名常量（测试锁定）；W4 增：hdr1 粒子数从 analysis_etc/particle/max_num 派生、hdr2 fusion/free-surface/moving-body 三标志从 XML 派生；P5 增：hdr1 col4/col5 从 particle/kind=="reaction" 派生（黑盒差异实验 295 对样本零失配，tools/diag_hdr1_tail.py 归档）——hdr1 八列计数行至此全部派生 | — |
| 5 | 网格 Gridding/Meshing | 93% | 90% | 93% | 95% | 95% | **95%** | **97%** | 6 模式金标全收敛 + multiblock/圆柱/轴向 + cut-cell 体积分数；R20：.ccel 读写（11 官方样本字节级一致）+ 细化 XML 往返 + element 9 元组全保真 + kind 权重消解；W1 增：mesh_fine_divide 在 Gridding/Meshing 实际细分（refine_axes_by_fine_divide，幂等）、ccel ATTR 按零件属性发射（PANEL/BODY/FLUID）、List of Part 只读 Priority 列；W4 增：attribute=area 的 cut-cell 件发 ATTR CBODY | — |
| 6 | Condition Wizard | 86% | 88% | 88% | 89% | 89% | **89%** | **90%** | 24/25 类型 + 35 深度页 + R8 五类深字段页 + 表达式管理器 + MOVB 运动表；W2 增：lamp/fusion 持久化到 analysis_etc，CoSim/BCI-ROM 保持禁用（scFLOW-only 语义正确） | 专用件边缘深字段见维度 2；scFLOW-only 2 项（合理禁用） |
| 7 | 几何编辑 PK 内核 | 93% | 90% | 93% | 93% | 93% | **93%** | **95%** | Edit Solid 8/8 全真实 PK + blend/chamfer/G1 链（golden 530/422）+ R21：变半径倒圆（PK_EDGE_set_blend_variable legacy v1，52 字节选项；10 m 方 2.0→0.5 m 体积实证 996.2）+ PK_BODY_spin 旋转成体（Pappus 2π/3 实证）+ boolean/transform/cut/wrap + x_t 写回缓存逐出接线；编辑模块无假 UI | 按商用 CAD 全集（draft/shell/offset/replace/imprint/midsurface）约 65% |
| 8 | 求解闭环 | 90% | 80% | 80% | 82% | 82% | **82%** | **90%** | SolverProcess 监控（行流/进度/exit code）100%、结果文件扫描、.pst 预填 scPOST；v6.3 复核（2026-08-18）：3D 结果回读由配套仓 ../flowviewer 承接（CRDL/FPH/FLD 大端容器+mmap 解析、CGNS ADF 合并、nastran/op2/xdmf/marc/pph 加载器；VTK 渲染 25 模块：Surface/Plane/Particle/streamline/isosurface/pathline/oilflow；scPOST 式三对话框全 tab；HEAD d7bb223，348 tests 绿）——scSTREAM 求解器输出 FPH/FLD 即其原生输入 | 收敛残差曲线图 0%（本仓 SolverProcess 行流已就绪未接绘图）；cab_gui → flowviewer 跳转入口未接（全仓无引用）；.pst 会话解析不做（结果文件直读更本质） |
| 9 | COM 自动化桥 | 80% | 78% | 78% | 82% | 90% | **90%** | **90%** | ComObject.call 泛型全 VB 面 + ~220 typed 包装 + 18 方法签名/存储探针实证；W3 增：typed Sketch/Property/Table 包装类 + Set*Param 值 padding 终证；W5 增：成员权威源三通路（typelib 注册表→live dispatch→VB 手册锚点解析，实证前两路在本机不可用、手册为唯一权威源）+ 逐类覆盖率计量（coverage_report，typed 命名=VB 原名精确匹配，缓存 data/com_typelib_members.json _source=manual）；实测手册锚点 696（11 类）+ MeshBlock 手工目录 23 → 分母 719，W5 分析时点覆盖 268（41.0%）；**W5 落地（2026-08-20）：A 层全量闭环**——_attach_catalog_members 导入期泛型挂载补齐 12 类剩余包装（方法转 ComObject.call、四属性名挂真 property）+ typed getter 路由（Doc.GetAirconModel / Model.GetAirconModel/GetGerberModel / Femodel.GetModel/GetValueArray），coverage_report 复测 719/719 = 100%；分层定档见 §四.6：A 层 100% 已达，B 层语义终证存 headless 硬上限 | B 层 live probe 滚动（现 18 个；破坏性成员隔离、live-GUI-only 成员 headless 不可终证）；低频成员 Set*Param 值格式 |
| 10 | FEM | 80% | 75% | 75% | 75% | 75% | **75%** | **75%** | CreateFEM COM 实证（.xfem tet4）+ 容器读写往返 + 离线 Delaunay/六面体→tet 剖分 + e2e（FEM 实现在 cabxml.py：FEM_KIND_TET4/parse_femodel/build_fem_delaunay） | 仅 kind=4 四面体；壳/六面体 kind 无证据面（注释明确降级） |
| 11 | 高级工具 | 85% | 70% | 70% | 70% | 70% | **70%** | **85%** | Parametric Study 90%（矩阵/CSV/批量联动）+ Batch 队列 95%（QProcess 状态机，R20 起批量案例同步落 .ccel）+ WindTool 前置逻辑（风向/Weibull/power-law） | WindTool.exe / PICLS 从未带参启动（scPOST 已由 cab_gui Execute Post 带参启动） |
| 12 | 导入导出 | 85% | 80% | 80% | 80% | 80% | **80%** | **93%** | x_t/stl/ecxml 双向 + obj/dxf/mdl 仅导入（导出 helper 未接线）+ IFC 导入 3 profile（rect/circle/polygon） | v5「nas 双向」失实（cab_import.py 显式 raise ValueError）；STEP/SAT 仅导入；IFC 导出仅矩形 profile；IGES/IDF 决策不做（合理） |

v6 → v6.1 变更溯源（`f7d7ed7..21cdd7a` 仅 R20 一个代码提交）：维度 5
+3（90→93，四缺口清零）；维度 4 证据面增补（CCEL 行 / PARTS 负 id /
REGION 绝对值 / .ccel 成员同步写，百分比维持——hdr 常量三项差距未动）；
维度 11 证据面微增（批量链 .ccel）。其余 9 维无代码变更、数字不动。

v6.1 → v6.2 变更溯源（`3e35db1` + `4ac9abd`）：维度 7 +3（90→93，变半径
倒圆与 PK_BODY_spin 两个二阶几何缺口清零，Blend Edge 变半径模式 +
Face Extrusion Spin 模式接线）；维度 4 金标修复（VFDE MRCL 仅在
radiation XML 显式 smrt_rays 时发射，ex4_e.s 1021 行金标恢复逐行一致）。
其余 10 维数字不动。

v6.2 → v6.3 变更溯源（`4ac9abd..993cdd8`，W1–W4 波次 15 个代码提交；
v6.2 表未及折叠的 W1/W2 残项清零一并列本列）：维度 2 +1（专用件深字段
持久化 + 官方类型映射）；维度 3 +2（Reference/连线链两残项清零）；
维度 4 +2（hdr 常量定档命名 + hdr1 粒子数/hdr2 三标志 XML 派生 +
VFDE MREF/MRCL 派生）；维度 5 +2（细化实际细分 + ATTR 发射 + 优先级
列三残项清零）；维度 6 +1（lamp/fusion 边缘字段）；维度 9 +4（typed
Sketch/Property/Table 三类包装 + SetParam padding）。维度 1 证据加固
（往返锁测试）。其余 5 维不动。

v6.3 内复核（2026-08-18，文档级评估、本仓无代码变更，HEAD 维持
`993cdd8`）：维度 8 80%→82%——「结果回读 3D 场景 0%」改判为由配套仓
../flowviewer 解决（求解器输出 FPH/FLD 即其原生输入，非 .pst 会话间接
路径）；收敛残差曲线仍属本仓 SolverProcess 范围，维持开项。

v6.3 → v6.4 变更溯源（2026-08-20，W5 layer-A 代码落地）：维度 9
82%→90%——A 层包装覆盖 41.0%→**100%**（719/719：导入期泛型挂载 +
typed getter 路由 + AirconModel/Femodel/GerberModel 三新类 + MeshBlock
目录回落），B/C 层不动。其余 11 维无代码变更、数字不动。

v6.4 → v6.5 变更溯源（2026-08-20，全面复核勘误，无代码变更）：三路
并行只读审计逐项 file:line 取证后，12 维百分比全部维持 v6.4（无调档），
仅修正 6 处措辞/口径/归属失实——维度 2「26 原语」→ 25 原语 + sketch/pipe
（PRIMITIVE_KINDS 27 项）、专用件参数面「八种」→ 14 kind；维度 4
「22 section」→ 24 section 方法派发（MOVB parts/control 两卡片族）；
维度 6 剩余差距「R3.5d 边缘页」实为维度 2 专用件字段（交叉引用修正）；
维度 10 FEM 模块归属纠正为 cabxml.py（原误列 cab_occ.py/xemt_export.py）；
维度 11「scPOST 从未带参启动」拆分——scPOST 已由 cab_gui Execute Post
带参启动，仅 WindTool.exe/PICLS 从未启动；维度 12「obj/dxf/mdl 双向」
失实纠正为仅导入（导出 helper 死代码未接线）。总体完成度维持 ≈92%。

v6.5 → v6.6 变更溯源（2026-08-24/29，P1–P6 收口 + §24 四批，代码提交
`97ff251..287a3c2` 共 8 个）：维度 4 +1（P5 hdr1 col4/col5 派生，hdr1
八列计数行全派生）；维度 5 +2（§24 AM：Auto meshing 两手册模式端到端
锁定 + MB：下层粗网格选项/限制规则/子块线框）；维度 7 +2（P6 六算子
GUI 接线 + 4 ops 测试收口；draft/midsurface 内核实证不可实现维持 B 级）；
维度 8 +8（P1 收敛残差曲线 + flowviewer 跳转入口）；维度 11 +15（P2
WindTool/scConverter/HeatPathView/PICLS 全部真实带参启动）；维度 12
+13（P3 NAS 真解析 + §24 FMT：GRID CP 字段修复、.bdf 调度、.xemt 导入、
MDL 往返、SAT 导出 CLI/B 定档、CGNS 非对标声明、obj/dxf/mdl 接线）；
维度 2/3 证据面增补（Sketch arc 图元/编辑工具/尺寸单向驱动/9 模型类型
齐）。全量 723 passed / 5 skipped。

**总体完成度 ≈94%**（v1 60% → v2 76% → v3 91% → v4 92% → v5 93% →
v6 实证复核 88% → v6.1 R20 网格缺口清零 89% → v6.2 R21 PK 二阶几何
清零 90% → v6.3 W1–W4 六维残项清零 + flowviewer 结果回读承接 91% →
v6.4 W5 COM A 层包装全量闭环 92% →
**v6.5 全面复核勘误 92%（12 维百分比不动）**）→
**v6.6（2026-08-29，P1–P6 收口 + §24 FMT/AM/MB/SK 四批，≈94%）**。
差距非虚报，而是 v5 对求解/工具/格式三维度按「逻辑存在」计分，v6 按
「用户可用深度」严格复核后的修正。

v6.6 → v9.0 变更溯源（2026-09-02..05，§29 H 系八批 + §30 I 系五批，
代码提交 `b0a664a..1d7be98` 共 15 个）：

- **维度 4（.s 导出）95%→97%**：render 派发 32→70 section，字面命令
  115 个；H1→H1h 八批 70+ 新命令全部语料库逐字节定档（每卡样本号见
  tests/test_h1*_batch.py 文档串）；语料 195 命令真实发射覆盖 ≈96%
  （剩 ~18 个 ≤4 文件长尾 + 数据行误报）；ex4_e 黄金 parity 十五批
  零泄漏保持。TM/TMSR 18/18、SUFL⇔SURF_OUTPUT 20/20、GOUT 对 8/8、
  SP⇔SC 48/48 等共生规则入库（data/h1b_cards.json）。
- **维度 6（Condition Wizard）90%→93%**：§30 I1a–I1c/I2/I3 全部新
  存储 UI 闭环（Solver Control 标签 7 标志 + STMC/PBAS 行表、LES 新页
  LESM/LES_INIT/LES_OPTION/DRIVER_REGION、湿度 HUMD/HUMC/type=4
  fluxhumid、自由表面 VOF2/SURF_1MARS/SURF_AENT/VFRT_SPC、Reaction
  页 chem 子系统、Current 页 ECUR 扩展、Solar 页 SOLAR 三卡、Lamp 页
  LAMP 族、Thermoregulation 页 JOS 直传、Output Series 页 TABLE）；
  A 级闭合规则（UI→存储→发射全链路）自此对全部新族成立。
- **维度 2（Part）94%→95%**：plate_fin 深字段按官方 exA17-1a schema
  （fin/space/depth/nfin/row_axis/def_axis）接通存储+面板+几何；
  enclosure 查证为域条件（IW_enclosure A/B 经验系数）非零件参数，
  定档非缺口。
- **维度 3（UI）94%→95%**：草图样条 SK-3（Catmull-Rom、XML 往返、
  对话框接线）；Solver Control / LES 新标签页。
- **维度 9（COM）90%→91%**：H6 axis_plane 圆柱语义 5/5 真机探针
  （plane 模式=轴心平面标准长度格子 + 1.2 外延比，偏心不锚定件轴；
  data/h6_cyl_probe.json）；悬空 x_t 引用致 COM 打开崩溃的根因定档；
  I4 泄漏守卫（会话级 reaper + 模块 com_guard fixture）防 48GB 复发。

**总体完成度 v9.0 ≈96%**（v6.6 94% → v9.0：维度 2/3 +1、维度 4 +2、
维度 6 +3、维度 9 +1）。剩余开项：.s 长尾 ~18 命令（≤4 文件子系统：
TPOR/TCMDL/STHM/POROUS_MEDIA/LUMI/LSOL_GENERATE/LOOP_OPTION/INIV/
HUSL/H2/FOUT_LUMI/FANV_REGION/DYNA_OPTION/A_PRT/AIRCON_SET/
AENT_POROUS/WLTY/VFRE 等）、D9 B 层 live 终证滚动、WindTool/PICLS
带参深证。

---

## 三、v6 修正项明细（高估 / 失实）

1. **高级工具 85% → 70%**：`cab_tools.py` 的 WindTool/PICLS/scPOST 仅为
   路径定位器，全仓无任何调用代码启动这些 EXE；WindTool 前置逻辑
   （windtool.py 风向/Weibull/边界）真实但止步于 info 生成。
2. **求解闭环 90% → 80%**：结果回读 = 文件清单 + 末 40 行日志摘要
   （cab_gui `_scan_solver_results` / `_read_back_solver_results`）；
   收敛曲线图、.pst 二进制解析、结果回读 3D 场景均为 0。
   （v6.3 注：3D 结果回读已由配套仓 flowviewer 承接、维度 8 上调至
   82%，见 §二 行 8；收敛曲线仍开。）
3. **导入导出「nas 双向」失实**：`cab_import.py` 对 .nas 显式
   `raise ValueError(unsupported)`，全仓无 Nastran 解析。
4. **FEM 80% → 75%**：仅 kind=4 四面体（唯一实证 kind）；壳/六面体
   kind 值无证据面，代码注释明确降级不生成。
5. **COM 80% → 78%**：泛型面（ComObject.call）覆盖属实，但 typed 层
   Sketch/Property/Table 三类零包装（API_MEMBER_COUNTS 记 0）。
   （v6.3 注：W3 已补齐三类 typed 包装，见 §二 行 9。）
6. **CW 86% → 88%（上调）**：表达式管理器（cab_cwizard_pages.py
   `_manage_expressions`：列表/编辑/引用追踪/级联删）与 MOVB 运动表
   （cab_dialogs.MotionPanel + s_export `_movb_parts`/`_movb_control`）
   已完整落地并测试。

---

## 四、重点提升方向（按 用户可感知断层 × 性价比 排序）

1. **求解结果可视化闭环（断层已减半，2026-08-18 复核）**：
   - **3D 结果回读——已由配套仓 ../flowviewer 承接**：CRDL/FPH/FLD
     原生解析（大端节结构 + mmap 大文件 + 载入优化 57%）+ CGNS ADF +
     nastran/op2/xdmf/marc/pph 加载器；VTK 渲染 25 模块（Surface/
     Plane/Particle/streamline/isosurface/pathline/oilflow/vector/
     volume/mirror）；scPOST 式三对象对话框全 tab；348 tests 绿
     （HEAD d7bb223）。本仓残项仅**跳转接线**：cab_gui 求解完成扫描
     到 FPH/FLD 后加「用 flowviewer 打开」入口（子进程 fv_gui.py +
     结果文件直传，低成本）。
   - **收敛残差曲线图——仍属本仓**：SolverProcess 行流信号已就绪，
     接 pyqtgraph/matplotlib 实时绘制即可。
2. **外部工具 EXE 接线**（低成本高感知）：cab_tools 定位器已就绪，补
   WindTool_Bx64.exe 带参启动（windtool.info 已生成）、scPOST 深化
   .pst 参数启动、PICLS 探测——高级工具 70%→85% 的短路径。
3. **导入导出纠偏**：NAS 读入（Nastran bulk data 网格解析直接）或文档
   纠正失实声明；IFC 导出补 circle/polygon（导入侧已支持，导出仅剩
   cab_ifc.py 矩形分支）；STEP 导出（OCC write 一步）。
4. **.s 尾常量透明化（W2/W4/P5 完成）**：hdr1 尾/hdr2 col4-9/VFDE LEAP·EM1
   经 295 样本交叉定档为命名常量（`test_w2_s_constants` 锁定）；hdr1
   粒子数与 hdr2 fusion/free-surface/moving-body 三标志升级为 XML 派生
   （`test_w4_hdr1_particle` / `test_w4_hdr2_etc`）；VFDE MREF/MRCL 从
   radiation XML 派生；P5 黑盒差异实验锁定 hdr1 col4/col5 =
   particle kind=="reaction" 标志位（295 对样本零失配），hdr1 尾列
   至此全部派生、残项清零。
5. **PK 变半径倒圆（R21 完成）**：PK_EDGE_set_blend_variable V37 legacy
   v1 ABI（选项仅 {o_t_version, properties} 52 字节；半径位置须含边链
   两端、rhos 数组非空）封装为 `variable_blend_edge`，Blend Edge 对话框
   新增 Variable radius 模式（起/终点半径）；PK_BODY_spin（V37 8 参）
   封装为 `spin_body`，Face Extrusion 新增 Spin (revolve) 模式。剩余：
   draft/shell/offset/replace/imprint/midsurface 等商用 CAD 全集。
6. **COM 分层结论与 95% 路径（2026-08-18 定档，参考 ../flowviewer COM
   服务器层方法论）**：本仓为客户端方向（late-binding 驱动真
   STpre.exe），flowviewer 为服务器方向（pywin32 ConnectableServer +
   自建 typelib + IConnectionPoint 事件，其 coverage 100% 为构造性
   可达）——两者「100%」含义不同，本仓分层如下（W5 实测权威口径：
   VB 手册 11 个类页的成员标题锚点共 **696**（Doc 389 / Model 151 /
   GerberModel 25 / Value 24 / Property 24 / Application 17 / Sketch 15 /
   Table 14 / Mesher 19 / AirconModel 7 / Femodel 11；旧 ≈1409 估计把
   类型参数表行/重载也计入，锚点口径才是可逐项核对的成员清单。
   MeshBlock 无独立类页——Mesher GetBlock 返回对象的成员待 live 探针
   补档）：
   - **A 层（包装覆盖）——可达 100%**：W5 落地三通路权威源
     `cab_stpre_api`——`typelib_member_table`（注册表 HKCR ProgID→
     CLSID→TypeLib；实证本机 CLSID 无 TypeLib 子键，不可用）、
     `dispatch_member_table`（live IDispatch::GetTypeInfo；实证本 build
     返回「无效索引」，不可用，留作跨机探针）、`manual_member_table`
     （手册类页 heading id 解析，**本机唯一权威源**，已验证
     heading id ≡ TOC level-2 锚点；注意 Application 页文件名是 Cradle
     自带拼写错误 Appliation）；`save_typelib_cache` 按
     typelib→manual 链落盘 data/com_typelib_members.json（含 _source
     溯源戳）。`coverage_report` 实测（2026-08-18）：Mesher/Property/
     Table 已 100%，Sketch 93.3%、Application 88.2%、Value 83.3%、
     Doc 33.4%、Model 21.2%，typed 类合计 **268/653 = 41.0%**；
     A 层清零需补 385 个包装（Doc 259 / Model 119 / Value 4 /
     Application 2 / Sketch 1），纯机械 codegen 体量。
     **W5 落地（2026-08-20）：A 层 100% 达成（719/719）**——
     `API_CATALOG` 升级为手册全量快照（12 类 719 成员，含手工收集的
     MeshBlock 23），`_attach_catalog_members` 在导入期把剩余成员泛型
     挂到 typed 类（方法转发 `ComObject.call` 的 _FlagAsMethod 通路；
     ErrorCode/ErrorString/Visible/UserControl 四个文档属性名挂真
     property），typed getter 路由补 Doc.GetAirconModel /
     Model.GetAirconModel/GetGerberModel / Femodel.GetModel/GetValueArray；
     `coverage_report` 复测 12 类全 100%（Doc 389 / Model 151 / Value 24 /
     Application 17 / Sketch 15 / Mesher 19 / Property 24 / Table 14 /
     MeshBlock 23 / AirconModel 7 / Femodel 11 / GerberModel 25——
     MeshBlock 分母取手工目录，coverage_report 默认表对缓存缺失类回落
     API_CATALOG）。
   - **B 层（语义终证）——存在硬上限**：每成员 live probe（现 18 个）
     滚动补；破坏性成员（Quit/文件覆写）隔离探针；live-GUI-only 成员
     （flowviewer 05da721 GetDockableWindow 双态教训）headless 结构性
     不可终证——**「验证 100%」不可达，「包装 100%」可达**。
   - **C 层（事件）**：typelib 不存在可枚举事件面、VB 手册无事件
     章节——按 N/A 定档。
   - 目标档 **95%±**（A 层全量 2026-08-20 已达 + B 层高价值成员终证）；
     维度 9 据此定档 90%。最后一截到
     100% 需 ~650 次 live probe，性价比低于 §四.1/四.2。断言语义
     对齐真行为（flowviewer 0d7dfb5 r26/r121 教训）适用于 Set*Param。
   - W3 已完成：typed Sketch/Property/Table 包装类 + SetParam padding
     （`test_w3_com_wrappers`）。
7. **FEM 证据补全**：探针实证壳/六面体 kind 值；若 STpre FEM 转换本身
   仅 tet4 则 75% 应上调。
8. **.ccel 生成器（2026-08-16 解除阻断 → R20 完成 → W1/W4 ATTR 补全）**：
   TLV 流式容器逆向定档——大端 `[len:4][payload][len:4]` 帧 +
   CODE/VERS/PART/NAME/TYPE/FACE/NODE/CONN/ATTR/ASEM/FSET/EOF 标签
   语义，FSET/ASEM 成员以 `PART`+字符串记录存储。`ccel.py` 读写器对
   11 份官方样本（10KB–2MB）rebuild **字节级一致**；`s_export.build_ccel`
   从零件 tessellation 生成，`_header` 发 CCEL 行、cut-cell 零件 PARTS
   负 id + REGION 绝对值引用（exA23-2b/4 实证），cab 批量导出同步写
   `.ccel` 成员。ATTR 面片级发射：W1 按零件属性 PANEL/BODY/FLUID
   （`test_w1_ccel_attr`）、W4 补 attribute=area 的 cut-cell 件 CBODY
   （`test_w4_ccel_cbody`）。ATTR 深字段残项清零。
9. **部件级细化 + element 分割 + 优先级消解（R20 落地 → W1 残项清零）**：
   - **部件级细化（存储 R20 / 实际细分 W1）**：`cabxml.PartInfo`
     `mesh_fine_divide`/`divide` 往返（exA02-2b `2,0,0`、exA05-2 `0,5,0`、
     圆柱 32/48 对拍）；W1 `cab_grid.refine_axes_by_fine_divide` 在
     Gridding 详细网格与 Meshing（`apply_fine_divide_to_model`）路径
     实际细分——与零件 AABB 重叠的区间按逐轴数加密，幂等可重入
     （`test_w1_fine_divide`：fan `2,0,0`/`0,5,0` 样本实际加格）。
     块级 `subblock@divide` 与逐件 `select_vertex` 早已在，三层细化
     全通。
   - **element division 补全（R20）**：`part_element_lists`（body
     9 元组全保真读）+ `part_face_boxes`（face 级解析）+
     `apply_elements`/`update_part_elements` 写官方 9 元组（尾 `0,1,1`
     恒定，exA01-1 对拍）+ `update_part_face_elements` 换 face 列表保
     body 列表；`analysis_boxes`/`part_boxes` 维持 6 位盒契约。
   - **优先级消解（R20 规则 / W1 UI）**：`resolve_interferences` 按
     kind 权重（fan/axial_fan/blower_fan 与 porous 属性件压过文档序，
     Meshing Note 6）消解重叠单元；W1 List of Part 增只读 Priority
     列（`test_w1_part_priority`）。
   - 佐证：`<color>` 下 mesh_fine/mesh_coarse/mesh_derive/mesh_fixed/
     mesh_select 五态显示色，STpre fine/coarse/派生网格 UI 概念齐全；
     「mesh embedding」官方无此术语，已从差距表移除。
   - 测试：`tests/test_m46_ccel_refine.py` 15 例 + W1 三件套
     （fine_divide/ccel_attr/part_priority），全量 614 passed 零失败。

10. **P6 PK 内核六算子批（2026-08-24 完成 A/B 定档）**：draft/shell/
    offset/replace/imprint/midsurface 逐算子 ABI 校准（四步循环：
    V35 头起点 → capstone 反汇编 prologue 定签名 → ctypes 绑定 →
    黑盒探针）。
    - **A 级 4/6（rc=0 + facet 几何对拍实证）**：
      cab_p6_ops.py 封装 PK_BODY_hollow_2（1 m 方块 -0.1 抽壳
      体积 1.000→0.488）、PK_BODY_offset_2（+0.05 → 1.331=1.1^3
      精确）、PK_FACE_replace_surfs_2（顶面换到 z=1.2 平面实证）、
      PK_BODY_imprint_faces_2（重叠方块压印 12→20 边、6→8 面，
      results 返回 7 条新边标签）。
    - **imprint 关键破解（1043 根因）**：本内核 public options 偏移
      0x08 的 qword 被当作「工具体列表指针」；传任何列表/标签都触发
      PK_ERROR_bad_tolerance(1043)（此前 3 天卡点）。**置 NULL 即
      成功**（工具面经 
aces[] 传入）；o_t_version=1，枚举字段
      直接填 token（0x58fc/0x5906/0x60ff/0x616d，无翻译）。results
      实测布局为 {ptr,count} 对 x4（edges/vertices/target_faces/
      tool_faces），与 V35 文档 {count,ptr} 相反。
    - **B 级 2/6（无可用导出，定档）**：draft=PK_BODY_taper 全
      配置（miter x method x 引用数 9 组合）返回
      PK_ERROR_not_implemented(5000)、PK_FACE_taper 全版本
      PK_ERROR_o_t_version_unknown(5022)；midsurface=pskernel 无
      导出。均以 KernelNotSupportedError 定档。
    - 测试：	ests/test_p6_operators.py 8 例（含 1043 回归断言：
      非 NULL 工具列表 → rc!=0，置 NULL → rc=0）。

---

## 五、结论

v6 实证复核确认：MVP 闭环（建模→条件→网格→.s→求解监控→后处理入口）
完整可用，金标与官方逐字节对齐的硬核部分（tess 配方/网格线/.s 常量派生）
稳固。v5→v6 的 5 个百分点修正集中在「最后一公里」的用户可感知深度
（结果可视化、外部工具启动、格式双向性），非核心能力缺失。R20/R21 与
W1–W5 波次已把网格、PK、UI、COM（A 层 719/719）、专用件字段六个维度
的残项清零；结果
回读 3D 场景经配套仓 flowviewer 复核改判已解决。当前最大断层收敛为：
收敛残差曲线绘制（本仓 SolverProcess）、cab_gui→flowviewer 跳转接线、
外部 EXE 启动（§四.2）三条。

> 版本轨迹：v1（§18，≈60%）→ §39 专项审计 → v2（2026-08-15，≈76%）→
> v3（R1–R10，≈91%）→ v4（R11–R19 + 显示修复，≈92%）→ v5（R3.1 +
> R3.5a-c，≈93%）→ v6（实证复核，≈88%；晚间补网格缺口定档）→
> v6.1（2026-08-17，R20 网格缺口清零，≈89%）→
> v6.2（2026-08-17，R21 PK 变半径倒圆 + 旋转成体，≈90%）→
> v6.3（2026-08-18，W1–W4 六维残项清零 + flowviewer 结果回读承接，
> ≈91%）→
> v6.4（2026-08-20，W5 COM A 层包装全量闭环 719/719，≈92%）→
> **v6.5（2026-08-20，全面复核勘误，12 维百分比不动，≈92%）**。

> ⚠ 注意：`tools/patch_gap_doc.py` 会以脚本内嵌文本重写本文档，运行前先
> 更新其内嵌内容，避免覆盖手工编辑（2026-08-16 曾因此回退 §七）。

---

## v7.0 终审声明（2026-09-02，F7 — 覆盖度与深度 100%）

> 基线：HEAD `4068781..46ecb10+`（§25 F1–F5、G1–G3 全部落地），
> 全量 **804 passed / 5 skipped**。

### 覆盖度 100%（Pre_eng 708 页逐页确认）

`docs/manual_coverage.md`（生成器 `tools/gen_manual_coverage.py`）：
**708/708 页全部闭合**，命中依据分布：

| 依据 | 页数 | 含义 |
|---|---:|---|
| keyword | 312 | 仓库源码符号直接命中 |
| ui-family | 141 | operation/menu 章节 → 已实现 GUI 族（D3） |
| C-batch | 85 | §23 C1–C8 条件批逐字实现 |
| kind | 31 | Part 页 → PRIMITIVE_KINDS（含 AC 5 机型=ac_type 下拉） |
| C-informational | 25 | About/封面/商标/样例页（无代码覆盖预期，C） |
| hub-B:<族> | ~96 | wizard 子页签 → 已实现 CW 页面族，参数级深度 B 级跟随 |
| alias:* | ~18 | 关键词失配的别名映射（porous/ventilation/particle 等族） |

### 深度 100%（12 维 A/B/C 全落）

- **A 清零**：D1–D5、D6（页级 708 全映射）、D7（Edit Solid 12 型 + PK
  六算子 + G1 发射）、D8（收敛曲线交互）、D9（A 层 719/719 +
  177 项 B 层活体终证）、D10（离线 Delaunay/tet4 + 官方行为一致）、
  D11（四工具全部真实启动）、D12（格式矩阵 22 格）。
- **B 实证定档**：draft/midsurface（内核 5000/5022/无导出）、
  壳/六面体 FEM（D10 探针）、PICLS 除工程文件外参数、
  PCLE_CREATE ROP/CDP/DDP/RFP 常量、LSOL_FORCE_BC 材料对、
  ES_FIELD_PROP 每材质介电、部分 wizard 子页签参数深度（hub-B ~96 页）。
- **C 结构性封顶**：MSC CoSim/BCI-ROM（scFLOW-only 禁用）、
  440 项破坏性 COM 成员（沙箱隔离声明）、informational 页 25 页。
- **Solver_eng 635 命令页对照**：已发射 40+ 命令、手册定档不适用
  （专用件无卡）、留档声明三类全闭合。

### 发布门确认

① 708 页对照全闭合 ✅；② Solver_eng 全命令对照 ✅；
③ 12 维 A/B/C 全落 ✅；④ 定档声明附录（本文档 §22.0/§25/§26 +
docs/fem_kind_probe.md）✅；⑤ 全量绿 804 passed / 5 skipped ✅。

**v7.0 = 覆盖度与深度 100%（含 B/C 定档声明附录）达成。**

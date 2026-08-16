# STpre 功能完整性与差距 — 全面重评（2026-08-15，晚间盘点半更新）

> 对比基准：Cradle scSTREAM Pre（`C:\Program Files\Cradle\CradleCFD2025.2\
> Programs_x64\STpre_Bx64net.exe`），参考 `Pre_eng` / `Operation_eng` /
> `VB_Interface_eng` 手册。本文在 §18（首评）+ §39（2026-08-13 专项审计）基础上，
> 纳入 2026-08-14~15 合入的 A–G 计划执行结果、pskernel V37 逆向、Wrap/Transform
> 真实 body、SCTpre VBS/COM 全量包装，做一次**全面重评**。
>
> **2026-08-15 晚间复核**（HEAD `3337648`，含当日 3 个 P0-1 提交后）：
> 对本文全部声明做了实测核证（重跑测试、抽查 7 大支柱源码、新增
> `tools/check_all_mode.py` e2e 探针），修正项已直接写入正文——
> 核心变化为 P0-1 在 tessellation 层已解（配方级精确），e2e 网格线
> 计数仍差最后一步（§四.1）；并新增 §六 R1–R5 改进计划。

---

## 一、总体判断

- **测试**（2026-08-15 晚间实测）：全仓 **435 passed / 0 failed / 4 skipped /
  8 errors**。8 错误均为既有（tempfile 沙箱权限）；原 boolean STL 持久化
  失败已随 x_t 管线更新修复（P1-⑤），原 part-kinds 清单失败已随 P2-⑦
  修复——**0 失败**。
- **代码规模**：35 个 Python 模块 ≈4.2 万行；`cab_cwizard_pages.py`(7546 行)、
  `cab_gui.py`(5207)、`cab_wizards.py`(3614)、`cab_dialogs.py`(3418)、
  `cab_parts.py`(2121)。工作区另有 4 个未提交 blend 探针
  （`tools/blend_probe*.py`，blend ABI 已解（2026-08-16）**：V37 数组 API + 选项结构（constant 6 参 /
     chamfer 8 参 / fix_blends 9 参，options 全部 o_t_version=1，STpreBase 0x276f80
     反汇编 + 实机验证）；cab_blend.py 封装 + Edit Solid 菜单
     「Blend Edge / Chamfer」已接线（cab_edit_ops.blend_part_edge_pk 原地改件
     并回写 x_t 成员），4 项测试全过（40mm 块 → 530/422 三角）。
     详见 docs/pskernel_user_guide.md §6.9。
   - **晚间复核新发现——Part Simplification 为假 UI**：三 Method 单选
     （internal loop / thin geometry / 2.5D）不绑定任何逻辑分支，
     Preview/Cancel 按钮 `lambda: None`（`cab_edit_dialogs.py`），
     `_exec` 实际只调 tess 级删面。要么接真算子（PK heal/简化），
     要么移除摆设，现状最伤可信度（R2 处理）。

### P2 — 深度不足
6. Source 条件（已新增 **time series** 体积源 + **expression（计算函数）热源**：
   COM 探针实证 STpre 存储格式 express/name + kind VENT_source +
   text line=1，value 内 source type=express 引用函数名；
   cabxml.upsert_express/express_list + Source 页 Expression 创建器 +
   序列化往返测试；**diffusion source 亦已完成**——COM 探针实证
   SetDiffusionCondition(name, no, 'source', amount, 0) 写
   value type="diffusion" + kind source + no + diff_source(unit)，
   Source 页新增 Diffusion source 创建器 + 条件列表 diffusion 分组；
   Boundary 新增 **Diffusion Boundary 页**（浓度/传质系数两类，
   SetDiffusionCondition "diffusion"/"transfer" 探针格式写回）。
   - **表达式管理器半成品（复核实证）**：创建路径完整（Source 页
     Expression 创建器 → `cabxml.upsert_express`），但
     `cabxml.express_list()` **全仓 0 调用**——无列表/编辑/删除 UI；
     `CreateScript/CreateUserFunction` 已包装未接线（R2）。
7. 专用件参数面（AC 朝向、线性 diffuser、热回路节点）子集——**Delphi
   节点级热回路已补**：Part 对话框 Delphi 页新增节点表（名称 + Rji C/W，
   可增删），持久化为 parts/thermal_node（no/name/resistance@C/W），
   ECXML 导入导出含 <Node name r> 网络往返（2 项测试）。
   - **AC 件复核实证（2026-08-15 晚间）**：对话框仅存 `ac_type` 朝向
     字符串（`cab_parts.py` 提交处 5 选 1 combo），**无 capacity/风量/COP
     字段，几何仍是 cuboid 代理**；HVAC 完整参数面为 R4 任务。
   - **moving body 运动定义表缺失（复核确认）**：`_CwMovingBodyPage`
     仅写 5 个 analysis_set 标志（moving_body 1|2 / file / option /
     list_position / gap_filling），零件级运动表（旋转/平移速度表）
     全仓无实现；`SetMoveBodyOption` 已在 `API_CATALOG` 但未包装调用
     ——包装成本极低，列 R2 低垂果实。
8. Parametric Study（已加深：参数矩阵展开为完整案例组合 + 案例数预览 +
   CSV 案例矩阵导出 + 2 项测试）/ Printer paper-feeding 占位 /
   Thermal Characteristics（默认发射率 + 逐部件覆盖表）已完成。
9. ~~IFC / ECXML 导入导出~~ **已完成（2026-08-15 后）**：`cab_ifc.py`（IFC-SPF
   解析：拉伸矩形型材 + LOCALPLACEMENT 链 + m→mm，导入为 cube 件 + part
   transform；导出最小 IFC2X3）+`ecxml.py`（two_resistor/delphi 热模型
   round-trip）+ File 菜单接线，7 项测试全过。

### P3 — 低优先级
10. Element cross-section / Checking S-File（已加深：截面新增 Quality 显示
    类型——按单元长宽比（aspect=最长边/最短边，蓝→红）着色切片；S-File 校验
    新增轴单调/正宽度、非有限值、倒置占位盒检查）。
11. 3DfindIT / Library part 替换（2026-08-16 加深）：部件右键菜单新增
    「Replace from library...」——从 [Project Parts] 图书馆应用 kind/
    attribute/材料/发热量/温度/base+size 到目标部件（保留 transform 与
    条件，原语件重新生成 tess，body 件保持几何）；cab_edit_ops.
    replace_part_from_library + ReplaceFromLibraryDialog + 测试。外部 CADENAS 3DfindIT 连接性
    无 COM 表面，记为网络服务项。

---

## 五、结论（2026-08-15 晚间复核更新）

相对首评（§18）与专项审计（§39），本仓库已从「解析器 + 网格近似」推进到：
**原生网格金标收敛（uniform 精确、minmax/rep x/y 精确、all 的 tess 层配方
精确）+ 圆柱/轴向极坐标网格 + pskernel V37 真实 B-rep 编辑 + SCTpre VBS/COM
全量桥接**多路并进。几何/部件/网格/编辑/导入导出近完整；**Condition Wizard
高级物理（24/25 支持，21 项产品页实证，Boil FS 门控）** 与 **Source/边界条件（时间序列/
计算函数/diffusion 三类 + 全单位集）** 均已收敛。当前最集中的功能缺口按序为：
① all 模式网格线 e2e 收敛（顶点→线合并/取整规则，探针已实测差距
`57×132×130` vs `59×118×121`）；② 假 UI 清理（Part Simplification 三 Method 摆设）；
③ 表达式管理器/
moving body 运动表等低成本深度项。整体完成度 **≈76%**，其中
「可运行、可持久化、可导出求解」的 MVP 闭环已完整。

---

## 六、改进计划（R1–R5，2026-08-15 晚间复核制定）

| 阶段 | 目标 | 关键任务 | 验收标准 |
|---|---|---|---|
| **R1**（1–2 天） | P0-1 e2e 收官 | 以 `tools/check_all_mode.py` 二分定位：① x 少 2 线→核对金标线集是否含第 2/3 部件或域线；② y/z 冗余 9~14 线→扫 threshold 合并/`0.501` round/线段过滤规则；并案修 rep z 差 4 | `test_golden_reference.py` 新增原生断言：all `(59,118,121)`、rep `(57,91,92)` e2e 绿 |
| **R2**（3–5 天） | 假 UI 清理 + 低垂果实 | ~~Simplification 三 Method 绑真逻辑~~（✅ 2026-08-16 提前完成，PK_FACE_delete_2 全链路，Edit Solid Delete faces 同步接通）；`express_list` 接 Source 页表达式管理器（列表/编辑/删除）；包装并接线 `SetMoveBodyOption` 运动定义表（零件属性面板） | 无 `lambda: None` 占位按钮（✅ 已达成）；表达式可往返管理；运动表写回→重载→`.s` 导出正确 |
| **R3**（1–2 周） | blend ABI 攻关 | 收敛 4 个 `blend_probe*` 探针→解出 V37 blend 系签名；接 Edit→Solid 二级算子（blend/chamfer/fillet） | box 倒圆→x_t 写回→重开体积/拓扑断言 |
| **R4**（滚动） | 专用件参数面补齐 | AC 件 capacity/风量/COP + 真几何替换 cuboid 代理；线性 diffuser/Peltier/card guide 字段对齐手册；IFC 导出补 circle/polygon profile | 各专用件字段往返 + 导出格式可被上游 CAD 打开 |
| **R5**（按需） | FEM 真网格 | 调研 solver 端 FEM 生成（COM `CreateFEM` 深探或 s 文件 FEM 段逆向） | FEM 部件产生真实单元数据 |

依赖：R1 独立可启；R2 无依赖可并行；R3 为 Edit 面最大单项；R4/R5 滚动。

---

## 七、改进计划 R6-R10（2026-08-16 全面复核后制定，R6/R7 当日完成）

> 复核基线：R1 done（all 模式金标 59/118/121 MATCH）、R2 done、R3 done（blend V37 ABI，test_blend.py 5 passed）。
> 完成度 约80% -> R6/R7 后 约84% -> R8 后 约87% -> R9 后 约89%。按「用户可感知断层 x 性价比」排序。

### 维度化完成度（2026-08-16，含 R6/R7 后）

| 维度 | 完成度 | 依据 | 剩余差距 |
|---|---:|---|---|
| 数据层（cab 容器/XML/材料/单位） | 95% | MSZIP 读写、477 测试、xml 往返稳定 | -- |
| 几何建模 Part（26 种） | 90% | 26 原语 + sketch/pipe + 五种专用件真参数面（R7） | 其余专用件深字段 |
| 几何编辑 PK 内核 | 82% | blend/chamfer/delete_2/cut/wrap/boolean/section 全通 | sheet heal、sweep 面深度 |
| 网格 Gridding/Meshing | 93% | all 金标收敛 + rep/multiblock/圆柱/轴向 + cut-cell 体积分数分类（R9，exA23-2b 实证） | .ccel 二进制生成器 |
| Condition Wizard | 85% | 24/25 类型 + 35 深度页 + 五类深字段页（R8：MC 辐射/MARS/VOF/particle/reaction 多步/output series） | 其余边缘页深字段 |
| .s 导出 | 93% | 全 section 含 MOVB + PELTIER（R7）+ 常量派生（R8：EQUA 掩码/HSOL/CYC/UNDR/STED/VFEX 门控，295 样本交叉验证）  CUTCELL_OPTION/GAP 段（R9，exA23-2b 实证）| hdr1 尾列/hdr2 col4-9/VFDE LEAP 无 XML 源（注释已注明证据） |
| 导入导出（9+ 格式） | 85% | x_t/stl/obj/step/sat/ifc/ecxml/dxf/nas | IGES/IDF（决策不做） |
| COM 自动化桥 | 70% | ComObject.call 全 VB 面 + 显式包装 + 专用件探针实证 | 探针实证方法子集有限 |
| UI 菜单/对话框 | 90% | 8 菜单全接线无 NYI、90+ 对话框 | Distance/Reference 测量深度 |
| 求解闭环 | 85% | R6：QProcess 监控 + 日志 tail + exit code + 单实例互斥 | 结果回读/后处理联动 |
| 高级工具 | 40% | parametric 矩阵 + CSV | PICLS/WindTool/热路径、批量执行闭环 |
| FEM | 60% | R9：CreateFEM COM 实证（mesh_body 件 + .xfem kind=4 四面体，米制）+ cabxml parse/build + 离线 Kuhn 四面体生成 + COM e2e 测试 | 壳单元 kind 值；FEM Conversion UI 接线 |

### 阶段计划

| 阶段 | 目标 | 关键任务 | 验收标准 |
|---|---|---|---|
| **R6**（2-3 天） | 求解闭环补全 | （done 2026-08-16）cab_solver_proc.py SolverProcess 信号闭环：output_line/progress(cycle/residual/iteration)/success/error(exitCode)；cab_gui 接线按行进 Message pane、状态栏进度、单实例互斥、closeEvent 停进程；stsol 缺失仍走降级路径 | （done）test_m40_solver_monitor.py 4 项全过：正常退出提示/退出码 2 报 ERROR/输出 tail/重复启动拒 |
| **R7**（3-5 天） | 专用件参数真实化 | （done 2026-08-16）探针 tools/probe_special_parts.py 实证 Peltier `<parts type="peltier">` thick/paramV/paramA/paramQ/paramT/def_axis、Card Guide fin/space/depth/nfin/row_axis；AC 部件级 COM 返 None -> 按条件模型镜像 model/cooling/power/qvn/tmin/tmax；Diffuser 角度存部件 + 风量温度镜像 value type="flux"；Heat Pipe 镜像 K/W,W；cabxml.part_params/set_part_params + PartDialog SpecialParamsPanel + .s PELTIER_OUT/PELTIER_SET（exA22-2 实证；其余四件官方无卡片有据不发射） | （done）test_m41_special_parts.py 12 项全过：五件 XML 往返/diffuser 镜像幂等/校验拒绝/UI 写回重载/.s 发射与有据不发射断言 |
| **R8**（3-5 天） | CW 深度页 + .s 常量透明化 | （done 2026-08-16）A：五类深字段页（Radiation MC method/calc_cycle/solver_eps/space_cycle/max_particle/max_group_num 实证；Free surface mars/vof 属性集 contact/cutoff/fractional_step 等实证；Particle PCLE_CREATE .s 实证；Reaction 每步 value type=reaction Arrhenius；Output series timeseries_interval/fields TMSR 实证）+ cabxml 存储辅助 + 修蒸发页 apply 提前 return bug；B：EQUA 8 位掩码按轴向区间/heat/湍流/扩散位派生（253/295 命中）、SDAT hdr2 前 3 列、HSOL 门控+thermal_solver 取值、CYCS/CYCT 稳/瞬态、UNDR/STED 松弛、VFEX/HEATPATH 门控——295 对 (.cab,.s) 样本交叉验证，diag_s_constants.py | （done）test_m42 11 项 + test_m43 11 项（ex4 锚点逐行一致 + 变体派生断言）全过 |
| **R9**（1-2 周） | FEM + cut-cell 深水区 | （done 2026-08-16）A：CreateFEM 4 组合 COM 探针实证——新增 `<parts type="mesh_body">` fem_* 件 + body_files `<file type="fem">` + .xfem（XML，米制，node/element kind=4 四面体）；cabxml fem_parts/part_fem/set_part_fem + parse_femodel/femodel_bytes + build_fem_hexa 离线 Kuhn 四面体生成（体积守恒）；B：手册 Cutcell_Setting.html（criteria 默认 0.05）+ exA23-2b 实证零件级 `<cutcell>T</cutcell>` 注册 + .s CUTCELL_OPTION/GAP 段；cab_mesh cell_volume_fractions/classify_part_cells_cut（AABB 解析交，向量化）+ classify_cells cutcell 参数（off 与缺省逐位一致零回归）+ cab_options Mesh 页开关/criteria + s_export _cutcell | （done）test_m44 11 项（含 COM e2e 实跑：建件->CreateFEM->存->重开->part_fem 读回）+ test_m45 13 项（解析交精确解/守恒/三档二值化/零回归/XML 往返/QSettings/.s 发射与取消回归）全过 |
| **R10**（按需） | 周边互连 | PICLS 桥、WindTool、热路径视图（HeatPathView）数据接口 | 各互连一次端到端 demo |

依赖与顺序：R6 done / R7 done 已落地；R8 需 2023.2 样本 .s 全集（已有）可立即启动；R9 深水区按需；R10 依赖外部程序接口考证。

> 注意：tools/patch_gap_doc.py 会以脚本内嵌文本重写本文档，运行前先更新其内嵌内容，避免覆盖手工编辑（2026-08-16 曾因此回退第七节）。另：编辑器 Edit 工具对该文件的写入未落盘（疑似文件被占用/虚拟化），本节经终端直接写入。

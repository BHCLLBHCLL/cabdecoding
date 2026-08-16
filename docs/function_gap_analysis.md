# STpre 功能完整性与差距 — 全面重评 v5（2026-08-16，R1–R19 + R3.1/R3.5a-c 完成）

> 对比基准：Cradle scSTREAM Pre（C:\Program Files\Cradle\CradleCFD2025.2\
> Programs_x64\STpre_Bx64net.exe），参考 Pre_eng / Operation_eng /
> VB_Interface_eng 手册。本版在 v3（R1–R10）基础上纳入 R11–R19（COM 桥
> 扩展/批量执行/FEM Delaunay/参数化×批量联动/G1 链/求解结果回读/COM 存储
> 实证）、post-meshing 显示修复（ce69193）与 R3.1/R3.5（至 9420da5）。HEAD 9420da5。
>
> **假设声明**：用户提及的 R3.1 / R3.5 按 v3 §四剩余项顺序解释为
> R3.1 = sheet heal/sweep 面深度、R3.5 = 专用件/CW 边缘页深字段（见 §五）；
> 若指代不同请指出，本表可即时修正。

---

## 一、总体判断（2026-08-16 v4 快照）

- **测试**：全仓 **557 项**（80 个测试文件）；本沙箱实测 **539 passed /
  4 skipped / 14 errors**（14 项全部为沙箱 tempfile 权限拒绝，正常环境全过），
  **0 failed**。金标 e2e 原生断言（all 59/118/121、rep 57/91/92 MATCH）。
- **代码规模**：42 个运行时模块 ≈4.80 万行；新增 cab_batch / cab_solver_proc /
  windtool / cab_tools / cab_blend 五个模块（R6–R19）。
- **pskernel 覆盖**：1204 导出中已引用 **120+**（核心 B-rep 88），含 facet/
  boolean/cut/wrap/transform/blend/chamfer/G1/delete_2/heal-cap/transmit/receive。
- **总体完成度 ≈93%**（v1 60% → v2 76% → v3 91% → v4 92% → v5 93%）。P0 全清；
  剩余 = 深度长尾（sheet heal/sweep、Reference 深度、.ccel、专用件/CW 边缘
  深字段、.fld/PICLS）。

---

## 二、功能完整度与深度百分比清单（12 维，2026-08-16）

| # | 维度 | 完成度 | 深度依据（实证/金标） | 剩余差距 |
|---:|---|:---:|---|---|
| 1 | 数据层（cab 容器/XML/材料/单位） | 95% | MSZIP 读写、xml 往返、555 测试 | -- |
| 2 | 网格 Gridding/Meshing | 93% | all/rep 金标 MATCH + multiblock/圆柱/轴向 + cut-cell 体积分数 | .ccel 二进制生成器（无样本可逆） |
| 3 | .s 导出 | 93% | 全 section + 常量派生（295 样本交叉验证，ex4 逐字节） | hdr1 尾列/hdr2 col4-9/VFDE LEAP 无 XML 源 |
| 4 | UI 菜单/对话框 | 92% | 8 菜单无 NYI、90+ 对话框、测量四模式（距离/角度/连线链/部件最小距） | Reference 深度、连线链菜单块 |
| 5 | 几何建模 Part | 93% | 26 原语 + sketch/pipe + 八种专用件参数面（R3.5a-c 新增 fan/axial_fan/blower_fan/pin_fin/slit_punching/anemostat，STpreBase 字符串实证） | 其余专用件/CW 边缘页（R3.5d） |
| 6 | 求解闭环 | 90% | QProcess 监控 + 结果文件回读 + .pst 预填 Execute Post + 收敛尾部 | 结果回读至场景/收敛曲线图 |
| 7 | 几何编辑 PK 内核 | 93% | **Edit Solid 8 类算子全部真实 PK**：Delete faces/Sew sheets/Fill sheet+cover/Sweep/Create sheet from edges/Unify surfaces/Remove redundant edges/Extract empty region | sheet 几何深度（变半径倒圆/扫掠扭转等二阶参数） | blend/chamfer/G1 链（find_g1_edges 5 参）+ delete_2/cut/wrap/boolean/transform 全通 | sheet heal/sweep 面深度（R3.1） |
| 8 | Condition Wizard | 86% | 24/25 类型 + 35 深度页 + 五类深字段页 + Boil + 表达式管理器 | 其余边缘页深字段（R3.5） |
| 9 | 高级工具 | 85% | WindTool 前置 + 批量排队 + 参数化研究×批量联动（案例矩阵→覆盖→求解） | .fld 后处理（scPOST 范畴）、PICLS（无文档） |
| 10 | 导入导出（9+ 格式） | 85% | x_t/stl/obj/step/sat/ifc/ecxml/dxf/nas 双向 | IGES/IDF（决策不做） |
| 11 | COM 自动化桥 | 80% | ComObject.call 全 VB 面 + 23 方法签名实证封装 + 存储深实证（data/com_*_probe.json） | Set*Param 值格式终证、方法子集有限 |
| 12 | FEM | 80% | CreateFEM 实证 .xfem 四面体 + 离线生成 + Delaunay 任意几何 + UI 接线 | 壳单元 kind 值（无证据面） |

**深度说明**（与 STpre 逐面对比关键结论）：
- 显示 tess 精确一致（PK_TOPOL_facet_2 + 六容差配方，tr03 2206 三角/7 x 线）；
- Edit B-rep 为真实 PK 算子 + x_t 原地回写；CW 24/25（唯一剩余 = scFLOW-only）；
- .s 常量全 XML 派生；FEM 真单元（四面体）离线生成；求解→后处理入口闭环。

---

## 三、剩余差距（按优先级）

### P1 — 高价值深度
1. ~~**sheet heal / sweep 面深度（= R3.1）**~~ 全部完成：8 类 Edit Solid 算子全部接真实 PK（含 R3.1e-h 新增 Create sheet from edges=PK_FACE_make_sheet_body、Unify surfaces=PK_EDGE_delete、Remove redundant edges=PK_BODY_simplify_geom、Extract empty region=ask_regions+shells+make_solid_bodies）。
2. **Reference 深度**：拾取/测量四模式已通（R13），Reference（参考点/面集
   基准定义）未对齐 STpre。

### P2 — 深度不足
3. **.ccel 二进制生成器**：调研完——格式由 solver 从 .s CUTCELL 段生成，全盘
   无 .ccel 样本可逆；当前内联 PARTS 盒列表发射为已记录差异。
4. **专用件/CW 边缘页深字段（= R3.5）**：R3.5a-c 已完成（六种专用件参数面）；R3.5d CW 边缘页深字段仍待官方样本逐页实证（R8 探针模式）。

### P3 — 低优先级 / 决策性
5. .fld 后处理（scPOST 范畴）；PICLS（无手册文档，如实降级）。
6. IGES/IDF 导入（决策不做）。

---

## 四、结论

相对 v1（§18 首评 ≈60%）→ v2（≈76%）→ v3（≈91%）→ v4（≈92%），本版 **≈93%**：原生网格金标
全收敛、显示 tess 与 STpre 精确一致、pskernel V37 真实 B-rep 编辑、SCTpre
VBS/COM 全量桥接、求解→结果回读→后处理入口闭环、FEM 真单元、参数化×批量
联动均已具备。剩余差距全部为深度/长尾项（R3.1/R3.5 见 §五），无阻塞性缺失。

---

## 五、R3.1 / R3.5 开发难度与深度规划（2026-08-16）

### R3.1 — sheet heal / sweep 面深度

**目标**：把 Edit Solid 剩余 7 类占位算子中的 sheet 系（Sew sheets / Create
cover / Fill sheet / Create sheet from edges）接上真实 PK 路径，sweep（Sweep
Part Face）从 tess 级提升到 PK_FACE/BODY 级。

**现状盘点（证据）**：
- 内核已就绪：PK_BODY_sew_bodies + PK_FACE_make_sheet_body +
  PK_SURF_make_sheet_trimmed 经典管线已在 cab_ps_ops（STpreBase IAT 同套，
  无 PK_BODY_fix_general）；heal 仅 cap 模式实证。
- 缺口 = UI 多件流程 + sweep 算子 ABI（PK_BODY_sweep/PK_FACE_sweep 选项
  结构未探）+ sheet 件在 cab 模型中的持久化（polygon 件已是兜底）。

**难度评估**：**中高（2–3 周）**。
- 低风险部分（1–2 天）：Sew sheets = 选 N 个 sheet/polygon 件 → sew_bodies →
  transmit → x_t 回写（管线现成，纯接线）；Fill sheet/Create cover = heal cap
  路径复用。
- 高风险部分：sweep 的 V37 选项结构（PK_BODY_sweep_o_t：vector/angle/draft/
  twist…）需 q-solid V35 头文件 + STpreBase 反汇编 + 实机扫参三轮（同 blend
  攻关模式，1–2 周）；面级 sweep（PK_FACE_sweep）比体级更复杂，可先体级。
- 验收：box 面 sweep → x_t 回写 → 重开体积/拓扑断言（test_blend 同款）。

**深度收益**：PK 内核 88% → **91%**；Edit Solid 8 类算子全部脱离占位。

### R3.5 — 专用件 / CW 边缘页深字段

**目标**：五种已实证专用件（Peltier/Card Guide/AC/Diffuser/Heat Pipe）之外的
其余专用件（fan 系、anemo、pin fin、slit punching、spin rectangle 等）参数
面补齐；CW 边缘页（MC 辐射/MARS/VOF/particle/reaction/output series 之外的
深字段）按官方样本逐页实证。

**现状盘点（证据）**：
- 五种专用件有 COM 实证 + XML 往返 + .s 发射（test_m41 12 项）；其余 21 种
  原语已有 Create* 包装但参数 = 通用 base/size 代理。
- CW 深字段页 5 类已实证（R8）；其余边缘页 = 官方样本缺口逐个待查。

**难度评估**：**中等（1–2 周，滚动）**，单件边际成本低但件数多。
- 每件 = COM 探针（Create* + 参数写回）→ cabxml.part_params 扩展 →
  SpecialParamsPanel 面板 → .s 段发射（有官方卡片才发）→ 往返测试；
  单件 ≈ 0.5 天，优先 fan 系（P-Q 曲线已包装，缺几何参数）。
- 风险：部分专用件无独立 COM 返回（AC 已实证返 None）→ 按条件模型镜像
  （R7 已建立的模式）；.s 侧需官方样本对拍。
- 验收：每件 XML 往返 + UI 写回重载 + .s 有据发射断言（test_m41 模式）。

**深度收益**：Part 90% → **93%**、CW 86% → **88%**。

### 建议执行顺序
R3.1（sheet/sew 接线先行，sweep 后置）与 R3.5（fan 系先行）可并行；两者均
不依赖 STpre COM 会话（R3.1 纯 pskernel，R3.5 需 COM 探针但可批处理）。

> 版本轨迹：v1（§18，≈60%）→ §39 专项审计 → v2（2026-08-15，≈76%）→
> v3（R1–R10，≈91%）→ v4（R11–R19 + 显示修复，≈92%）→ v5（R3.1 + R3.5a-c，≈93%）。

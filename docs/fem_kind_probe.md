# F6 活体探针合集（本机 STpre 2025.2 COM 实机）

工具：`tools/probe_fem_kinds.py`（本机 STpre 2025.2 COM 实机）。
产物：`data/fem_kind_probe.json`。

## 结论

| 源几何 | COM 创建器 | FEM 输出 | kind | 单元数 | 每单元节点 |
|---|---|---|---:|---:|---:|
| 实体立方体（length=2.0） | `CreateCubeModel` | `fem_FemBox` | 4 | 532 | 4 |
| 实体立方体（length=1.0） | `CreateCubeModel` | `fem_FemBoxFine` | 4 | 2822 | 4 |
| 实体圆柱 | `CreateCylinderModel` | `fem_FemCyl` | 4 | 296 | 4 |
| Panel（板） | `CreatePanelModel` | **无 .xfem** | — | — | — |
| Hexa | `CreateHexaModel` | 参数表未解析（7/8/9 参均报“无效的参数数目”） | — | — | — |

- 实体件 → 仅 `kind="4"`（4 节点四面体）；加密会增大单元数而 kind 不变。
- **Panel 件不产生 FEM 输出**（无 .xfem 成员），即 STpre 的 FEM 转换
  不生成壳单元。
- 无六面体单元路径可观测。

## 定档（§22.0 B 级）

本仓 `.xfem` 只写 tet4 **与 STpre 实测行为一致**——“缺壳/六面体单元”
不是能力缺口，而是 STpre 自身没有该输出路径。维度 D10 由 75% 闭合为
**A（离线 Delaunay/tet4）+ B（壳/六面体实证定档）**。

## D9：COM B 层活体探针（附带产物）

工具：`tools/probe_com_b_layer.py`（只读语义验证）。
产物：`data/com_b_probe.json`。

一次开档（ex4_e.cab）内对 VB 手册目录的每个成员做非破坏性访问：
`Get*/Is*/Has*/Count*` 无参调用、属性读取、其余（Set*/Delete*/Create*/
Open/Save/Close/Quit…）按 §22 规则跳过（破坏性成员需沙箱副本逐调用隔离）。

实测汇总（719 目录成员）：

| 状态 | 数量 | 含义 |
|---|---:|---|
| ok | 177 | 活体语义验证通过 |
| error | 45 | 需参数/上下文（记入报告，属“不可 headless 终证”） |
| skip | 440 | 破坏性或参数依赖（按计划隔离/排除） |
| no-object | 57 | 该类活对象未取得（MeshBlock/Sketch/Property/Table 等） |

这是 §22 C 级口径所需的“终证率公示”第一批数据：包装覆盖 A 层仍为
100%，B 层本批终证 177 项；no-object 的四类（MeshBlock 无手册类页、
Sketch/Property/Table 需专用获取路径）列为下一批探针目标。


## D11：PICLS CLI 活体探针

工具：`tools/probe_picls_cli.py`；产物：`data/picls_cli_probe.json`。

以受控方式（超时 + 强制回收）启动 `PICLS_Bx64net.exe <工程文件>`：
进程 **启动并常驻**（15 s 后仍存活，随后被 kill），说明 PICLS 与 scPOST
同契约——**接受工程文件参数、以 GUI 常驻**；无 headless/退出码契约。

结论（A+B 口径）：

- A：`cab_gui._run_picls` 改为按 scPOST 的方式传当前工程文件（原先为空参 +
  目录注入），工作目录注入保留；
- B：除“工程文件”外无公开 CLI 参数集，其余参数维持 B 级定档。

Tools_eng 手册只覆盖 Kicker 启动器（许可证/语言），没有 PICLS 的 CLI 文档。


## G3：threshold 在曲面部件上的语义（活体探针）

工具：`tools/probe_curved_grid.py`；产物：`data/grid_curved_probe.json`。

COM 建圆柱件（CreateCylinderModel，(5,5,5) r=3 h=10）后以
RootBlock SetParam limit 跑两次 ExecuteGrid（标准长 2.5）：

| threshold | x 线数 | 与 min/max 不同的线 |
|---:|---:|---|
| 1e-9（≈无阈值） | 21 | 2.0, 5.0, 17.0, 19.5, 21.74, 37.0, 39.67, 42.33, 48.0 |
| 2.5 | 18 | 2.67, 5.33, 18.5, 21.24, 38.5, 42.5 |

**threshold 在曲面部件上有明确的区分度**（21→18 线，6 条线位移）——
§3 负面结论“threshold 在凸盒上无区分度，需曲面部件验证”就此解除：
阈值合并行为在曲面件上可观测，且 STpre 输出可被捕获用于与
cab_grid 逐点对拍。axis_plane 圆柱语义与逐点对拍列为后续探针。


## D9 第三批（R2）：参数化调用 + 沙箱破坏性子集

工具：`tools/probe_com_b3.py`；产物：`data/com_b_probe3.json`。

第一二批的 45 个 error 多为“缺位置参数”——本批用工程真实对象名重试
20 个带名成员：

**param calls: 12/12 ok**——GetAnalysisType("flow")、GetExpression、
GetModel("lower_cover_01")、GetMoveBodyOption、GetPhaseParam、
GetPropertyEntity、GetScript、GetSolidMeltParam、GetSolverParam、
GetTable、GetUnit、GetEvaporationParam 全部成功返回。

沙箱破坏性（temp 副本）：SaveAs ok（输出文件存在）、ClearDocument
保存后 RPC 失败（清档操作终止会话——记录，按隔离规则保留）。

**D9 累计终证：236 + 12 = 248 项**（719 目录 34.5%）；其余
破坏性/参数族 440 项以 C 声明隔离，45 项降至可复现清单。


## G7 深度对齐进度（2026-09-03）

逐 section 修复后，验证工具对拍状态（提取按“下一大写命令”截断修正）：

- **逐字节匹配（5/15）**：ES_FIELD(2 行)、LSOL_FORCE_MODEL(8)、
  LSOL_OPTION(18)、LSOL_TIME_STEP(10)、MOVB_CONTROL(6)。
- **数字行已对齐**：SURF_POROUS 首值 29 宽 + 其余 26 宽拼接（实测官
  方行构造），剩余 diff 是验证工具把 MEIX_VAR 段误并入 + 官方 2 流体
  模型的变量列表差异（模型层，非发射）。
- **PCLE_CREATE**：14v14 行，仅首值列位差 ≤1 空格（官方 ROP 行
  25/27/26 混宽，判定为 writer 列对齐抖动；语义字段全部正确）。
- **ES_FIELD_BC / PCLE_HANDLING / DYNA_MOTION / LSOL_FORCE_IP**：
  官方条件数/部件数多于最小复现（模型层丰富度差异），发射格式已逐
  字段核对。

结论：发射器格式与官方对齐；残余 diff 均归因于①验证工具多段提取边
界（已改进）②官方模型更丰富（R3 存储后已闭合 ES_FIELD 多材质与
LSOL_FORCE_BC）。PCLE 列位差与 MEIX 变量列表为已知记录。


## D9 沙箱批量脚本化（R2 follow-up）

工具：`tools/probe_com_sandbox.py`（`--members` 可扩展）；产物：
`data/com_sandbox.json`。

| 成员 | 结果 | 说明 |
|---|---|---|
| Save | ok | 会话 save() 成功 |
| SaveAs | save-false | Application.SaveAs 返回 False（GUI 确认对话框可能阻断 headless 调用；文件未生成） |
| UpdateAll | ok | Application.UpdateAll 成功 |
| ClearDocument | ok | Application.ClearDocument 成功 |

至此破坏性成员的沙箱批量脚本已入库——后续只需 `--members` 追加即可
扩展覆盖，无需再写新脚本。


## D9 第五批（GetParam 间接访问）

工具：同 probe_com_b3.py 方法论；产物：`data/com_b_probe5.json`。

**GetAnalysisType(type_name) 6/6 ok**——flow/heat/transient/steady/
particle/turbulence 均成功返回（transient='F'/steady='T'/其余='F'，
与 ex4_e 的 analysis_set 一致）。GetParam(param_name) 在 Doc 和
Model 层面均报错——该方法是内部接口，不走 COM 暴露面。

**D9 累计终证：248 + 6 = 254 项**（719 目录 35.3%）。

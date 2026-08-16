# R6–R10 阶段对比报告

> 生成日期：2026-08-16
> 基线 `f7663b7`（c5/c7 完成）→ 现状 `2c11c9a`（R10 完成），跨度 4 个提交、5 个阶段（R6/R7 合并提交）。

## 一、总览

| 指标 | 基线（R6 前） | 现状（R10 后） | 变化 |
|---|---:|---:|---:|
| 综合完成度 | ≈80% | ≈91% | +11% |
| 全仓测试 | 461 passed / 4 skipped | 534 passed / 4 skipped | +73 |
| 代码规模 | — | 25 文件 +5666 / −44 行 | — |
| 新增运行时模块 | — | 3 个 | — |
| 新增探针/诊断脚本 | — | 6 个 | — |
| 新增测试文件 | — | 7 个（m40–m46，共 2046 行） | — |

## 二、各阶段提交明细

| 阶段 | 提交 | 文件数 | 增删行 | 核心产出 |
|---|---|---:|---:|---|
| R6 求解监控 | `00fd13a` | 9 | +1407 / −11 | `cab_solver_proc.py` + `cab_gui.py` 接线 |
| R7 专用件参数 | `00fd13a` | 9 | 同上 | `cabxml.part_params` + SpecialParamsPanel + PELTIER 段 |
| R8 CW 深度页 + .s 常量 | `934e3a7` | 8 | +1764 / −33 | 五类深字段页 + EQUA/HSOL/CYC/UNDR/VFEX 派生 |
| R9 FEM + cut-cell | `2eba6a9` | 10 | +1670 / −7 | `.xfem` 四面体 + cut-cell 体积分数分类 |
| R10 WindTool 前置 | `2c11c9a` | 6 | +840 / −8 | `SetFluxPower2` 等 + `windtool.py` + 工具定位 |

## 三、功能维度完成度对比

| 维度 | R6 前 | R10 后 | 关键变化 |
|---|---:|---:|---|
| 求解闭环 | 60% | 85% | QProcess 监控、日志 tail、exit code、单实例互斥 |
| FEM | 10% | 60% | CreateFEM COM 实证 + `.xfem` 解析 + 离线 Kuhn 四面体 |
| 高级工具 | 40% | 70% | WindTool 前置 + 外部工具定位 |
| Condition Wizard | 75% | 85% | 五类深字段页（MC 辐射/MARS/VOF/particle/reaction/output series） |
| .s 导出 | 85% | 93% | 常量 XML 派生（295 样本）+ CUTCELL/PELTIER 段 |
| 几何建模 Part | 85% | 90% | 五种专用件真参数面 |
| 网格 | 90% | 93% | cut-cell 体积分数分类 |
| COM 自动化桥 | 70% | 75% | 专用件/FEM/WindTool 探针实证 |
| 数据层 | 95% | 95% | 无变化 |
| 几何编辑 PK 内核 | 82% | 82% | 无变化 |
| UI 菜单/对话框 | 90% | 90% | 无变化 |
| 导入导出 | 85% | 85% | 无变化 |

## 四、新增模块与脚本

**运行时模块**：
- `cab_solver_proc.py` — 求解器 QProcess 监控（output_line/progress/success/error 信号闭环）
- `windtool.py` — 16 风向判定 + info 文件生成 + Weibull 东京表 + power-law 参数校验
- `cab_tools.py` — 外部 Cradle EXE 定位器（find_cradle_tool）

**探针/诊断脚本**（6 个，均含官方样本或 COM 实证）：
- `tools/probe_special_parts.py` — Peltier/Card Guide XML 存储实证
- `tools/probe_fem.py` — CreateFEM 落盘 `.xfem` 格式实证
- `tools/probe_cw_deep.py` — CW 深字段样本解包探针
- `tools/probe_windtool.py` — SetFluxPower2 落盘格式实证
- `tools/diag_s_constants.py` — 295 对 (.cab,.s) 常量交叉验证
- `tools/diag_cutcell.py` — cut-cell 分类诊断

## 五、测试覆盖详情（新增 73 项）

| 测试文件 | 行数 | 用例 | 覆盖点 |
|---|---:|---:|---|
| test_m40_solver_monitor.py | 165 | 4 | 正常退出 / 退出码 2 报错 / 输出 tail / 重复启动拒 |
| test_m41_special_parts.py | 316 | 12 | 五件 XML 往返 / diffuser 镜像幂等 / 校验拒绝 / UI 写回 / .s 发射 |
| test_m42_cw_deep_fields.py | 309 | 11 | 五页 XML+UI 往返 / 禁用移除 / 未知字段容错 |
| test_m43_s_constants.py | 281 | 11 | ex4 锚点逐行一致 + 8 类变体派生断言 |
| test_m44_fem.py | 317 | 11 | .xfem 解析 / 往返 / Kuhn 体积守恒 / COM e2e 实跑 |
| test_m45_cutcell.py | 384 | 13 | 解析交精确解 / 守恒 / 三档二值化 / 零回归 / QSettings / .s 发射 |
| test_m46_windtool.py | 274 | 11 | 16 风向角度 / Weibull 数值 / info 四节 / 8 区间挂接 / 工具定位 / XML 往返 |

**回归保障**：每个阶段均跑全仓回归且既有测试无回归（ex4 `.s` 输出、网格分类、COM 探针锚点逐位一致），最终 534 全绿。

## 六、关键突破（按难度/价值）

1. **求解闭环**（R6）：补上 STpre「Execute Solver」核心体验的最大断层
2. **.s 常量透明化**（R8）：295 对官方 (.cab,.s) 交叉验证，写死的头部分析量全部变 XML 派生，ex4 输出逐字节不变
3. **FEM 真单元**（R9）：原计划 1–2 周的深水区，当日 COM 探针实证 `.xfem` 四面体格式 + 离线生成
4. **WindTool 前置**（R10）：从官方 VBS 脚本反推 COM 接口并实证 power-law 落盘格式

## 七、剩余差距

- `.ccel` 二进制生成器
- 壳单元 kind 值（FEM）
- FEM Conversion UI 接线
- Distance/Reference 测量深度
- 批量执行编排
- `.fld` 后处理（scPOST 范畴）
- PICLS（无手册文档，无法考证接口）

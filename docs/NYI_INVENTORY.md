# cabdecoding NYI / 产品边界项清单

> 方法学沿 pphdecoding：完整度 100% 口径下，凡「灰显/不做/无法终证」
> 的项必须在此载明**边界理由**（§0.3 豁免清单的展开册）。
> 扫描可再生（本册为人工审计账，随批更新不丢账）。
> 建立日期：2026-09-05（v9.1 双口径重核）。

合计 **11** 项（边界 8 + 豁免 3）。

## 产品边界项（灰显/不做，理由载明）

### 1. MSC CoSim / BCI-ROM（D6 Condition Wizard / Analysis Types）

**产品边界**：scFLOW-only 耦合分析。scSTREAM .cab 工程格式无法承载其
配置（STpre 中该二项仅在 scFLOW 工程可勾选）；本仓保持灰显并在
`_CwAnalysisTypesPage._ALWAYS_DISABLED` 硬编码禁用（写入即失真）。

### 2. Draft（拔模）/ Midsurface（中面）（D7 几何编辑）

**内核边界**：pskernel.dll 实测 `PK_BODY_draft_2` 返回 5000、
midsurface 5022（本批几何不支持），且无 Transmit 导出面可绕行——
六算子 hollow/offset/replace/imprint 等真实可用，此二项为官方内核
在目标几何类上的能力上限（B 级定档，`docs/pskernel_user_guide.md`）。

### 3. .pst 会话解析（D8 求解闭环）

**决策边界**：scPOST 会话文件为 GUI 会话态，非求解数据本体；结果
文件（FPH/FLD/CGNS）直读由配套仓 `../flowviewer` 承接（348 tests 绿，
25 渲染模块），比解析 .pst 更本质。刻意不做，非缺失。

### 4. 非 MSZIP 压缩族（D1 数据层）

**样本边界**：MSCF 容器规范含多种压缩方法，但本仓全部官方样本
（Exercise/Validation/SCT 共 602 个 .cab）实测均为 MSZIP。解压端
未实现 LZX 等其他族——无样本即无对拍基准，出现即补。

### 5. STHM / POROUS_MEDIA / JOS_* 语义映射（D4 .s 导出）

**证据边界**：三类卡为系数/异构行结构（NASA 多项式系数、多孔材料
异构行、JOS-3 人体模型），官方语料各仅 1–4 个样本、无第二佐证源
可交叉验证字段语义。采用**逐字直传**（字节级保真）+ B 级定档，
语义映射待更多官方工程样本。

### 6. WindTool.exe / PICLS 参数深证（D11 高级工具）

**黑盒边界**：两外部工具已真实带参启动（P2 批），但其参数面为
第三方黑盒（无手册/无 API），除工程文件传递外无法逐字段终证——
深证上限为工具本体，非本仓缺口。

## 豁免项（达标口径不含，沿 pphdecoding §9.6）

### 7. 部件几何 Parasolid 实体复刻（D2 几何建模）

官方内核经 pskernel.dll ctypes 已全驱动（D7 六算子+二阶几何真实
执行）；Part 域的显示/网格为代理 tessellation，实体内核复刻不在
目标内（驱动 + 存储 schema 官方化即深度达标）。

### 8. D9 COM B 层 live 语义终证

A 层包装 719/719 全量闭环（typed 命名=VB 原名精确匹配）；B 层
live 语义终证对破坏性成员（删除/覆盖类）与 live-GUI-only 成员存在
headless 硬上限——沙箱隔离声明已入库（`data/com_sandbox.json`），
滚动终证随会话推进。

### 9. 求解器/scPOST 本体重写

scSTREAM 求解器与 scPOST 为官方可执行体，本仓走进程驱动 + 结果
直读路线（复刻无必要，同 pphdecoding §9.6-3 口径）。

## 差距项（完整度 <100% 的真实缺口，不入本册——见 gap §0.4）

- D2 专用件深字段逐字段复核未清零（滚动）
- D6 区域标量族等存储级值族无 CW 面板（下一 UI 批）
- D10 壳/六面体 FEM kind（特性批）
- D12 IFC 导出圆/多边 profile、STEP/SAT 导出（特性批）

### 10. FEM 壳/六面体单元 kind（D10）

**官方行为边界**（2026-09-05 复核确认，`docs/fem_kind_probe.md`）：
本机 STpre 2025.2 COM 实机 FEM 转换仅输出 kind=4 四面体——Panel 件
不产生 .xfem、无六面体单元路径可观测（CreateHexaModel 各参数表均
报无效参数数目）。本仓 tet4 离线 Delaunay/Kuhn 剖分 + .xfem 字节级
写端测试与官方行为一致；壳/六面体 kind 无官方输出面可对拍，不实现。

### 11. STEP/SAT 写端捆绑（D12）

**许可链边界**：STEP 导出走三降级分支（STPRE_STEP_CLI → pythonocc
OCC → B 级声明 SatExportUnavailable），SAT 仅 STPRE_SAT_CLI——
pythonocc/FreeCAD 均不能写 ACIS SAT，官方 STEP 导出同样依赖许可
CAD 链，本仓不捆绑运行时 writer（*import* 侧 STEP/SAT 已可用）。
IFC 导出三 profile（矩形/圆/任意多边）均已在位并有 roundtrip
测试（test_p3_import_export.py）。

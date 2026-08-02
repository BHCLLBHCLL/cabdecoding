# scSTREAM Pre cab 文件解析开发规划

> 更新日期：2026-08-03 ｜ 仓库：`cabdecoding` ｜ 格式细节见
> [CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md)

## 1. 总体判断

**可行性高，容器与数据源已完全打通，核心工作量集中在写端（重打包）与
业务层（XML 模型、.s 导出、GUI）。**

本次调研已完成的三项关键验证：

1. `.cab` = 标准 Microsoft Cabinet（MSCF）容器，魔数 `MSCF`，单文件夹、
   **MSZIP** 压缩，30 个 CFDATA 块，3 个成员（`ex4_e.xml` / `_ex4_e_property.xml`
   / `_ex4_e_all.x_t`）。已实现纯 Python 解包，解压结果与 Windows `expand`
   逐字节一致（md5 全同）。
2. cab 内两个 XML 为**标准明文 XML**（UTF-8 BOM），项目定义 `ex4_e.xml`
   含求解设置、部件/材料/条件、**网格坐标表（mesh_block）与部件盒表
   （element）**——即 `.s` 的 CXYZ 与 PARTS 数据源，导出无需重跑网格。
3. `.s`/`.xemt` 与 cab 成员的字段映射已逐项对上（材料 7 种、网格
   99×243×63 → 98×242×62 单元、region/条件名、文件名块等），且
   `flddecoding` 仓库已有可复用的 `.s`/`.xemt` 解析与 FLD 生成代码，
   `pphdecoding` 仓库已有可复用的 Parasolid 传输流解析与 PyQt5+VTK GUI 骨架。

## 2. 目标与范围

### 2.1 核心目标（本仓库交付物）

1. **cab 逆向解析**：容器解析/解包/摘要（CLI），成员级与内容级（XML、
   Parasolid 头部）展示。
2. **GUI 工具 + 元数据编辑**：参照 scSTREAM Pre 界面（Navigation / Tree /
   Property / Draw 四窗格），支持查看模型树、编辑部件名/材料/颜色/变换、
   求解参数、材料属性，保存后重打包 cab。
3. **导出 `.s` 与 `.xemt`**：从 cab 成员无损重建 SDAT 与 EMT，布局对拍
   官方导出的 `tests/ex4_e.s` / `tests/ex4_e.xemt`（先逐字节，后语义级）。

### 2.2 明确不做（长期项）

- Parasolid 完整 B-rep 拓扑还原（沿用 pphdecoding 的“部分提取”：schema/
  字段名/实体类型/SDL 属性）。
- 网格求解或 FLD 生成（flddecoding 已覆盖，仅做互操作对接）。

## 3. 系统架构

### 3.1 模块划分（规划）

| 模块 | 职责 | 复用来源 |
|------|------|---------|
| `cab_container.py` | MSCF 容器解析/写回：CFHEADER/CFFOLDER/CFFILE/CFDATA、MSZIP 跨块解压、重打包 | 本次调研的验证脚本（zdict 逐块解压） |
| `cab_model.py` | 高层 `CabProject`：成员分类、顺序拼接、magic 校验、摘要 | — |
| `cabxml.py` | `ex4_e.xml`（stpre）与 `_ex4_e_property.xml` 的解析/序列化（保留 BOM/注释/缩进）、模型对象 | pphdecoding `pphxml.py` 的 sanitize/round-trip 思路 |
| `parasolid.py` | x_t 传输流头/属性行/schema/实体部分提取 | 直接移植 pphdecoding `parasolid.py` |
| `s_export.py` | XML 模型 → SDAT `.s`（CXYZ/PARTS/REGION/条件/输出各段） | flddecoding `s_model.py` 的数据类与字段语义 |
| `xemt_export.py` | 属性库+部件表 → EMT `.xemt` | flddecoding `xemt_model.py` 的逆写 |
| `cab_vtk.py` | 部件几何（x_t 部分提取 + XML 变换/盒）→ vtkPolyData，离屏可测 | pphdecoding `pph_vtk.py` |
| `cab_gui.py` | PyQt5 + VTK 查看/编辑 GUI | pphdecoding `pph_gui.py` 的四窗格骨架 |
| `cab_parser.py` | CLI：摘要 / 解包 / 导出 .s+.xemt / round-trip | pphdecoding `pph_parser.py` 风格 |
| `tests/` | 容器往返、XML 编辑往返、导出对拍、GUI 离屏回归 | 两仓库测试惯例 |

### 3.2 数据流

```
.cab ──cab_container──▶ 成员流（顺序拼接 + magic 校验）
        ├──ex4_e.xml──────────▶ cabxml.stpreModel ──┬─▶ s_export ──▶ .s
        ├──_ex4_e_property.xml▶ cabxml.propertyModel┼─▶ xemt_export ─▶ .xemt
        └──_ex4_e_all.x_t─────▶ parasolid 部分提取 ─┴─▶ cab_vtk ──▶ GUI 3D
                                     │
                             cab_container.write ◀── 编辑后模型（GUI/CLI）
```

## 4. 分阶段开发计划

> 排序依据：依赖前置、可独立验收、风险从低到高。每阶段含交付物与验收标准。

### P0 容器层（1–2 天）

- 交付：`cab_container.py` + `cab_parser.py`（摘要/解包）+ `tests/test_container.py`
- 内容：
  - 解析 CFHEADER/CFFOLDER/CFFILE/CFDATA；按顺序拼接提取成员（uoffFolderStart
    实测为精确连续值，仍不依赖它，用 magic 校验：XML BOM / `**` 头）。
  - MSZIP 跨块解压（zdict 方案，验证 30 块全解、与 `expand` md5 一致）。
  - 写端：重打包（MSZIP 编码器选型见 §5 决策 1），round-trip
    「解包→原样重打包→再解包」逐字节一致（除 header 时间戳/校验和）。
- 验收：`pytest` 全绿；`cab_parser.py tests/ex4_e.cab` 输出 3 成员正确大小；
  重打包件可被 `expand` 解出原成员。

### P1 XML 元数据模型（2–3 天）

- 交付：`cabxml.py` + 模型数据类 + `tests/test_cabxml.py`
- 内容：
  - `stpre` 解析为结构化模型（unit/project/group/parts/region/analysis_set/
    output/value/condition/mesh_block/element），保留未知元素（forward-compat）。
  - 序列化器逐字节稳定（BOM、注释头、2 空格缩进、文本节点空格）。
  - 编辑 API：改部件名/材料/颜色/transform、条件值、求解参数、属性库物性。
  - round-trip「解析→序列化→重解析」+「改 XML→写回 cab→重解包」。
- 验收：序列化后与原件差异仅限注释时间戳（可选）；编辑字段在重解析后
  取值正确；对未知章节零丢失。

### P2 Parasolid 几何接入（2–3 天）

- 交付：`parasolid.py`（移植）+ `cab_vtk.py` + `tests/test_parasolid_cab.py`
- 内容：x_t 头属性行（FRU/APPL/DATE…）、`SCH_*`、T51 schema、字段表、
  实体类型（复用 pphdecoding 已验证逻辑）；按 XML `<parts>/<transform>`
  组装 vtk 场景（x_t 面片提取 + 变换矩阵 + 颜色）。
- 验收：ex4_e 全部 32 部件可列出；离屏渲染无异常；部分提取结果与
  pphdecoding 对同类型 x_t 的输出结构一致。

### P3 `.s` / `.xemt` 导出（3–5 天，核心攻坚）

- 交付：`s_export.py` / `xemt_export.py` + `tests/test_sxemt_export.py`
- 内容：
  - `.xemt`：先做，结构简单；对拍官方件语义级一致（序号/名称/分组/材料）。
  - `.s`：SDAT 各段生成——头部/STREAM、POST 文件名块、UNIT、EQUA/GRAV/
    HSOL/CYCS/UNDR、PROPERTY（属性库→7 材料）、CXYZ（mesh_block→m 制）、
    PARTS（element 盒表）、REGION/FLUX_REGION/INIT_REGION 等（face list +
    value/condition 映射）、FOUT/MEIX_VAR 等输出段。
  - 对拍：`tests/ex4_e.s`（官方）vs 本仓库导出，先文本 diff 定位差异段，
    再逐段语义对拍；`flddecoding` 的 `s2fld`/`sxemt2fldcgns` 作为独立
    消费端验证（导出的 .s+.xemt 能跑通 FLD 生成）。
- 验收：`.xemt` 与官方件结构化一致；`.s` 各段字段值一致（容许空格/格式差），
  且导出的 `.s+.xemt` 可被 flddecoding 管线正常消费。

### P4 GUI（4–6 天）

- 交付：`cab_gui.py`（+`requirements-gui.txt`）+ `tests/test_gui.py`
- 内容：沿用 pphdecoding 四窗格骨架并参照 scSTREAM Pre 手册：
  - **Navigation Window**：打开/另存/重打包 + 文件信息卡片（成员、压缩率、
    XML 章节、Parasolid 摘要）+ 分组导航树。
  - **Tree Window**：项目树（计算域/组/部件/region/条件/求解设置/网格/
    材料库）；右击编辑元数据；模型树复选框控制 3D 显隐。
  - **Property Window**：选中项的结构化属性（可编辑字段高亮，保存→
    XML 模型更新→重打包）。
  - **Draw Window**：部件 3D（x_t 提取 + 盒体预览）、着色/线框、剖切、
    Fit/Reset、坐标指示器。
  - **导出**：一键导出 `.s`+`.xemt`（调用 P3 管线）。
- 验收：离屏回归（构建/信号/编辑写回）；打开 ex4_e.cab → 改部件名 →
  导出 .s/.xemt → 重打包 → 重开一致。

### P5 样本扩充与验证（数天–数周，持续）

- 交付：新增样本到 `tests/` + `tests/test_samples.py`（跨样例扫描）
- 内容：收集不同版本/规模 cab（2024、2025.2、多网格组、多材料/辐射/
  湿度/粒子案例），跑结构不变量：CFHEADER 布局、成员顺序、XML 章节集、
  uoffFolderStart 布局规律、MSZIP 块参数。
- 验收：跨样例扫描全绿；未验证项显式标注（不当作已验证）。

## 5. 关键技术决策

| # | 决策点 | 方案 | 理由 |
|---|--------|------|------|
| 1 | MSZIP 写端 | 首选 Windows `CreateCompressor(MSZIP)`（cabinet 相关 API）；备选自研受限编码器（每块独立窗口，压缩率略降但合法） | 标准库无跨块历史编码；写端需 SCTpre 实机验收 |
| 2 | 成员定位 | 按顺序累加 cbFile + magic 校验（uoffFolderStart 实测精确连续，作为交叉核对） | 稳健且不依赖元数据约定 |
| 3 | XML 序列化 | 自研稳定序列化器（保 BOM/注释/缩进/未知元素） | ElementTree 默认输出会破坏空格与注释 |
| 4 | CFDATA 校验和 | 读端忽略（工具兼容），写端先写 0 并记录 | 算法未验证（见格式说明 §10） |
| 5 | Parasolid 展示 | 部分提取（复用 pphdecoding） | 完整 B-rep 为长期项 |
| 6 | .s 验证链 | flddecoding 的 s2fld/sxemt2fldcgns 作消费端 | 独立第三方管线可证明导出的可用性 |

## 6. 风险与应对

| 风险 | 等级 | 应对 |
|------|------|------|
| 重打包 cab 不被 SCTpre 接受 | 高 | 先做「原样成员重打包→SCTpre 打开」最小验证；再增量改 header 字段；保留 expand + 自研双向验证 |
| `.s` 面分类（face list → BC）映射不全 | 中 | 用 ex4_e 官方 .s 对拍建黄金表；face 编号 `-1..-6` 语义以 element 节与 region 名互证 |
| 单样本过拟合（XML 章节集/header 布局） | 中 | P5 样本扩充；解析器对未知章节零丢失、显式报告 |
| 新版 cab 布局变化（2024/2025.2） | 中 | 解析层版本门控（version 头注释 + STREAM 版本行），格式说明按版本记录 |
| MSZIP 写端跨块历史实现复杂 | 中 | 备选「每块独立窗口」合法编码器；压缩率差异可接受 |

## 7. 测试策略

- 单元：容器头/块解析、XML 模型、导出各段。
- 往返：解包→重打包→再解包逐字节一致；XML 改→写回→重解析一致。
- 黄金对拍：官方 `tests/ex4_e.s`、`tests/ex4_e.xemt` 结构化/语义对比；
  `expand` 提取件 md5 对比。
- 消费端：flddecoding 管线消费导出的 `.s+.xemt`。
- GUI：离屏构建/信号回归（沿用 pphdecoding `test_gui.py` 模式）。

## 8. 建议执行顺序与里程碑

1. **M1（本周）**：P0 容器层 + P1 XML 模型（含 round-trip 测试）。
2. **M2（次周）**：P2 几何接入 + P3 `.xemt` 导出。
3. **M3（第 3 周）**：P3 `.s` 导出对拍完成（黄金 diff 通过）。
4. **M4（第 4–5 周）**：P4 GUI 交付（查看/编辑/导出/重打包闭环）。
5. **M5（持续）**：P5 样本扩充，收敛开放问题（校验和算法、MSZIP 写端
   实机验收）。

依赖：P1 依赖 P0；P3 依赖 P1（+P2 的几何信息用于面分类交叉验证）；P4 依赖
P1–P3；P5 与各阶段并行推进。

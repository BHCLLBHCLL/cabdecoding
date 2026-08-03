# scSTREAM Pre cab 文件解析开发规划

> 更新日期：2026-08-04 ｜ 仓库：`cabdecoding` ｜ 格式细节见
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
- 完整 B-rep 拓扑还原仍为长期项；**显示级曲面已通过 Cradle
  `pskernel.dll` 的 GO 面片化实现**（2026-08-04，见 §10）。
- 网格求解或 FLD 生成（flddecoding 已覆盖，仅做互操作对接）。

## 3. 系统架构

### 3.1 模块划分（规划）

| 模块 | 职责 | 复用来源 |
|------|------|---------|
| `cab_container.py` | MSCF 容器解析/写回：CFHEADER/CFFOLDER/CFFILE/CFDATA、MSZIP 跨块解压、重打包 | 本次调研的验证脚本（zdict 逐块解压） |
| `cab_model.py` | 高层 `CabProject`：成员分类、顺序拼接、magic 校验、摘要 | — |
| `cabxml.py` | `ex4_e.xml`（stpre）与 `_ex4_e_property.xml` 的解析/序列化（保留 BOM/注释/缩进）、模型对象 | pphdecoding `pphxml.py` 的 sanitize/round-trip 思路 |
| `parasolid.py` | x_t 传输流头/属性行/schema/实体部分提取 | 直接移植 pphdecoding `parasolid.py` |
| `ps_tessellate.py` | x_t body 经 Cradle `pskernel.dll` 接收 + `PK_TOPOL_render_facet` GO 面片化 → `TessPart`（点/三角形），显式面片容差 | Cradle Parasolid 内核 / GO 文档 |
| `s_export.py` | XML 模型 → SDAT `.s`（CXYZ/PARTS/REGION/条件/输出各段） | flddecoding `s_model.py` 的数据类与字段语义 |
| `xemt_export.py` | 属性库+部件表 → EMT `.xemt` | flddecoding `xemt_model.py` 的逆写 |
| `cab_vtk.py` | 部件几何（x_t GO 面片 + XML 列主序变换 + 点法线/锐边拆分）→ vtkPolyData，离屏可测 | pphdecoding `pph_vtk.py` |
| `cab_gui.py` | PyQt5 + VTK 查看/编辑 GUI | pphdecoding `pph_gui.py` 的四窗格骨架 |
| `cab_parser.py` | CLI：摘要 / 解包 / 导出 .s+.xemt / round-trip | pphdecoding `pph_parser.py` 风格 |
| `tests/` | 容器往返、XML 编辑往返、导出对拍、GUI 离屏回归 | 两仓库测试惯例 |

### 3.2 数据流

```
.cab ──cab_container──▶ 成员流（顺序拼接 + magic 校验）
        ├──ex4_e.xml──────────▶ cabxml.stpreModel ──┬─▶ s_export ──▶ .s
        ├──_ex4_e_property.xml▶ cabxml.propertyModel┼─▶ xemt_export ─▶ .xemt
        └──_ex4_e_all.x_t─────▶ ps_tessellate（pskernel GO 面片化）──▶ TessPart
                                       │
                                       ├─▶ parasolid 部分提取（元数据/头部）
                                       └─▶ cab_vtk（列主序变换 + 点法线）──▶ GUI 3D
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

## 9. 实现状态（2026-08-04）

| 阶段 | 状态 | 说明 |
|------|------|------|
| P0 容器层 | ✅ 完成 | `cab_container.py` + `cab_parser.py`；10 项测试；重压缩 cab 已由 Windows `expand` 解包逐字节验证 |
| P1 XML 模型 | ✅ 完成 | `cabxml.py`；7 项测试；两个 XML 成员字节级往返，编辑→重打包→重解析闭环 |
| P2 几何接入 | ✅ 完成 | `parasolid.py`（文本 x_t 部分提取）+ `ps_tessellate.py`（pskernel GO 面片化）+ `cab_vtk.py`（点法线/变换/离屏渲染）；8 项测试 |
| P3 导出 | ✅ 完成 | `s_export.py` + `xemt_export.py`；5 项测试；`.s` 与官方 1021 行**零结构差异**（仅 CXYZ 末位 1-ulp 舍入差），`.xemt` 仅日期注释不同；flddecoding `s_model` 消费一致 |
| P4 GUI | ✅ 完成 | `cab_gui.py`（PyQt5+VTK，四窗格）+ `requirements-gui.txt`；Part shading 使用 x_t 光滑曲面，Element division 使用网格盒线；5 项离屏测试 |
| P5 扫描 | ✅ 基础就绪 | `tests/test_samples.py` 自动发现 `tests/**/*.cab` 跑结构不变量/往返/导出对拍；当前样本：ex4_e / box / tr03 |

全仓测试：`python -m pytest tests -q` → 59 项通过、3 项跳过（`box.cab` /
`tr03.cab` / `tr03_$$$.cab` 无官方 `.s/.xemt` 对拍文件）。
`test_samples.py` 已改为按实际成员名动态匹配，不再把新样例误判为 ex4_e。
剩余开放项（见 CAB_FORMAT_SPEC.md §10）：CFDATA 校验和算法、多样本覆盖
（2024/2025.2 版本、多网格组、多材料/辐射/湿度/粒子案例）、.s 面分类的
跨版本确认、Parasolid 完整 B-rep 拓扑（长期项；显示级已解决，见下节）。

## 10. Parasolid 曲面显示问题分析与修复（2026-08-04）

### 10.1 现象

关闭 Element division 后，scSTREAM Pre 能显示光滑的 `.x_t` 曲面，而
cab_gui 显示为阶梯状/棱面，不像原始 Parasolid 几何。

### 10.2 根因

GO 三角形本身解析正确（ex4_e 的 24 个 body 全部可解析，面片均为单环
三角形 `lntp=[occ, 3007, 1, 3]`），问题出在以下四个下游环节：

1. **面片精度未控制**：`PK_TOPOL_render_facet` 之前传入全零选项，Parasolid
   使用内核内部默认容差，`lower_cover_01` 仅 790 个三角形，曲率面明显有棱。
2. **没有点法线**：生成的 `vtkPolyData` 只有三角形坐标，VTK 退化为
   flat shading，每个三角形按平面着色，视觉上就是“阶梯面”。
3. **GO 选项结构偏移错误**：旧代码把 `go_option` 硬编码在缓冲区第 200 字节；
   x64 下 `PK_TOPOL_facet_mesh_o_t` 实际为 368 字节，后续字段会写错位置。
4. **XML transform 未应用**：`.x_t` 内 body 为局部坐标，cab_gui 直接渲染
   tess 坐标，未乘 `<parts>/<transform>`，所有零件叠在原点。

### 10.3 修复

- `ps_tessellate.py`：用完整 ctypes 结构体替代裸缓冲区；显式设置
  `surface_plane_tol=1e-4`、`surface_plane_ang=12°`（可通过
  `tessellate_xt(facet_tol=..., facet_angle_deg=...)` 调整）。
- `cab_vtk.py`：`vtkCleanPolyData` + `vtkPolyDataNormals` 计算点法线，
  45° feature angle 拆分锐边；按 XML 列主序 transform 应用 `hom @ m`，
  并修正 `_box_bounds_from_cube` 的矩阵方向。
- `cab_gui.py`：Part shading actor 显式 Gouraud + ambient/diffuse/specular。

### 10.4 验证

- ex4_e 全模型面片数：默认 9,826 → 25,006 个三角形；
  `lower_cover_01`：790 → 2,110 个三角形。
- 24/24 个 body 挂接 CAD 网格且均带点法线。
- 应用 transform 后 CAD 包围盒与 XML `element` 网格盒完全对齐。

### 10.5 tr03 补充：无 `element` 网格 + 嵌套 `group`（2026-08-04）

- tr03 只有 `.x_t`，尚未生成网格：XML **没有 `<element>` 章节**，且
  `<group>` 嵌套一层（`tr03 → tr02`）。
- 根因：`cabxml.StpreModel.parts()` 只遍历顶层 group，模型读不到
  Case/Impeller/Rotate；`cab_vtk.part_boxes()` 又在挂接 CAD 前直接
  跳过无网格盒的部件，于是 GUI 只剩域框/网格线框。
- 修复：
  - `StpreModel.groups()/parts()` 递归遍历嵌套 group；
  - `part_boxes()` 对无 `element` 但有匹配 Parasolid body 的部件先建
    占位 `PartBox`，CAD 挂接成功后保留，否则丢弃；
  - 新增 `test_tessellate_cad_only_no_element_mesh` 回归。

### 10.6 box 补充：根级 `<parts>` + SDL 名称脏字节（2026-08-04）

- box.cab 的 `<parts type="body">` 直接放在 `<stpre>` 根下，**没有
  `<group>`**；原 `StpreModel.parts()` 只从 group 内取部件，因此模型层
  读不到 box。
- x_t 中 `SDL/TYSA_NAME` 属性列表里有多个非字符串属性，`PK_ATTRIB_ask_string`
  对它们返回未初始化字节（如 `b'\xd6\xd7\xd7'`），旧的 `body_name` 按
  ASCII + replace 解码后得到 3 个替换字符，长度与真正的 `"box"` 相同但先
  出现，导致 CAD 按名称挂接失败。
- 修复：
  - `StpreModel.parts()` 同时收集根级 `<parts>` 与所有 group 内部件；
  - `ps_tessellate.body_name()` 只接受可打印 ASCII，过滤脏字节，
    保证 `"box"` 能成为 body 名；
  - Tree 增加“(ungrouped)”节点显示根级部件；
  - 新增 `test_tessellate_root_level_parts_no_group` 回归。

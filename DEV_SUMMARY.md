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
| `ps_facet2_nodes.py` | STpre 同源节点路径：`PK_TOPOL_facet_2` 表格化面片（facet→fin→data→point→坐标）→ `TessPart`；GO 仅作回退 | 反汇编 STpreBase/ParasolidGW/pskernel，见 CAB_FORMAT_SPEC §5.2 |
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
        └──_ex4_e_all.x_t─────▶ ps_facet2_nodes（facet_2 表路径 ≡ STpre）──▶ TessPart
                                       │  （失败时 ps_tessellate GO 回退）
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
| P2 几何接入 | ✅ 完成 | `parasolid.py`（文本 x_t 部分提取）+ `ps_tessellate.py`（pskernel GO 面片化）+ `ps_facet2_nodes.py`（facet_2 表路径，STpre 同源）+ `cab_vtk.py`（点法线/变换/离屏渲染）；8+3 项测试 |
| P3 导出 | ✅ 完成 | `s_export.py` + `xemt_export.py`；5 项测试；`.s` 与官方 1021 行**零结构差异**（仅 CXYZ 末位 1-ulp 舍入差），`.xemt` 仅日期注释不同；flddecoding `s_model` 消费一致 |
| P4 GUI | ✅ 完成 | `cab_gui.py`（PyQt5+VTK，四窗格）+ `requirements-gui.txt`；Part shading 使用 x_t 光滑曲面，Element division 使用网格盒线；5 项离屏测试 |
| P5 扫描 | ✅ 基础就绪 | `tests/test_samples.py` 自动发现 `tests/**/*.cab` 跑结构不变量/往返/导出对拍；当前样本：ex4_e / box / tr03 |

全仓测试：`python -m pytest -q` → **58 项通过、2 项跳过**（2 项为
`test_samples.py` 缺少官方 `.s/.xemt` 对拍文件，与本改动无关）。
新增 `tests/test_ps_facet2_nodes.py`（3 项）：box 8 节点/12 三角形坐标与 GO
一致；tr03 三个 body 三角形数与 GO 完全相同；facet2 TessPart 可挂接
cab_vtk 并生成点法线。临时文件已清理：`tests/tr03_$$$.cab`、`__pycache__`、
`.pytest_cache`。
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

## 11. Parasolid `PK_TOPOL_facet_2` 表路径逆向与修复（2026-08-04）

### 11.1 定位

遍历 `C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64`，确认 STpre 从
`.x_t` 生成显示节点的调用链（RVA 均相对 DLL 基址 0x180000000）：

```text
STpreBase_Bx64.dll
  ?MakeFacet@PreBody@@QEAAHHPEAVFacetParam@@@Z        RVA 0x293A20
  ?MakeFacetParam@PreBody@@QEAAPEAVFacetParam@@QEAN@Z RVA 0x293C20
      ↓
ParasolidGW_Bx64.dll
  ?PKBody_GetTriangles@LocalParasolid@@...            RVA 0xA49A0 等
  ?PKFaces_RenderV3@LocalParasolid@@...               RVA 0x1415C0 / 0x141850
      ↓
pskernel.dll
  PK_TOPOL_facet_2                                    RVA 0x44DFA0
  PK_TOPOL_facet_2_r_f                                RVA 0x44FCE0
```

输出独立脚本 [ps_facet2_nodes.py](ps_facet2_nodes.py)：纯 ctypes 复现
`PK_TOPOL_facet_2` 表格化面片（facet→fin→data→point→坐标），GO 仅作回退。

### 11.2 深层次根因（为什么之前 box/tr03 无曲面）

1. **V5 选项结构此前只按“V35 文档顺序”猜测**：18 个 choice 字节确实在
   0x138..0x149，但本内核的 `point_vec/normal_vec/data_curv_idx` 三者的
   偏移与文档相反（文档：data_curv_idx 在前；内核：point_vec 0x141 /
   normal_vec 0x142 / data_curv_idx 0x143）。按旧偏移 `opts.point_vec=1`
   实际打开的是 normal_vec，拿到 6 个法向量而非坐标。
2. **token 同样不按文档顺序**：坐标表 token 为 **0x57BB**（不是 0x57BC）；
   0x57BC 是 normal_vec，0x57BD 才是 data_curv_idx。旧代码把 0x57BC 当
   point_vec 解码，得到 6 个 ± 单位轴向量，三角形组装全部退化/越界，
   `facet2()` 返回 None → GUI 退回结构化网格盒（阶梯状）或线框。
3. **索引表解析错误**：`fin_data`/`data_point_idx` 是 4 字节 int 数组
   （`data[fin]`、`point[data]`），旧代码按 8 字节 pair 解析，max 索引可达
   26 亿，读取越界崩溃。
4. **参数检查器**：外部进程必须 `PK_SESSION_set_check_arguments(0)`，否则
   返回 `PK_ERROR_o_t_version_incorrect`(5022)。

三个交叉验证锁定正确映射：逐字节单开 choice 探测；box 上 0x57BB 数据恰为
8 个角点且与 GO 逐点一致；STpre 解码器（ParasolidGW `PKBody_GetTriangles`）
按 24 字节步长从 0x57BB 读坐标。

### 11.3 修复

- `ps_facet2_nodes.py`：
  - 修正 `CHOICE_OFFSET`（point_vec=0x141 / normal_vec=0x142 /
    data_curv_idx=0x143）与 `FCTAB_*` 常量（POINT_VEC=0x57BB /
    NORMAL_VEC=0x57BC / DATA_CURV_IDX=0x57BD）；
  - `facet_fin` 按 8 字节 `{facet, fin}` 查找表解析；`fin_data` /
    `data_point_idx` 按 4 字节索引数组解析；`point_vec` 按 24 字节向量解析，
    并防御 `-1` 洞环分隔符与越界；
  - 新增 `available()` 与 `tessellate_xt(bytes)` 供 GUI 使用。
- `cab_gui.py`：加载时优先 `ps_facet2_nodes.tessellate_xt()`（STpre 同源），
  失败退回 `ps_tessellate`（GO）。
- `ps_tessellate.py`：`_get_session()` 复用已由 `ps_facet2_nodes` 启动的
  pskernel 会话（同一进程只允许一个会话，否则 PK_SESSION_start 返回 932）。

### 11.4 验证

- box：8 节点 / 12 三角形，坐标 0..0.01 与 GO 逐点一致；
- tr03：Case 1573/3142、Impeller 1030/2132、Rotate 102/200，三角形数与 GO
  完全相同，节点数不增（共享顶点去重更优）；
- ex4_e：24 个 body 全部经 facet2 生成，三角形数与 GO 完全一致；
- 全仓 `pytest`：58 通过 / 2 跳过（跳过与本次无关）。

格式细节（choice 偏移表、表 token、表编码、`set_check_arguments` 说明）已
同步至 [CAB_FORMAT_SPEC.md](CAB_FORMAT_SPEC.md) §5.2。
更完整的备查档案（工具、RVA 换算、逐字段偏移、探测脚本、错误码、基线数据）
见 §12。

## 12. 逆向详细档案（备查，减少后续定位成本）

> 本节是把本次反汇编、探测、解码的**全部可复现细节**固化下来。后续遇到
> Parasolid 曲面/面片相关问题，先按 §12.6 的探测流程复现，再对照 §12.5 的
> 表编码和 §12.8 的基线数据，通常能直接定位是“结构偏移错”还是“表解码错”。

### 12.1 工具与前置知识

- 反汇编：`objdump -d -M intel --start-address=<VA> --stop-address=<VA>`，
  或 Python capstone（本机已装 capstone 5.0.7）。
- 二进制：`C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\`
  - `pskernel.dll`（72 MB，真正的 Parasolid 内核）
  - `ParasolidGW_Bx64.dll`（Cradle 对内核的 C++ 包装）
  - `STpreBase_Bx64.dll`（STpre 上层，含 `PreBody::MakeFacet`）
- 官方文档镜像（V35，可访问）：`http://www.q-solid.com/Parasolid_Docs_V35/`
  - 表格化面片章节：`chapters/fd_chap.110.html`
  - 表结构头文件：`headers/pk_topol_fctab_*_t.html`
  - 注意：**文档只给字段顺序，不给枚举数值**；本内核的 token 数值与文档
    顺序在中间 3 张表不一致（见 §12.4），一切以探测为准。

### 12.2 RVA / 文件偏移换算

```text
pskernel.dll 段映射（objdump -h）：
  .text  VMA 0x180001000  FileOff 0x400
  .rdata VMA 0x183ED1000  FileOff 0x3ECFA00

公式：VA = ImageBase(0x180000000) + RVA
      FileOffset = RVA - 0x1000 + 0x400      （.text 内）
      FileOffset = RVA - 0x3ED1000 + 0x3ECFA00（.rdata 内）
```

示例：`PK_TOPOL_facet_2_r_f` RVA 0x44FCE0 → VA 0x18044FCE0；
`PK_TOPOL_facet_2` RVA 0x44DFA0 → VA 0x18044DFA0。

### 12.3 关键反汇编点位（已确认，勿重复挖掘）

| 位置（VA） | 内容 | 说明 |
|------|------|------|
| pskernel 0x180443550 | 选项转换器 | 对 `version-5..26` switch（22 项跳表）；把调用者 0x138..0x149 的 18 个 choice 字节拷入内部 0x1C8..0x1DF |
| pskernel 0x18044DFA0 | `PK_TOPOL_facet_2` 主体 | 面片生成入口，写 `PK_TOPOL_facet_2_r_t` |
| pskernel 0x18044FCE0 | `PK_TOPOL_facet_2_r_f` | 释放表；`fctab-0x57B2` switch（跳表在 0x18044FDF0，25 项） |
| pskernel 0x1804503FB..0x180451166 | 18 处 `mov [rax],0x57xx` | 写表 token 的顺序，仅能验证 token 集合，**不能**当名称映射 |
| pskernel 0x1813C4380 | 表校验函数 | 逐个 `cmp [rax],0x57xx` 提取 fin_fin/fin_data/facet_fin/data_point_idx/data_normal_idx 等 |
| pskernel .rdata 文件偏移 0x3F37840（≈RVA 0x3F38E40） | 表名字符串簇 | 旧名：`facet_fin, fin_fin, fin_vertex, vertex_point, vertex_normal, vertex_param, point_vec, normal_vec, param_uv, param_dp, param_d2p, facet_face, facet_occ, edge_fin, edge_occ, error_facet, ...`；新名从 0x3F37A88 起：`facet_topol, strip_face, strip_topol, fin_edge, point_topol, fin_topol, error_object, incr_faces`；0x3F37C20 起为 `table.<name>` 完整清单 |
| ParasolidGW 0x180120E33 | STpre 表解码器循环 | 只挑 `0x57B6/0x57B7/0x57BB/0x57C2` 四张表；0x57C2 按目标 face/edge 筛出 fin 后走 `fin_data→data_point_idx→坐标` |
| ParasolidGW 0x1801211EB | 坐标读取 | `point * 0x18 + [wrapper+0]`：**证明 24 字节坐标表就是 token 0x57BB** |
| ParasolidGW 0x18018B290 | `?PKTopol_facet_2_r_f@...` | 18 项 switch 的 free 包装，统一调 vtable+0xC0，无表级差异 |

### 12.4 V5 选项结构逐字段偏移（ctypes 实测）

`PK_TOPOL_facet_2_o_t` v5 = `_MeshControlV5`（312 字节）+ 18 个 choice 字节：

```text
control 偏移（_MeshControlV5，sizeof=312）：
 0x00 o_t_version        0x40 max_facet_sides     0x90 is_surface_plane_tol
 0x04 shape              0x44 is_min_facet_width  0x98 surface_plane_tol
 0x08 match              0x48 min_facet_width     0xA0 is_surface_plane_ang
 0x0C density            0x50 is_max_facet_width  0xA8 surface_plane_ang
 0x10 n_view_directions  0x58 max_facet_width     0xB0 is_facet_plane_tol
 0x18 view_directions*   0x60 is_curve_chord_tol  0xB8 facet_plane_tol
 0x20 cull               0x68 curve_chord_tol     0xC0 is_facet_plane_ang
 0x24 n_cull_transfs     0x70 is_curve_chord_max  0xC8 facet_plane_ang
 0x28 cull_transfs*      0x78 curve_chord_max     0xD0 is_local_density_tol
 0x30 n_loops            0x80 is_curve_chord_ang  0xD8 local_density_tol
 0x38 loops*             0x88 curve_chord_ang     0xE0 is_local_density_ang
                                                   0xE8 local_density_ang
 0xF0 n_local_tols       0x100 n_topols_with_local_tols
 0xF8 local_tols*        0x108 topols_with_local_tols*
                          0x110 local_tols_for_topols*
 0x118 ignore            0x120 ignore_value        0x128 ignore_scope
                         (double)                 0x12C wire_edges
 0x130 incremental_facetting  0x134 incremental_method
（0x138 起为 18 个 choice 字节，见 CAB_FORMAT_SPEC §5.2.1）
```

`PK_TOPOL_facet_2_r_t`（返回结构，20 字节）：

```text
0x00 number_of_facets(int)  0x04 number_of_strips(int)
0x08 number_of_fins(int)    0x0C number_of_tables(int)
0x10 tables*(PK_TOPOL_facet_table_t[])
```

`PK_TOPOL_facet_table_t` 每项 16 字节：`{fctab int, pad int, ptr qword}`；
`ptr` 指向 16 字节包装器 `PK_TOPOL_fctab_*_t = {void* data, int length}`。
**易错点**：`tables[i].ptr` 是包装器指针，`data` 在包装器首 qword；不要把
数据数组指针当包装器指针再解一次（本仓库早期 bug 即在此）。

### 12.5 表编码与组装链（含全部已知陷阱）

```text
组装链：facet → facet_fin → fin → fin_data → data → data_point_idx → point → point_vec → 坐标

facet_fin       8B {int facet; int fin}      查找表；三角面片每 facet 3 条连续记录
fin_data        4B int[]                    data[fin] = 数据索引
data_point_idx  4B int[]                    point[data] = 点索引
point_vec       24B {x,y,z} double[]         vec[point] = 坐标（token 0x57BB）
normal_vec      24B double[]                 单位法向量（token 0x57BC）
fin_edge        8B {int fin; PK_EDGE_t edge} token 0x57C2（实测语义，非 V35
                                             文档的 facet_face）；只收边界 fin，
                                             box 24 条 = 12 条边 × 2
strip_face      8B                           token 0x57C3，实测恒为空
```

陷阱清单（按踩坑顺序）：

1. **choice 偏移**：`point_vec=0x141 / normal_vec=0x142 / data_curv_idx=0x143`
   （与 V35 文档相反）。按文档置 `opts.point_vec=1` 实际打开的是 normal_vec。
2. **token**：坐标表是 **0x57BB**，法向量表 0x57BC，data_curv_idx 0x57BD；
   不要按“0x57B2 起顺序编号”猜测。
3. **索引表是 4 字节 int 数组**，不是 8 字节 pair；按 pair 解析 max 索引
   可达 26 亿导致越界崩溃。
4. **包装器 vs 数据指针**：`data[fctab]` 应存 `t.ptr`（包装器），再用
   `string_at(t.ptr,16)` 读 `(data*, length)`。
5. **point_vec 的 length 字段**：box 上真 point_vec len=8；曾误读的表 len=24
   （实为 data_curv_idx 位置的浮点数据）不是坐标。
6. **`-1` 洞环分隔符**：`shape=any` 时 facet_fin 中会出现 `fin=-1`，必须跳过；
   索引查表前做 0 <= idx < len 防御。
7. **同一进程单会话**：`PK_SESSION_start` 第二次调用返回 932；两模块需共享
   会话（ps_tessellate 已会复用 ps_facet2_nodes 的会话）。
8. **参数检查器**：`PK_SESSION_set_check_arguments(0)` 否则 5022。
9. **0x57C2 ≠ facet_face**：V35 文档把 0x57C2 叫 facet_face（facet→face 索引
   表），本内核实测是 fin_edge（`{fin, edge}` 查找表）。判别法：box 上
   facet_face 表 24 条记录的第二列与同进程 `PK_BODY_ask_edges` 的 12 个边 tag
   完全一致（每条边出现 2 次）；第一列是 fin 索引（每 facet 缺第 3 条 =
   面内对角线）。STpre 的 `PKFaces_RenderV3` 解码器用这张表按面/边收集 fins。

### 12.6 快速复现探测流程（30 秒定位“表不对”）

```python
import ctypes as C
from ctypes import byref, memset, c_int, c_void_p, POINTER, cast, string_at, sizeof
import struct
import ps_facet2_nodes as m
from pathlib import Path

sess = m._get_session()
tag = sess.receive_xt(Path('tests/box/_box_all.x_t').read_bytes())[0]
pk = sess.pk
pk.PK_TOPOL_facet_2.restype = c_int
pk.PK_TOPOL_facet_2.argtypes = [
    c_int, POINTER(c_int), c_void_p,
    POINTER(m._Facet2OptionsV5), POINTER(m._Facet2Result)]

# 1) 单 choice 探测：只置一个字节，看返回 token
for off in range(0x138, 0x14A):
    opts = m._Facet2OptionsV5(); memset(byref(opts), 0, sizeof(opts))
    opts.control.o_t_version = 5
    opts.control.max_facet_sides = 3
    opts.control.is_surface_plane_tol = 1
    opts.control.surface_plane_tol = 1e-4
    opts.control.is_surface_plane_ang = 1
    opts.control.surface_plane_ang = 12 * 0.017453292519943295
    (C.c_char * sizeof(opts)).from_buffer(opts)[off] = b'\x01'
    res = m._Facet2Result(); memset(byref(res), 0, sizeof(res))
    rc = pk.PK_TOPOL_facet_2(1, (c_int*1)(tag), None, byref(opts), byref(res))
    toks = []
    if rc == 0 and res.tables:
        tbl = cast(res.tables, POINTER(m._FacetTable * res.number_of_tables)).contents
        toks = [hex(t.fctab) for t in tbl]
    print(hex(off), toks, 'rc', rc)

# 2) 数据语义验证：dump 指定 token 的包装器 (data*, length) 与首元素
def wrapper(ptr):
    return struct.unpack_from('<Qi', string_at(ptr, 16))
# 例：0x57BB 应为 8 个 24B 向量（box 的 8 个角点）
# q0, ln = wrapper(tables[i].ptr); vec = string_at(q0, ln*24)
```

判定标准（对照 §12.8 基线）：

- rc=5022 → 先 `PK_SESSION_set_check_arguments(0)`；
- rc=932 → 进程已有会话，复用而不是新建；
- 返回 token 与 choice 映射不符 → 结构偏移错（核对 §12.4）；
- 三角形退化/越界 → 先看 point_vec 是否 0x57BB、索引表是否按 4B int 解析；
- 节点坐标是单位轴向量 → 拿到的其实是 normal_vec（0x57BC），choice 错了。

### 12.7 常见错误码速查

| 错误码 | 含义 | 处理 |
|------|------|------|
| 5022 | `PK_ERROR_o_t_version_incorrect` | `PK_SESSION_set_check_arguments(0)`（外部进程逆向调用时） |
| 932 | `PK_SESSION_start` 失败 | 同进程已有 pskernel 会话；共享会话对象 |
| 0x3A9B | 表校验失败（缺表组合） | 核对请求的 choice 组合是否合法（如 strip_face 需 strip_boundary/zigzag） |

### 12.8 验证基线数据（facet2 vs GO）

| 样例 | body | facet2 节点/三角形 | GO 节点/三角形 | 结论 |
|------|------|------|------|------|
| box | box | 8 / 12 | 8 / 12 | 坐标逐点一致（0..0.01 立方体） |
| tr03 | Case | 1573 / 3142 | 1600 / 3142 | 三角形数相同，节点更少（共享顶点去重） |
| tr03 | Impeller | 1030 / 2132 | 1030 / 2132 | 一致 |
| tr03 | Rotate | 102 / 200 | 102 / 200 | 一致 |
| ex4_e | 24 bodies | 全部生成 | 全部生成 | 三角形数全部一致 |

回归测试：`tests/test_ps_facet2_nodes.py`（3 项）覆盖 box 坐标、
tr03 与 GO 三角形数对照、cab_vtk 挂接与点法线。

## 13. 复杂大面三角化过粗分析与自适应预防（2026-08-05）

### 13.1 现象与量化

`PK_TOPOL_facet_2` 默认只设 `surface_plane_tol=1e-4`、
`surface_plane_ang=12°`（STpre 同源参数）。对曲率大的“复杂大面”，12° 角度
容差意味着面片法向摆动可达 ~11.3°（实测 `upper_cover_01` 每个 128-facet
曲面 max 面内二面角 = 11.29~11.48°，正好贴在容差上界），轮廓/高光处可见
明显棱线。

全局收紧容差的效果（`_ex4_e_all.x_t`，facet_2 直接调用）：

| body | 默认 12°/1e-4 | 6°/1e-4 | 4°/1e-5 |
|------|------|------|------|
| lower_cover_02（diag≈0.115） | 4664 | 9052 | 15332 |
| button（diag≈0.097） | 14538 | 48690 | 96138 |
| upper_cover_01（diag≈0.114） | 2808 | 7814 | 17952 |

结论：全局收紧能明显提升复杂面质量，但**小圆角/小曲面也全部加密**，button
4°/1e-5 直接爆到 9.6 万三角形，代价不可接受——必须按面/按局部自适应。

### 13.2 平滑度评价方法（二面角陷阱）

- 朴素“全网格相邻三角形最大二面角”在所有配置下都是 ~90°（甚至 180°）：
  跨 PK_FACE 的锐棱（台阶、倒角边）是真实几何，不是曲面粗糙度，会把信号
  完全淹没。**只统计同一 face 内相邻三角形**才有意义。
- 逐 face 度量方法：`PK_BODY_ask_faces` 拿 face tag → 对每个 face 单独调
  `PK_TOPOL_facet_2` → 解码后按共享边收集面内相邻三角形 → 取法向量夹角
  最大值。默认 12° 下曲面 face 该值 ≈ 11.3°；平面 face 为 0°（即使 facet
  很多，如 `lower_cover_02` 的 585/551-facet 大平面，max 二面角仍为 0）。

### 13.3 表语义纠错：token 0x57C2 是 fin_edge，不是 facet_face

为做按面分组，复查了 `PK_TOPOL_fctab_facet_face_t`。官方 V35 头文件说它是
“facet 索引 → PK_FACE 值”的索引表，但本内核 V5 的 0x57C2 实测是
**`{int fin; PK_EDGE_t edge}` 查找表**：

- box：24 条记录，第一列 = fin 索引 1,2,4,5,7,8,…（每个 facet 只含第 2、3 条
  fin；第 1 条 fin 是面内对角线），第二列 = 12 个互异值、每个出现 2 次；
- 同一进程 `PK_BODY_ask_edges` 返回 [59,82,87,91,95,97,99,101,103,105,107,110]，
  与表第二列完全一致；
- STpre 解码器（ParasolidGW 0x180120E33 起）从 0x57C2 按记录
  `[rcx+rax*8+4]`（即 edge tag）筛出 fin，再走 `fin_data→data_point_idx→
  坐标`，与“按面收集边界 fin”的用法吻合。

因此本内核 V5 选项块里**没有 V35 文档的 facet_face/facet_topol 表**；按 face
分组只能逐 face 调用 facet_2。文档已同步修正（CAB_FORMAT_SPEC §5.2.1/5.2.2、
§12.5 陷阱 9）。

### 13.4 原生局部容差机制（首选自适应方案）

`PK_facet_local_tolerances_t`（5 个 double：curve_chord_tol/max/ang、
surface_plane_tol/ang）可以挂到**单个/一组 PK_FACE 或 body** 上覆盖全局
容差；字段为 0 时继续沿用全局值。V5 `_MeshControlV5` 偏移：

```text
0xF0 n_local_tols            0x100 n_topols_with_local_tols
0xF8 local_tols*             0x108 topols_with_local_tols*
                             0x110 local_tols_for_topols*（下标数组）
```

实测生效性（`upper_cover_01`，全局保持 12°/1e-4）：

| 调用 | 三角形数 |
|------|---------|
| 全局 12°/1e-4（基准） | 2808 |
| body 级局部 4°/1e-5 | 17952（= 全局 4°，证明 body 级覆盖生效） |
| 仅 1 个大曲面 face 局部 4°/1e-5 | 3818（其余面保持 12°） |
| 仅 4 个大曲面 face 局部 4°/1e-5 | 6872 |

错误码速查：topol 不是 face/body → `PK_ERROR_unsuitable_topology`；
`local_tols_for_topols` 下标越界 → `PK_ERROR_bad_value`。

### 13.5 已实现的自适应算法（ps_facet2_nodes.py）

`tessellate_xt(..., adaptive=True)` / `facet_body_adaptive()`：

1. `PK_BODY_ask_faces` 取全部 face；
2. 每个 face 按基准容差（默认 12°/1e-4）单独 facet，度量
   `(facet 数, 面积, 面内最大二面角)`（见 §13.2）；
3. 选出「面内最大二面角 > 8° 且 面积 ≥ 1e-4×body 包围盒表面积 且
   facet ≥ 8」的 face——只挑又大又弯的复杂面；平面与小圆角不选；
4. 最后一次 body 级 facet_2 调用，对选中 face 挂局部容差
   `surface_plane_tol=1e-5、surface_plane_ang=6°`（默认，均可配置）。

默认参数：`refine_angle_deg=6.0`、`refine_tol=1e-5`、`smooth_angle_deg=8.0`、
`min_rel_area=1e-4`、`min_face_facets=8`。GUI 加载已默认开启 adaptive；
库函数默认关闭（保持与 STpre/GO 计数一致的既有回归不变）。

实测（ex4_e / tr03 / box）：

| 样例 | body | 基准三角形 | adaptive 三角形 | 耗时 |
|------|------|------|------|------|
| ex4_e | upper_cover_01 | 2808 | 11018 | ~0.18s |
| ex4_e | lower_cover_02 | 4664 | 10068 | ~0.28s |
| ex4_e | button | 14538 | 23120 | ~0.70s |
| tr03 | Case | 3142 | 16530 | ~0.5s |
| tr03 | Impeller | 2132 | 2764 | — |
| tr03 | Rotate | 200 | 200（无复杂面） | — |
| box | box | 12 | 12（平面，不变） | — |

### 13.6 其他可用的自适应/预防措施（按优先级）

1. **逐 face 分次 facet + 坐标合并**：facet 的 topol 参数直接传 face tag，
   每个 face 可用自己的容差/参数；`match=topol` 保证共享边顶点重合，合并按
   坐标去重即可。当前实现用“探测 face + 一次 body 局部容差调用”，免去合并，
   是同一思路的更优落地。
2. **全局默认 12° → 8°/6°**：简单粗暴；代价是小圆角也加密（button 6° 已
   4.9 万三角形）。可配合 `ignore` 忽略小特征使用。
3. **后处理曲率监督细分**：输出后对“面内二面角超阈值”的区域做
   Loop/midpoint 局部细分；只能让着色更平滑，不提高对原始曲面的几何拟合
   （不如内核局部容差）。可用 `normal_vec` 表（0x57BC）做无拓扑细分的
   法向插值。
4. **`density` 选项**：按视图方向加密，需 view matrix；静态装配/离屏渲染
   不适合。
5. **`curve_chord_tol/curve_chord_max` 与 `max_facet_width`**：补充大半径
   边缘的弦向精度；STpre 的 `PKFaces_RenderV3` 会按 body 尺寸缩放 chord
   容差，本仓库目前只显式设置了 surface 两个容差。
6. **`ignore` 小特征**：与自适应互补——先忽略纳米级圆角/倒角降面，再把
   预算留给大曲面。

### 13.7 回归与文档

- 全仓 `pytest`：**64 通过 / 3 跳过**（新增 2 项自适应测试：tr03 复杂面
  必须细化且不减面、box 平面保持不变；另有 face 度量健全性断言）。
- 文档同步：CAB_FORMAT_SPEC §5.2（0x57C2=fin_edge 纠错）与新增 §5.3
  （局部容差结构与自适应调用方式）；本节约 §13.1–13.6。

## 14. M1：File→Import x_t 导入实现（2026-08-06）

### 14.1 设计决策：独立 x_t 成员，不做字节级拼接

STpre 的 cab 用一个 `_<project>_all.x_t` 承载全部 body。直接“把导入文件的
原始字节追加到该成员”会得到多个 PART1 头/T51 记录拼接的非法传输流，
`PK_PART_receive` 无法解析。因此 M1 采用：

1. 每个导入的 `.x_t` 文件**原样**作为新 cab 成员保存：
   `<project>_import_0001.x_t`、`_0002.x_t` …（`cab_import.add_xt_member`）；
2. `ex4_e.xml` 的 `<body_files>` 追加 `<file type="xt">` 引用
   （`StpreModel.add_body_file`，幂等）；
3. GUI 加载时**遍历全部 `.x_t` 成员**逐个 `PK_PART_receive` 并三角化，
   导入部件因此能保存/重开一致；
4. 每个 body 注册为 `<parts type="body">`（`StpreModel.add_part`），字段
   布局对齐 ex4_e 官方样式（name/name2/property/attribute/volume/color/
   mode/visible_count/tree_expand/layer/monitor/rad_group_num/
   heat_balance/VF_balance/facet_kind/def_axis/file/transform）。

### 14.2 新增/修改代码

- `cab_import.py`（新）：`ImportedBody`、`import_xt_bytes()`、
  `import_xt_file()`、`add_xt_member()`、`register_parts()`、`available()`。
  导入走共享 pskernel 会话，三角化默认 `adaptive=True`（facet_2 表路径 +
  每 face 局部容差），失败时可关。
- `cabxml.py`（扩展）：`StpreModel.body_files()` / `add_body_file()` /
  `add_part()`；新元素 text/tail 空白按 ex4_e 缩进风格设置，兼容字节稳定
  序列化器。
- `cab_gui.py`：`load()` 改为遍历所有 `x_t` 成员（facet_2 与 GO 两条路径
  都循环）；File→Import… 菜单与 File 工具栏 Import 按钮接入
  `_import_dialog()`：选文件 → 导入/三角化 → 追加成员 → 注册部件 →
  刷新树与 3D → 置脏。

### 14.3 验证

- `tests/test_import.py`（3 项）：
  - box x_t 导入 → 1 body、8 节点/12 三角形；
  - 追加成员 + `body_files` 幂等 + `add_part` 序列化重解析 + cab 重打包
    往返（成员数 +1）；
  - GUI 加载含两个 x_t 成员的 cab → 两个成员都被三角化、树含导入部件。
- 全仓 `pytest`：**74 通过 / 4 跳过**。

后续（M2+）在 `body_files` 基础上扩展：部件 `<file>` 引用可细化到具体
成员名；导入对话框二期支持 STL/MDL/DXF（`ImportStlFile` 等入口已定位，
见 DEV_PLAN §3.2）。

## 15. M2：计算域设置实现（2026-08-06）

### 15.1 数据与语义

- 域数据在 `<analysis_region type="cube">`：`<base unit="mm">` +
  `<size unit="mm">`（min = base，max = base + size），`<property>` 为域材料；
- 六个边界 `face_list` region（Ymin=1/Xmax=2/Ymax=3/Xmin=4/Zmin=5/Zmax=6）
  必须保留——`set_domain_geometry` 只改 base/size/property；
- 无域项目（如新建工程）用 `ensure_domain` 创建完整 cube 域 + 六个
  face_list region。

### 15.2 新增/修改代码

- `cabxml.py`：`domain_base()/domain_size()/domain_unit()/
  domain_material()/set_domain_geometry()/set_domain_material()/
  ensure_domain()`；
- `cab_domain.py`（新）：`DomainSpec`（coordinate/unit/min/max/material/
  extend/auto_y）、`domain_from_xml()`、`apply_domain()`、
  `part_bounds()`（对 tess 应用 XML 列主序 transform 求世界坐标包围盒）；
- `cab_gui.py`：`_DomainDialog`——坐标系/单位（mm/m/cm 换算）/六轴 min-max/
  域材料/CAD Data Size（取部件包围盒）/Extend surroundings/轴向 Y 自动/
  Preview（应用+刷新，不关闭）/OK 写回置脏/Cancel 回退原域；Edit→Reset
  Computational Domain 菜单接入。

### 15.3 验证

- `tests/test_domain.py`（5 项）：ex4_e 域读取（base/size/material）、
  修改后序列化重解析、face_list 保留、无域创建、box 包围盒（0..0.01 m →
  对话框 mm 显示 0..10）、对话框 smoke（CAD Data Size + Preview + Revert）。
- 全仓 `pytest`：**79 通过 / 4 跳过**。

## 16. M3：Gridding 实现（2026-08-06）

### 16.1 算法与 XML

- `cab_grid.py`（新）：`GridSpec`、`rough_grids()`（顶点检测
  all/representative/axis_plane/minmax/not_considered/uniform）、
  `refine_grids()`（标准长度 + 几何比内/外部、threshold 下限）、
  `_target_counts()`（按目标单元数反推各轴点数）、`build_axes()`；
- `cabxml.StpreModel.set_mesh()`：写 `mesh_control`（RootBlock 的
  min/max/limit/grid/subblock、select_vertex/divide_method/divide_ratio2/
  outer_range/element_max 等）与 `mesh_block`（x/y/z 坐标表，首末点 `B`
  标记），结构对齐 ex4_e 官方 XML；
- GUI `_GriddingDialog`：顶点检测/网格化方法/标准长度/阈值/几何比
  （内外部）/目标单元数；应用后 `_rebuild_scene()` 预览网格线并置脏。

### 16.2 一期近似（已记录，待黄金对拍）

- `representative` 与 `axis_plane` 暂时分别用 `all`/`minmax` 的顶点集近似；
- `num_elements` 模式按各轴长度比例均匀分布（不叠加粗网格顶点）；
- 圆柱/轴对称坐标系的 R/θ 网格生成未实现，仍按笛卡尔处理。

### 16.3 验证

- `tests/test_grid.py`（6 项）：minmax/all/uniform/not_considered 粗网格、
  几何比单调性与阈值、目标单元数换算、`set_mesh` 序列化重解析（grid 数、
  mesh_axes 一致）、Gridding 对话框 smoke。
- 全仓 `pytest`：**85 通过 / 4 跳过**。

## 17. M4：Meshing 实现（2026-08-06）

### 17.1 算法

- `cab_mesh.py`（新）：
  - `classify_part_cells()`：以 `mesh_block` 单元中心为射线原点，对每个
    部件的三角化曲面做 **+X 偶数-奇数射线判定**（每三角形只处理其 yz 投影
    包围盒覆盖的单元切片，`numpy` 向量化）；
  - 射线恰好穿过三角形共享边时两个三角形都会命中导致奇偶翻转——对射线
    原点加 `1e-11/2e-11 × 域尺度` 的扰动，保证共享边只被一个三角形计数
    （box 全域 10³ 单元从 940 修正到 1000）；
  - `_merge_boxes()`：占用单元按 i 行程 + j/k 邻接贪心合并为轴对齐盒；
  - `classify_cells()`：部件 bbox 预过滤 + 逐部件判定，返回 Domain
    `<analysis>` 盒与各部件盒表；
  - `apply_elements()`：写 `<element>`（1-based 闭区间
    `i1,i2,j1,j2,k1,k2,0,1,1`），替换旧 `<element>`。
- `cab_gui._meshing_dialog()`：Mesh→Meshing 执行入口；状态栏进度；
  完成后刷新 3D（Element division 显示）并置脏。进度用状态栏而非模态
  QProgressDialog（offscreen 下模态框会阻塞）。

### 17.2 一期限制（待黄金对拍）

- 表面单元以 epsilon 判定，未做 STpre 的精确 cut-cell 表面处理；
- panel/sheet（开放曲面）未特殊处理（奇偶法只适用于封闭体）；
- 盒表合并是贪心近似，不是 STpre 的精确行程编码。

### 17.3 验证

- `tests/test_mesh.py`（5 项）：box 全域/子集占用（含共享边扰动修正）、
  `apply_elements` 序列化重解析、盒合并、Meshing 对话框 smoke。
- 全仓 `pytest`：**90 通过 / 4 跳过**。

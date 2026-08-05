# CAB 项目文件格式说明（scSTREAM Pre，逆向工程）

> 目标：完整描述 Cradle scSTREAM Pre 项目文件 `.cab` 的容器与全部成员格式，
> 支撑「逆向解析 / GUI 元数据编辑 / 导出 `.s` 与 `.xemt`」三条核心能力。
>
> 分析样例：`tests/ex4_e.cab`（244,000 B）+ 官方导出对拍件
> `tests/ex4_e.s`（48,571 B）/ `tests/ex4_e.xemt`（2,267 B）。
> 补充样例：`tests/box.cab`、`tests/tr03.cab`（2025.2，无 `element`
> 网格、嵌套 `<group>`）。
> 样例版本：scSTREAM V2023.2（STpre SDK 1623.20302.20231027），
> Parasolid modeller version 3401153（SCH_3401153_34101_1300）。

---

## 1. 总体概览

`.cab` 是 **Microsoft Cabinet（MSCF）归档容器**（不是 ZIP），魔数 `MSCF`。
解包后得到 3 个成员（与官方 [File]-[Export] 的 Default File / Property File /
XT File 一一对应）：

| 成员（存储顺序） | 未压缩大小 | 角色 | 格式 |
|------|-----------|------|------|
| `ex4_e.xml` | 104,926 B | 项目定义（全部前处理设置） | XML，UTF-8 BOM（`<stpre>`，见 §3） |
| `_ex4_e_property.xml` | 69,987 B | 基础材料属性库 | XML，UTF-8 BOM（`<property>`，见 §4） |
| `_ex4_e_all.x_t` | 802,665 B | Parasolid 几何（当前放置的全部 parts） | Parasolid 文本传输流（见 §5） |

> 成员名前缀规则：项目名 `ex4_e`；`_ex4_e_property.xml` / `_ex4_e_all.x_t`
> 带下划线，`ex4_e.xml` 不带。`ex4_e.xml` 内 `<property_db>/<file>`
> 与 `<body_files>/<file>` 显式引用另外两个成员名。

`.s`（SDAT，STsolver 输入）与 `.xemt`（EMT 材料/部件映射）是 Pre 导出文件：
手册 [File]-[Export] 明确「[S File] Current status is output to S file of
STsolver」；EMT 说明为「EMT file (*.xemt), which is output from Pre
automatically when S file is exported, stores the information about
relationship between part name, material name, region name」。
两者的全部数据源都在 cab 成员内（见 §6/§7），因此可从 cab 无损重建。

---

## 2. 容器格式：Microsoft Cabinet（MSCF）

### 2.1 文件头 CFHEADER（本样例 44 字节，含 8 字节 CFFOLDER）

实测字节（hex）与字段：

```
000000  4d 53 43 46  00 00 00 00  20 b9 03 00  00 00 00 00
000010  2c 00 00 00  00 00 00 00  03 01 01 00  03 00 00 00
000020  39 30 00 00  89 00 00 00  1e 00 01 00
```

| 偏移 | 长度 | 值 | 含义 |
|------|------|-----|------|
| 0 | 4 | `MSCF` | 签名 |
| 4 | 4 | 0 | 保留 |
| 8 | 4 | 0x0003B920 = 244,000 | cbCabinet（= 文件总长，LE u32） |
| 12 | 4 | 0 | 保留（标准中为 cbReserveCFHeader） |
| 16 | 4 | 44 | coffFiles（首条 CFFILE 的绝对偏移） |
| 20 | 4 | 0 | 保留零（见下方陷阱） |
| 24 | 1 | 3 | 观测 versionMinor |
| 25 | 1 | 1 | 观测 versionMajor |
| 26 | 2 | 1 | cFolders |
| 28 | 2 | 3 | cFiles |
| 30 | 2 | 0 | flags（无保留区、无预压缩等） |
| 32 | 2 | 0x3039 = 12345 | setID |
| 34 | 2 | 0 | iCabinet |
| 36 | 8 | 见 2.2 | CFFOLDER[0] |
| 44 | — | 见 2.3 | CFFILE 表 |

> **解析陷阱**：标准 [MS-CAB] 在偏移 20 依次放置 versionMinor(1)/versionMajor(1)/
> cFolders(2)/cFiles(2)/flags(2)/setID(2)/iCabinet(2)。本样例偏移 20–23 为 4 个
> 零字节，真实版本/计数整体后移 4 字节（也可能 coffFiles 按 8 字节 u64 存储，
> 值同为 44）。**不要**按标准字段位置解析，直接读 cFiles 并迭代 CFFILE 即可；
> Windows `expand` 可正常解包，说明微软侧兼容此布局。

### 2.2 CFFOLDER（8 字节）

| 偏移 | 长度 | 值 | 含义 |
|------|------|-----|------|
| 36 | 4 | 137 | coffCabStart（首条 CFDATA 绝对偏移） |
| 40 | 2 | 30 | cCFData（CFDATA 块数） |
| 42 | 2 | 1 | typeCompress = **MSZIP** |

单文件夹，压缩类型 1（MSZIP）。文件夹解压后的完整流（下文简称“文件夹流”）
按成员顺序存放全部成员数据。

### 2.3 CFFILE（16 字节固定 + NUL 结尾文件名）

字段（LE）：`cbFile u32` + `uoffFolderStart u32` + `iFolder u16` +
`date u16`（MS-DOS 日期）+ `time u16`（MS-DOS 时间）+ `attribs u16` +
`szName`（ASCII，`\0` 结尾）。

实测三条记录：

| 成员 | CFFILE 偏移 | cbFile | uoffFolderStart | iFolder | date | time | attribs | 名称偏移 |
|------|-----------|--------|-----------------|---------|------|------|---------|---------|
| ex4_e.xml | 44 | 104,926 | 0 | 0 | 0x575F | 0xA32D | 0x00A0 | 60 |
| _ex4_e_property.xml | 70 | 69,987 | 104,926 | 0 | 0x575F | 0xA32D | 0x00A0 | 86 |
| _ex4_e_all.x_t | 106 | 802,665 | 174,913 | 0 | 0x575F | 0xA32D | 0x00A0 | 122 |

日期时间解码验证：`0x575F` → 1980+(0x575F>>9)=2023 年，(0x575F>>5)&0xF=10 月，
&0x1F=31 日（2023-10-31）；`0xA32D` → 20:25:26，与 XML 头注释
`2023/10/31 20:25:25` 一致。三条记录时间戳相同。

> 三条 `uoffFolderStart` 均为精确连续值（0 / 104,926 / 174,913 =
> 104,926+69,987），文件夹流总长 977,578 B = 三成员之和，无间隙。
> 提取仍按顺序累加 cbFile 定位、以成员魔数（XML BOM、`**`+Parasolid 头）
> 校验，便于将来兼容其他变体。

### 2.4 CFDATA 与 MSZIP 载荷

#### 2.4.1 CFDATA 块头（本格式 8 字节，非标准 12 字节）

```
u32 csum      LE 校验和（算法未验证，工具可忽略）
u16 cbData    本块压缩字节数（含 2 字节 'CK'）
u16 cbUncomp  本块解压字节数（≤ 32768，末块可为余数）
payload       2 字节 'CK' 标记 + raw DEFLATE 流（RFC1951）
```

> 标准 [MS-CAB] 为 `csum u32 + cbData u32 + cbUncomp u32`；本格式两块长度
> 均为 u16（块头共 8 字节）。30 个块从头到尾精确覆盖文件（末块结束偏移 =
> 文件总长），且每块头后紧跟 `CK`，实证该布局。

#### 2.4.2 跨块 LZ77 历史

MSZIP 块之间**共享 32KB 滑动窗口**：后一块的 DEFLATE 引用可回溯到前一块
解压输出。逐块独立 `zlib.decompress(..., -15)` 会在非首块报
`invalid distance too far back`。Python 解法：

```python
out = b""
for i, blk in enumerate(blocks):
    dec = zlib.decompressobj(-15, zdict=out[-32768:]) if i else zlib.decompressobj(-15)
    out += dec.decompress(blk[2:])   # blk = 'CK' + deflate
```

验证：30 块全部解压成功，总长 977,578 B；三个成员切片与 `expand` 提取件
逐字节一致（md5 全同）。

#### 2.4.3 实测块统计

首块：csum=`0xEC6E6584`，cbData=3,234，cbUncomp=32,768；首块解压内容为
UTF-8 BOM + `<?xml version="1.0"...`。末块解压长度为 27,818（余数）。平均
压缩比约 4 倍（几何 x_t 部分占比大）。

---

## 3. 成员 1：`ex4_e.xml` — 项目定义（scSTREAM XML）

UTF-8 BOM。文件头注释：

```xml
<!-- scSTREAM V2023.2 -->
<!-- user : pre -->
<!-- Version : 1623.20302.20231027 -->
<!-- date/time : 2023/10/31 20:25:25 -->
<stpre>
```

根元素 `<stpre>`，顶层章节（按出现顺序）：

| 章节 | 内容 |
|------|------|
| `version` | `no="2023.2"`，module（Standard）、release（20230901） |
| `property_db` | 属性库文件名 `_ex4_e_property.xml` |
| `unit` | 43+ 个物理量显示单位（display=mm、geometry=m、velocity=m/s…） |
| `project` | 项目名、注释、cxyz_scale、precision、ambient_temperature、treeview 状态等 |
| `body_files` | 几何文件引用：`<file type="xt">_ex4_e_all.x_t</file>`（unit=m） |
| `analysis_region` | 计算域（type=cube）：name/base/size/color/property + 6 个 face_list 边界 region（Xmin…Zmax，face 编号 1–6） |
| `group` | 部件组（cellular_phone）：layer、可见性、heat_balance + 全部 `<parts>` |
| `region` | 未定义边界（Undefined(Stress/Heat/Radiation)…，含 seq_no） |
| `table` | 表格（pq-curve0 等） |
| `analysis_set` | 求解设置：type=incompressive、fluid=7、heat=1、turbulence、grav、cycle、calculation、courant、辐射（vf）、fluid_region、文件组 `<file>`（.s/.r/.vf/…）、cutcell 参数 |
| `output` | 输出控制：fld_file、fout（HTRC/SURT/HTFX）、restart、minmax、list、fan_ocon 等 |
| `steady_param` | 稳态参数（under_relax、inertia_relax） |
| `value` × N | 命名条件值（flux/initial/wall/heat_transfer/radiation_boundary/heat_source 等，如 Flux1、HeatSource1） |
| `condition` × N | 条件绑定：`<analysis>/<region>/<parts>` + `<value>` 名 |
| `mesh_control` | 网格控制：RootBlock（min/max/grid=99,243,63、divide 等） |
| `mesh_block` | **网格坐标表**：`<x num="99">`/`<y num="243">`/`<z num="63">` 各含 `<g no>` 坐标（单位 mm，`B`=边界、`N`/`S`=相邻段标记）——即 `.s` 的 CXYZ 数据源 |
| `element` | **部件体/面盒表**：`<analysis name="Domain(cuboid)">` 的 body/face list 与每个 `<parts name>` 的 body list（`i1,i2,j1,j2,k1,k2,0,1,1`）——即 `.s` 的 PARTS 数据源 |
| `draw_control` / `draw_scene` | 绘图控制与场景（eye/target/up/window/projection/frame） |
| `condition_wizard` | 向导状态位 |
| `state` | element_execute |
| `color` | 全部显示配色 |

### 3.1 `<parts>` 关键子元素（部件元数据编辑目标）

`<group>/<parts type="body|cube">`：

- `name` / `name2`：部件名（body 型带 name2）
- `property`：材料名（对应 `_ex4_e_property.xml` entry 与 `.xemt` mat）
- `attribute`：solid 等
- `volume`（unit=m）、`color`（RGBA）、`layer`、`visible_count`、`monitor`
- `facet_kind`、`def_axis`
- `file`（unit=m）：`x_t`（body 型引用几何文件）
- `transform`（unit=m）：4×4 齐次变换矩阵（16 个逗号分隔值，**列主序**
  存储；平移位于第 13–15 个分量，1-based）。按字符串顺序 reshape 成 4×4
  数组后，以 `hom @ m` 应用）
- cube 型另有 `base`/`size`（unit=mm）、`locate`

`<group>` 可嵌套（如 tr03：`tr03 → tr02`），部件可出现在任意层级；未生成
网格时 XML 可以**没有 `<element>` 章节**，部件几何仅由 `.x_t` body +
`<transform>` 提供。也允许 `<parts>` 直接位于 `<stpre>` 根下、不包在任何
`<group>` 中（如 box.cab）。

`draw_control` 中与 3D 显示相关的关键开关：`parts_draw_type=shade` 对应
Part 实体着色；`parts_facet=F` 表示不叠加 CAD 面片边；`mesh_element=T`
对应 Element division 网格盒线。

### 3.2 编辑语义

`ex4_e.xml` 为**标准 XML**（无索引标签陷阱，ElementTree 可直接解析/序列化，
注意保留 UTF-8 BOM 与注释头）。它是 GUI 元数据编辑的主载体：部件名、
材料、颜色、层、变换、边界条件值、求解参数均可改后写回并重打包。

---

## 4. 成员 2：`_ex4_e_property.xml` — 基础材料属性库

UTF-8 BOM。结构：

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<!-- property table -->
<!-- date/time :  Tue Oct 31 20:25:25 2023 -->
<property>
  <group>
    <type> fluid </type>
    <name> gas(incompressible) </name>
    <entry>
      <name> air(incompressible/20C) </name>
      <density> 1.206 </density>
      <ref_density> 1.206 </ref_density>
      <ref_temperature unit="C"> 20 </ref_temperature>
      <viscosity> 1.83e-05 </viscosity>
      <capacity> 1007 </capacity>
      <conductivity> 0.0256 </conductivity>
      <expansion> 0.003495 </expansion>
      <radiation field="T"> <absorption> 0 </absorption> <scattering> 0 </scattering> </radiation>
      <surf_tension> 0 </surf_tension>
    </entry>
    ...
```

- 顶层：`<property>` > 多个 `<group>`（type=fluid/gas/solid/…，name 如
  `gas(incompressible)`）> 多个 `<entry>`（一个具体材料）。
- entry 内物性键：density / ref_density / ref_temperature / viscosity /
  capacity / conductivity / expansion / radiation / surf_tension 等。
- 材料 `mat no="1".."7"`（`.xemt`）与 `.s` 的 `PROPERTY` 段、本 XML 的 entry
  一一对应（如 no=1 ↔ `air(incompressible/20C)` ↔ `.s` 材料 1）。

---

## 5. 成员 3：`_ex4_e_all.x_t` — Parasolid 文本传输流

纯文本（无 BOM，`\r\n` 行尾）。头部：

```
**ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789**************************
**PARASOLID !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~0123456789**************************
**PART1;
MC=unknown;
MC_MODEL=unknown;
MC_ID=unknown;
OS=Windows;
OS_RELEASE=7 later;
FRU=Software Cradle Co.Ltd.;
APPL=STREAM V2023;
SITE=Osaka Japan;
USER=unknown;
FORMAT=text;
GUISE=transmit;
KEY=C:\...\_ex4_e_all.x_t;
FILE=C:\...\_ex4_e_all.x_t;
DATE=2023/10/31(Tuesday)
**PART2;
SCH=SCH_3401153_34101;
USFLD_SIZE=0;
**PART3;
**END_OF_HEADER*****************************************************************
T51 : TRANSMIT FILE created by modeller version 340115323 SCH_3401153_34101_1300
6231 0 176 6 14 PART_XMT_BLOCK9 Part list9 n_entries0 0 1 d16 index_map_offset0 ...
```

要点：

- `**PART1` 属性行（`MC`/`FRU`/`APPL`/`SITE`/`KEY`/`FILE`/`DATE`）是
  元数据编辑的可读入口。
- `**PART2` 给出 `SCH=SCH_3401153_34101`；T51 行给出完整 schema
  `SCH_3401153_34101_1300` 与 modeller version `340115323`。
- 后续为 `**PART3` 起的传输记录（T51 schema 字段表、PKEdge/PKFace/PKVertex
  实体、SDL 属性）。**完整 B-rep 拓扑还原依赖 Parasolid 内核，本仓库沿用
  `pphdecoding/parasolid.py` 的「部分提取」路线**（schema / 字段名 /
  实体类型 / SDL 属性），满足轻量交互与元数据查看。

### 5.1 Parasolid 曲面显示与 GO 面片化（2026-08-04）

显示级曲面不再依赖手工解析 B-rep，而是调用 Cradle 自带
`Programs_x64/pskernel.dll`：

1. `PK_PART_receive` 接收 `.x_t` 全部 body（本样例 24 个）；
2. 对每个 body 调 `PK_TOPOL_render_facet`，通过 GO `GOSGMT` 回调收集面片；
3. 实测面片段 `segtyp=2016`（SGTPFT），`lntp=[occ, 3007, 1, 3]`，即
   `L3TPFV` 单环三角形；解析为 `TessPart.points / triangles`。

`body_name` 读取 `SDL/TYSA_NAME` 属性时只采用**可打印 ASCII**；`box.cab`
的同类属性列表中含非字符串脏字节（如 `b'\xd6\xd7\xd7'`），旧逻辑会把它
解码成替换字符并抢先成为最长名称，现已过滤，保证真实 body 名 `"box"` 能
与 XML `<parts>/<name>` 匹配。

`PK_TOPOL_render_facet` 选项结构为
`PK_TOPOL_render_facet_o_t = control(PK_TOPOL_facet_mesh_o_t) + go_option`：

- x64 下 `control` 为 368 字节，`go_option` 紧随其后；旧实现曾按第 200
  字节写 `go_option` 版本号，字段会错位，现改为完整 ctypes 结构体。
- 零选项时 Parasolid 使用内核内部容差，曲率面片过粗；现在显式设置
  `is_surface_plane_tol=1` / `surface_plane_tol=1e-4` 与
  `is_surface_plane_ang=1` / `surface_plane_ang=12°`。

`.x_t` 中 body 为**局部坐标**，装配位置由 `ex4_e.xml` 的
`<parts>/<transform>` 提供（4×4 **列主序**）。GUI 组装流程：

```text
x_t body ──PK_PART_receive──▶ PK_TOPOL_render_facet ──GO──▶ TessPart
    │                                                        │
    │                                            XML <transform> 列主序变换
    ▼                                                        ▼
part_boxes ─────────────▶ attach_cad_meshes ──▶ vtkPolyData（点法线 + 45°锐边拆分）
```

渲染层：`vtkCleanPolyData` 合并重复顶点，`vtkPolyDataNormals` 生成点法线
（Gouraud），`SetFeatureAngle(45)` 保留硬棱边。实测 ex4_e：默认 9,826 个
三角形 → 25,006 个；`lower_cover_01` 由 790 → 2,110 个；24/24 个 body 均带
法线，变换后 CAD 包围盒与 XML `element` 网格盒一致。

对于尚未生成 `element` 网格的项目（如 tr03），`part_boxes()` 不再预先丢弃
无网格盒的 body 部件：只要存在同名 Parasolid body，就先保留占位并在 CAD
挂接成功后显示 x_t 曲面；没有 CAD 的占位项会被清理。

### 5.2 `PK_TOPOL_facet_2` 表格化面片（STpre 节点生成路径）逆向（2026-08-04）

scSTREAM Pre 实际生成显示节点走的是 **表格化面片** 路径，而不是 GO 回调：

```text
STpreBase_Bx64.dll
  ?MakeFacet@PreBody@@QEAAHHPEAVFacetParam@@@Z        RVA 0x293A20
  ?MakeFacetParam@PreBody@@QEAAPEAVFacetParam@@QEAN@Z RVA 0x293C20
      |
      v
ParasolidGW_Bx64.dll
  ?PKBody_GetTriangles@LocalParasolid@@...            RVA 0xA49A0 等
  ?PKFaces_RenderV3@LocalParasolid@@...               RVA 0x1415C0 / 0x141850
      |  （填充 PK_TOPOL_facet_2_o_t 后经 vtable+0x1C50 调内核）
      v
pskernel.dll
  PK_TOPOL_facet_2                                    RVA 0x44DFA0
  PK_TOPOL_facet_2_r_f                                RVA 0x44FCE0
```

独立脚本 [ps_facet2_nodes.py](ps_facet2_nodes.py) 用纯 ctypes 复现该路径，
可直接对任意 `.x_t` 生成 `TessPart`（点/三角形）：

```text
python ps_facet2_nodes.py tests/box/_box_all.x_t            # 8 节点 / 12 三角形
python ps_facet2_nodes.py --obj out.obj tests/tr03/_tr03_all.x_t
```

#### 5.2.1 V5 选项结构布局（反汇编 pskernel RVA 0x443550）

`PK_TOPOL_facet_2_o_t` 的 version-5 布局为 **312 字节 mesh control 块 +
18 个连续 choice 字节**（0x138..0x149）。逐字节单开探测得到本内核的真实
choice 偏移（注意：**与 V35 文档顺序不同**，文档把 `data_curv_idx` 放在
`point_vec/normal_vec` 之前，本内核恰好相反）：

| choice 偏移 | 表 | token |
|------|------|------|
| 0x138 | facet_fin | 0x57B2 |
| 0x139 | strip_boundary | 0x57B3 |
| 0x13A | strip_zigzag | 0x57B4 |
| 0x13B | fin_fin | 0x57B5 |
| 0x13C | fin_data | 0x57B6 |
| 0x13D | data_point_idx | 0x57B7 |
| 0x13E | data_normal_idx | 0x57B8 |
| 0x13F | data_param_idx | 0x57B9 |
| 0x140 | data_deriv_idx | 0x57BA |
| **0x141** | **point_vec** | **0x57BB** |
| **0x142** | **normal_vec** | **0x57BC** |
| **0x143** | **data_curv_idx** | **0x57BD** |
| 0x144 | param_uv | 0x57BE |
| 0x145 | deriv_dp | 0x57BF |
| 0x146 | deriv_d2p | 0x57C0 |
| 0x147 | curv_dirs | 0x57C1 |
| 0x148 | **fin_edge**（实测语义，非 V35 文档的 facet_face） | 0x57C2 |
| 0x149 | strip_face | 0x57C3 |

结论的三种交叉验证：

1. **单 choice 探测**：只置 0x141 返回 token 0x57BB，只置 0x142 返回
   0x57BC，只置 0x143 返回 0x57BD。
2. **数据语义**：0x57BB 在 box 上返回 8 个 24 字节向量，恰为
   `(0,0,0)~(0.01,0.01,0.01)` 立方体 8 角点，与 GO 路径逐点一致；
   0x57BC 返回 6 个单位法向量（±X/±Y/±Z），与 `data_normal_idx` 最大值 5 吻合。
3. **STpre 自身解码器**：ParasolidGW `PKBody_GetTriangles` 内循环只挑
   `0x57B6/0x57B7/0x57BB/0x57C2` 四张表，其中按 `point*0x18` 步长读坐标的
   正是 token 0x57BB 的表——即 STpre 眼中的“坐标表”。

#### 5.2.2 表编码（V35 header `pk_topol_fctab_*_t`）

`PK_TOPOL_facet_2_r_t.tables[]` 每项 16 字节：
`{ fctab(int), pad(int), ptr(qword) }`，`ptr` 指向 16 字节包装器
`{ void* data; int length; }`（`PK_TOPOL_fctab_*_t`）。

| 表 | 元素 | 说明 |
|------|------|------|
| facet_fin | 8B `{int facet; int fin}` | 查找表，三角面片每 facet 3 条连续记录 |
| fin_data | 4B int 数组 | `data[fin] = 数据索引` |
| data_point_idx | 4B int 数组 | `point[data] = 点索引` |
| point_vec | 24B `{x,y,z}` 向量 | `vec[point] = 坐标` |
| normal_vec | 24B 向量 | 单位面法向量 |
| fin_edge（token 0x57C2） | 8B `{int fin; PK_EDGE_t edge}` | **本内核 0x57C2 不是 V35 文档的 facet_face**；实测为“边界 fin → 模型边”查找表：只收录每个三角面片落在模型边上的 2 条 fin（每个 facet 的第 3 条 fin 是面内对角线，不在表中），box 上 24 条记录 = 12 条边 × 每条边 2 次出现，第二列与同进程 `PK_BODY_ask_edges` 返回的 12 个 PK_EDGE tag 完全一致 |
| strip_face（token 0x57C3） | — | 实测恒为空（本调用组合 `max_facet_sides=3` + 默认 shape 不产生 strip） |

> **注意**：V35 文档中的 `facet_face`（facet → face 的索引表）与 `facet_topol`
> 在本内核 V5 选项块（0x138..0x149 共 18 个 choice）中**不可达**。要做按 face
> 的分组/度量，用逐 face 调用 `PK_TOPOL_facet_2`（一次传一个 PK_FACE tag），
> 或直接 `PK_BODY_ask_faces` 拿 face tag 后配合局部容差（见 §5.3）。

组装链：`facet → facet_fin → fin → fin_data → data → data_point_idx →
point → point_vec → 坐标`。`-1` 为洞环分隔符（`shape=any` 时出现），需跳过。

### 5.3 自适应面片：`PK_facet_local_tolerances_t` 局部容差（2026-08-05）

复杂大面在全局 `surface_plane_ang=12°` 下仍显“三角化过粗”（实测曲面最大
面内二面角 ≈ 11.3°，正好贴住角度容差上界）。Parasolid 内核自带**按拓扑实体
局部覆盖容差**的机制，是首选的自适应预防手段：

```c
typedef struct
{
    double curve_chord_tol;   /* 0.0 = 不覆盖全局 */
    double curve_chord_max;
    double curve_chord_ang;
    double surface_plane_tol; /* 0.0 = 不覆盖全局 */
    double surface_plane_ang; /* 0.0 = 不覆盖全局 */
} PK_facet_local_tolerances_t;
```

`PK_TOPOL_facet_mesh_2_o_t`（V5 即 `_MeshControlV5`）相关字段及偏移：

| 偏移 | 字段 | 语义 |
|------|------|------|
| 0xF0 | `n_local_tols` | 局部容差组数 |
| 0xF8 | `local_tols*` | `PK_facet_local_tolerances_t[]` |
| 0x100 | `n_topols_with_local_tols` | 挂局部容差的 topol（face/body）个数 |
| 0x108 | `topols_with_local_tols*` | PK_TOPOL tag 数组（body 或 face 均可） |
| 0x110 | `local_tols_for_topols*` | int 数组：每个 topol 使用 `local_tols` 的哪个下标 |

调用约定：`local_tols_for_topols[i]` 取值必须在 `[0, n_local_tols)`；
`local_tols` 某字段为 0.0 时该约束继续沿用全局值（只覆盖要改的约束）。
错误码：`PK_ERROR_unsuitable_topology`（topol 不是 face/body）、
`PK_ERROR_bad_value`（下标越界）。

实测（`upper_cover_01`，默认全局 12°/1e-4 → 2808 三角形）：

| 调用 | 三角形数 |
|------|---------|
| 全局 12°/1e-4 | 2808 |
| 全局 4°/1e-5 | 17952 |
| body 级局部 4°/1e-5（全局仍 12°） | 17952（与全局等价，机制生效） |
| 局部仅 1 个大曲面 face | 3818（其余 face 保持 12°） |
| 局部仅 4 个大曲面 face | 6872 |

自适应策略（已在 `ps_facet2_nodes.py` 实现，`tessellate_xt(adaptive=True)`）：

1. `PK_BODY_ask_faces` 取 body 全部 face；
2. 每个 face 按基准容差（默认 12°/1e-4）单独 facet，度量
   `(facet 数, 面积, 面内最大二面角)`——**只统计同一 face 内共享边的相邻
   三角形**，跨 face 的锐棱（台阶/倒角，二面角≈90°）不参与；
3. 选出「面内最大二面角 > 8° 且 面积 ≥ 1e-4×body 包围盒表面积 且
   facet ≥ 8」的面（即又大又弯的复杂面；小圆角/平面不选，避免面片爆炸）；
4. 最后一次 body 级 `PK_TOPOL_facet_2` 调用，对选中 face 挂
   `surface_plane_tol=1e-5`、`surface_plane_ang=6°`（可配置）的局部容差。

默认参数：`refine_angle_deg=6.0`、`refine_tol=1e-5`、
`smooth_angle_deg=8.0`、`min_rel_area=1e-4`、`min_face_facets=8`。
实测（ex4_e）：`upper_cover_01` 2808→11018、`lower_cover_02` 4664→10068、
`button` 14538→23120，探测+加密总耗时 < 0.8 s/body；平面 box 不变（12）。

#### 5.2.3 参数检查与调用前置

外部进程调用前必须 `PK_SESSION_set_check_arguments(0)`，否则
`PK_TOPOL_facet_2` 返回 `PK_ERROR_o_t_version_incorrect`(5022)——不是内核
不支持 v5，而是参数检查器用当前 SDK 的结构版本比对调用者结构导致。
STpre 自身版本匹配，无需关闭检查。

#### 5.2.4 验证

- box：8 节点 / 12 三角形，坐标 0..0.01 与 GO 逐点一致；
- tr03：Case 1573 节点/3142 三角形、Impeller 1030/2132、Rotate 102/200，
  三角形数与 GO 完全相同，节点数不增（facet_2 共享顶点去重）；
- ex4_e：24 个 body 全部生成，三角形数与 GO 完全一致。

GUI 加载时优先使用 `ps_facet2_nodes.tessellate_xt()`（facet_2 表路径），失败
再退回 `ps_tessellate`（GO 路径）；同一进程只能启动一个 pskernel 会话，
`ps_tessellate._get_session()` 会复用已由 `ps_facet2_nodes` 启动的会话。

### 5.4 多 x_t 成员与 body_files 引用（M1 导入，2026-08-06）

File→Import 导入的 `.x_t` **不拼接**进 `_<project>_all.x_t`（多段 PART1 头
拼接会使 `PK_PART_receive` 解析失败），而是：

1. 原始传输流存为独立成员：`<project>_import_0001.x_t`（`cab_import`
   自动递增编号，避免与已有成员重名）；
2. `ex4_e.xml` 的 `<body_files unit="m">` 追加引用：

   ```xml
   <body_files unit="m">
      <file type="xt"> _ex4_e_all.x_t </file>
      <file type="xt"> _ex4_e_import_0001.x_t </file>
   </body_files>
   ```

3. 读取端必须**遍历全部 `<file type="xt">` 对应成员**逐个
   `PK_PART_receive`，把各成员导出的 body 合并显示；部件仍按
   `SDL/TYSA_NAME` 与 `<parts>/<name>` 匹配，与几何文件归属无关；
4. 每个导入 body 注册为 `<parts type="body">`，字段布局对齐官方样式：
   `name/name2/property/attribute/volume/color/mode/visible_count/
   tree_expand/layer/monitor/rad_group_num/heat_balance/VF_balance/
   facet_kind/def_axis/file/transform`（transform 缺省为单位阵）。

约束：成员名 ASCII；`add_body_file` 幂等；保存使用
`archive.to_bytes(preserve_source_blocks=False)` 重建 CFFILE/CFFOLDER。

---

## 6. 导出格式 `.s`（SDAT，STsolver 输入）

UTF-8 BOM 的文本流，首行 `SDAT`。样例 `tests/ex4_e.s` 的章节（按出现顺序）：

`SDAT / STREAM / POST / HPT / VFEX / UNIT / HEATPATH / EQUA / GRAV / HSOL /
CYCS / UNDR / PROPERTY / CXYZ / PARTS / REGION / V_PRT / A_MDR / INIT_REGION /
TEMP / FLUX_REGION / AMOM_REGION / AENT_REGION / VENT_REGION / VFWL_REGION /
VFEM / VFDE / AUTOFIXP / FOUT / HTRC / SURT / HTFX / MEIX_VAR / UNOR / VNOR /
WNOR / PRES / HBAL_PARTS / HBAL_BTW_PARTS / FBAL / TPRT_OUTPUT / GOGO`

各章节与 cab 成员的数据映射（已验证样例逐项对应）：

| `.s` 章节 | 数据源 |
|------|------|
| `STREAM`（版本/注释） | `ex4_e.xml` 头注释（Version 1623.20302.20231027） |
| `POST/RO/VF/OT/HPT`（文件名块） | `analysis_set/<file>`（.s/.r/.vf/.ot/.hpt） |
| `UNIT`（温度单位等） | `unit` 章节 |
| `EQUA/GRAV/HSOL/CYCS/UNDR` | `analysis_set`（type/grav/heat/cycle/under_relax…） |
| `PROPERTY`（材料物性） | `_ex4_e_property.xml` entry（7 材料） |
| `CXYZ`（网格间距） | `mesh_block` `<x>/<y>/<z>` 坐标（mm→m 换算） |
| `PARTS`（部件盒） | `element` `<parts>` body list（i/j/k 索引盒） |
| `REGION`/`FLUX_REGION` 等 | `analysis_region` face_list region + `value`/`condition` |
| `INIT_REGION/TEMP` | `value type=initial` + `condition` |
| `FOUT/HTRC/SURT/HTFX/MEIX_VAR` | `output` 章节 |

> 结构式网格由 `mesh_block`（99×243×63 坐标）与 `element` 盒表重建；
> 网格数与 `.s` 头 `98 242 62`（ni×nj×nk 单元）一致。**导出可完全脱机实现，
> 无需重跑网格划分**，但部件面分类（面区 → BC 类型）需从 face list 与
> region 名称推导，是主要工作量所在。

---

## 7. 导出格式 `.xemt`（EMT：材料/部件/区域映射）

UTF-8 BOM 的标准 XML，根 `<EMT>`：

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<!-- date/time : 2023/10/31 20:25:31 -->
<EMT>
   <Version no="2023"/>
   <Material>
      <mat no="1" name="air(incompressible/20C)"/>
      ...
      <mat no="7" name="diecast_magnesium(300K)"/>
   </Material>
   <Parts>
      <fluid no="1" name="Domain(cuboid)" mat="1"/>
      <part no="1" name="Domain(cuboid)" mat="1"/>
      <group name="cellular_phone" expand="T">
         <part no="2" name="lower_cover_01" mat="7"/>
         ...
         <part no="32" name="(cuboid)_U_04" mat="4"/>
      </group>
   </Parts>
</EMT>
```

数据源：`Material` ← `_ex4_e_property.xml` 的 entry（名称+序号，与 `.s`
PROPERTY 顺序一致）；`Parts` ← `ex4_e.xml` 的 `analysis_region`（fluid，
mat=1）与 `group/parts`（part no 按出现顺序，mat 由 `<parts>/<property>`
材料名映射到 Material 序号）。分组结构（如 `cellular_phone`）直接保留。

---

## 8. 写入与往返（round-trip）

目标流程：`解析 cab → 编辑 XML 元数据 → 重新打包 cab → 导出 .s/.xemt`。

### 8.1 重打包要点

- 保留成员存储顺序（ex4_e.xml → _property.xml → _all.x_t）。
- 重建 44 字节 CFHEADER（保留 20–23 四个零字节的观测布局）、1 条 CFFOLDER
  （MSZIP、30 块），CFFILE 按成员重算（date/time 可用当前时间或保留原值；
  uoffFolderStart 直接写精确顺序偏移，与本样例官方文件一致）。
- MSZIP 写入：需要按 32KB 解压窗口分块、每块 `CK` + 独立 DEFLATE 流并允许
  引用前块历史；Python 标准库 `zlib` 无法直接产生跨块引用流。可选路线：
  a) Windows `CreateCompressor(COMPRESSION_ALGORITHM_MSZIP)`（cabinet.dll /
  ntcompression API）；b) 自实现受限编码器（每块独立窗口、压缩率略降，但
  合法）；c) 调用系统 `makecab.exe` 由文件生成 cab（保留头差异需验证）。
- CFDATA 校验和字段：算法未验证，写 0 或原样（Windows 工具不校验）。

### 8.2 编辑语义

- `ex4_e.xml` / `_ex4_e_property.xml`：标准 XML，ElementTree 直接
  parse/serialize；写回时保持 UTF-8 BOM、注释头、缩进风格（2 空格，文本节点
  带首尾空格——序列化需自定义以逐字节稳定）。
- `.x_t`：头部 `**PART1` 属性行（FRU/APPL/SITE/DATE 等）可文本级编辑；
  实体几何显示级通过 `pskernel.dll` 面片化（GO 回调见 §5.1；STpre 同源的
  `PK_TOPOL_facet_2` 表格路径见 §5.2），不做字节级改写。

---

## 9. 与 pphdecoding（scFLOW `.pph`）的异同

| 维度 | scSTREAM `.cab`（本仓库） | scFLOW `.pph`（pphdecoding） |
|------|--------------------------|------------------------------|
| 容器 | Microsoft CAB（MSCF + MSZIP） | ZIP（deflate） |
| 加密 | 无 | PKBody3 外层 Blowfish-LE ECB |
| 文本成员 | ex4_e.xml / _property.xml | main.xml / main.prp / main.xenv / main.js |
| 几何 | `_ex4_e_all.x_t`（明文 Parasolid） | `main.sctsnapshot`（CADThru 快照内 PKBody3 密文 + ZIPOCTREE） |
| 网格 | 内嵌于 XML（mesh_block/element） | 独立 `.gph/.oct/_part.mdl/_ridge.mdl`（CRDL-FLD） |
| 导出物 | `.s`（SDAT）+ `.xemt`（EMT） | `.s` + `.xemt`（flddecoding 已实现） |
| 解析器 | `parasolid.py` 可复用（schema/字段/实体） | 同左 |

---

## 10. 未解决问题清单

1. **uoffFolderStart 跨版本验证**：本样例三个成员均为精确连续偏移；其他
   版本/规模 cab 是否保持该约定需多样本确认（解析端按顺序拼接，不依赖
   该字段）。
2. **CFDATA 校验和算法**：u32 字段存在，常见 MS-CAB 校验变体均未匹配，
   需对照 Windows `makecab.exe` 输出反推或确认 Cradle 自定义算法。
3. **MSZIP 写端实机验收**：本仓库已用 zlib `zdict` 实现跨块历史编码器，
   输出经 Windows `expand` 解包验证逐字节一致；仍待 SCTpre 实机验收。
4. **多样本覆盖**：当前已有 ex4_e（2023.2）、box、tr03（2025.2，无
   `element` 网格、嵌套 group）；仍需更多版本（2024/2025.2 各规模）、
   不同网格组规模、多材料/多 region 的 cab 验证 CFHEADER 布局与 XML
   章节集（尤其新版新增 `<jos_model>`、`<boil>`、`<free_surface>` 等
   condition_wizard 位与对应章节）。
5. **`.s` 面分类**：element face list（`-1..-6` 编号语义）到 BC 类型的
   映射已在 ex4_e 黄金对拍锁定（A_MDR 行与 @UNDEFINED* 标记），跨版本确认
   仍需更多样例。
6. **Parasolid 完整 B-rep 拓扑**：完整拓扑还原仍留作长期项
   （商业内核 / 超长逆向）；**显示级曲面已通过 Cradle `pskernel.dll`
   `PK_TOPOL_render_facet` GO 面片化与 `PK_TOPOL_facet_2` 表格化面片解决**
   （2026-08-04，见 §5.1 / §5.2）。

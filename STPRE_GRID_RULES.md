# STpre gridding/meshing 算法规则逆向（多实例黑盒探测）

> 方法：`stpre_probe.py` 通过 `Gridding/Meshing via STpre API` 的 COM 桥
> 逐实例启动 STpre，控制 domain / vertex detection / method / std /
> threshold / ratio / transform / 部件几何，记录输出 `mesh_block`
> 坐标表、part cell boxes 与 mesh_control 回显，再归纳规则。

## 1. 复现与数据

```powershell
python stpre_probe.py                                   # 35 个默认用例
python stpre_probe.py --cases base_minmax_detail,vd_uniform
python stpre_probe.py --analyze data/stpre_probe_20260808_all.json
```

标准数据集：`data/stpre_probe_20260808_all.json`（35/35 OK，2026-08-08）。
每个 record 含 `input`（参数）、`rc`（COM 返回码）、`output.axes`
（mm 坐标）、`output.part_boxes`（部件占用 cell 范围）与耗时。

## 2. 已确认规则

### 2.1 RootBlock / 网格范围

- RootBlock AABB 恒等于 computational domain（min/max 精确落在域边界）；
- 网格只覆盖域内：部件完全/部分在域外时不产生占用 cell
  （`domain_noncube_offset`：box 的 y 在域外 → `part_boxes` 为空；
  `part_translate_2_5`：+2.5 m 位移移出域 → x/y/z 均无内区）。

### 2.2 part transform 单位

- `<parts><transform>` 16 值列主序，**平移量单位为 m**（与
  `<volume unit="m">`、`<file unit="m">` 一致）：
  - `+2.5`（当作米）→ 部件移出域，退化为单边几何网格；
  - `+0.0025`（=2.5 mm）→ 内区恰为 2.5..12.5 mm，10 个 1.0 mm 间隔；
- 旋转 30°/45° 后 STpre 按**变换后几何的 AABB/顶点**布网格
  （30° 旋转 AABB 为 13.66 mm，网格 32×32×29）。

### 2.3 vertex detection 模式

| 模式 | 行为（实测） |
|---|---|
| minmax (3) | 只在部件 AABB min/max 坐标放网格线；内部按 std 等分拟合 |
| axis_plane (2) | 只在轴对齐的面平面放线；旋转体无轴对齐面 → 退化为 AABB（同 minmax） |
| all (0) / representative (1) | 在**每个顶点投影坐标**放线 + AABB；相邻顶点平面之间按 std 拟合等分 |
| not_considered (4) | 对凸盒与 minmax 相同（仍按部件区域划分内/外区） |
| uniform (5) | 完全忽略部件：全域按 std 均匀布点（51×51×51 @ std=1.0） |

旋转 30° 立方体 x 轴证据（all/rep）：
顶点 x 投影 {-5, 0, 3.66, 8.66} 均有网格线，段间拟合：
`[-5,0]` 5×1.0、`[0,3.66]` 4×0.9151、`[3.66,8.66]` 5×1.0；
而 minmax/axis_plane 只有 AABB 线 -5 与 8.66，内部 14×0.9757。

### 2.3.1 tr03 representative 子集（P0-① 深挖，2026-08-15 后）

对 tr03 叶轮（域 z=[-20,120]，部件经 transform -47.5mm 后 z∈[-47.48,47.48]，
底部伸出域外）实测 STpre rep 轴 = 92 线，其中部件线仅 25 条（成员 B-rep 59 个
z 值 → 世界系 59 值，域内 33 值，仅 25 条在轴内）：

- **域外顶点直接丢弃**（部件 z < -20 的 23 个值全部不出现）。
- 域内 33 值中 **8 个被并入邻近网格线**（阈值 0.1 内的直接并入，如
  -19.989/-19.926 → -20；+19.989 → +19.9264；+24.932 → +24.9208），
  其余 25 值全部出现在轴内。
- 但另有一批「距离邻近线 0.3~0.45 却仍被丢弃」的值（-17.577、-8.103、
  +2.349、+21.176、+21.904、+32.573、+33.823…）——说明 **STpre rep 的
  顶点集是 B-rep 顶点的真子集**（疑似「至少一条非光滑边」的尖角顶点，
  PK_EDGE_ask_convexity smooth=3 判据待该 ABI 最后确认；当前
  `representative_vertices` 已按 4 参 ABI 正确取边，convexity 未确认时
  保守保留全部顶点）。
- 阈值联动验证：thr 0.1→92、0.5→89、2.0→42（z 轴），阈值=合并容差，
  但 STpre 的合并比本实现温和（本实现 thr=2.0 得 38 线 vs STpre 42）。
- 外部区（部件 AABB 顶面 47.4651 → 域顶 120）为 ratio_out 1.2 的几何级数
  12 段 {1.0,1.18,1.39,…,10.07}，逐段间距实测与总和约束解一致。

工具：`tools/reprobe_tr03.py`（live STpre COM 重跑 vd_0/vd_1，与金标一致）。

### 2.4 内区划分

- 相邻“特征平面”（顶点投影线或 AABB min/max）之间的区间按
  `n = round(段长 / standard_length)` 等分，实际间距 = 段长 / n
  （轴对齐 10 mm + std=1.0 → 10×1.0；旋转段 3.66 mm + std=1.0 →
  4×0.9151）；
- `ratio_in`（internal ratio）> 1.0 时内区不是等分而是**自部件边界
  向内部对称几何级数**：std=1.0、ratio_in=1.2、内区 0..10 →
  7 段 {1.0, 1.285, 1.653, 2.124, 1.653, 1.285, 1.0}，q≈1.285 由
  `1+q+q²+q³+q²+q+1=10` 解出；
- `std_5_0` → 内区 0..10 恰为 2×5.0；`std_0_25` → 40×0.25。

### 2.5 外区几何级数

- 部件边界 → 域边界之间为几何级数：**贴部件侧首间距 = standard
  length**，随后每段 ×q；q 由名义 `ratio_out` 经总和约束解出
  （`g0·(q^n-1)/(q-1) = L`），实际 q 接近名义值；
- base（L=25 mm、std=1.0、ratio_out=1.2、n=10）：间距
  1.0, 1.192, 1.422, 1.695, 2.022, 2.412, 2.876, 3.43, 4.09, 4.87，
  q≈1.192，总和恰 25.0；
- `ratio_out=1.0` → 外区也等分，全域 51×51×51（与 uniform 相同）；
- `ratio_out=1.5` → 外区点数减少（24³），最大间距 8.05；
- 左右外区独立求解（std_5_0：左 L=25→4 段 q≈1.148，右 L=15→3 段
  q=1.0）。

### 2.6 method / 单元数

- `detail`（rough_and_detail）：2.3–2.5 的完整规则；
- `coarse`（rough_only）：只在**域 min/max 与部件 min/max** 放线
  （4×4×4，`-25,0,10,25`），无内外区细分；
- `auto1`（指定单元总数）：每轴单元数 ≈ `round(目标数^(1/3))`
  （8000→20 cell/21 点；64000→40/41），再反解 std 分配内外区
  （8000：内区 6×1.667；64000：内区 17×0.5882）；
- `auto3`（指定每轴单元数）：严格 21 点 = 20 cell/轴 +1；
- `edge_contact=1`、`divide_scale=4` 对单凸部件 RootBlock 网格无影响；
- `two_parts`（同几何第二个部件）网格与单部件相同。

### 2.7 meshing（ExecuteElement）

- `part_boxes` 输出 9 字段 `[i1,i2,j1,j2,k1,k2,0,1,1]`：部件占用
  cell 索引范围 + 类型标志；与 `.s` 的 PARTS 6 字段范围一致；
- 部件在域外 → 无占用 cell。

## 3. 负面结论与待补充

- **STL/polygon 部件**按当前 relay（parts type=polygon + .stl 成员、
  无 body_files 条目）不被 STpre API 网格化：5 个 L 形用例全部退化为
  51×51×51 空域均匀网格，`part_boxes={}`；需先还原 STpre 自己的
  STL 部件 cab 布局（body_files type 或 file 引用）再探；
- threshold（limit）在凸盒上无区分度，需曲面/缺口部件验证
  （Parasolid 构造非凸 body 或圆柱 x_t）；
- axis_plane 对圆柱等曲面部件的“面平面”语义未验证；
- auto1 的“每轴 cell 数→内/外区分配”已解出（见 §5.2，13/13 验证）；
- multiblock（RootBlock 之外的子块）与 cylinder/axial 坐标系未覆盖。

## 4. 与 cabdecoding 原生算法差距（后续改进点）

> 2026-08-09：以下差距已在 cab_grid.py 原生实现中补齐（§7）。

1. 内区 `ratio_in>1` 对称几何级数已实现（`_inner_symmetric`）；
2. 外区“首间距=std、q 二分求和”保持（`_stpre_external`）；
3. vertex detection：All/Representative 顶点投影线 + 阈值合并已实现；
4. auto1 目标→每轴→内外区分配已实现（`stpre_rules.auto1_*`）。

## 7. 原生 gridding 落地对拍（2026-08-09）

- `cab_grid.rough_grids`：not_considered 保留部件 min/max 线；
  threshold 合并；uniform 只留域边界；
- `cab_grid.refine_grids` num_elements：STpre auto1 全布局
  （P 闭式 + L/R min-max + 内外区坐标生成）；auto3 目标=cell 数；
- `_inner_symmetric`：ratio_in>1 对称双端几何级数；
- `GriddingDialog._gridding`：顶点/面片先应用部件 transform；
- 对拍：base 29³ 与 auto1 21³ 的坐标与 STpre 黑盒数据逐点一致；
  全仓 229 通过 / 4 跳过。

## 5. 第二轮精确化（2026-08-08，新增 30 用例）

数据：`data/stpre_probe_20260808_auto1.json`（10）、
`data/stpre_probe_20260808_auto1_scale.json`（2）、
`data/stpre_probe_20260808_tr03.json`（9）、
`data/stpre_probe_20260808_ex4e.json`（9）、
`data/stpre_probe_20260808_stlreg.json`（2）。

### 5.1 auto1 精确规则（box，域 -25..25，部件 0..10）

- 每轴 cell 数 n = `round(target^(1/3))`：1000→10、2000→13、4000→16、
  8000→20、16000→25、32000→32、64000→40、100000→46；
- 内区 P 实测表（部件 10 mm，域 50 mm）：

| n | 10 | 13 | 16 | 20 | 25 | 32 | 40 | 46 |
|---|---|---|---|---|---|---|---|---|
| P | 3 | 3 | 4 | 6 | 9 | 12 | 17 | 21 |
| 内区间距 s | 3.333 | 3.333 | 2.5 | 1.667 | 1.111 | 0.833 | 0.588 | 0.476 |

  n=20 时随部件尺寸：5 mm→P=4（s=1.25）、10 mm→P=6（s=1.667）、
  20 mm→P=10（s=2.0）；P 与域外长度无关（域 0..100 时 P 仍为 6）。
- 外区 L/R 拆分规则已定量确认：L+R = n-P，枚举所有拆分，选
  `max(g0_L, g0_R)` 最小者（让较粗一侧尽量细），其中
  `g0_L = L_out·(q-1)/(q^L-1)`、`g0_R = R_out·(q-1)/(q^R-1)`、
  q=ratio_out=1.2；随后左右 g0 分别按各自总长精确求解
  （例：n=20 → L=8/R=6，g0_L=1.515、g0_R=1.511）。

### 5.2 auto1 内区 P 闭式公式（已解出，13/13 验证）

P 是满足下式的最小正整数：

```
P + ceil(log(1 + L_out·(q-1)/s) / log q)
  + ceil(log(1 + R_out·(q-1)/s) / log q) >= n      （s = p/P）
```

含义：以 s=p/P 为外区首间距、ratio_out=q 向域边界做几何级数，所需
区间数（向上取整）加内区 P 达到/超过每轴总数 n，取最小 P；外侧长度
为 0 时对应项为 0。随后 L/R = argmin max(g0L, g0R)（L+R = n−P）。
已用 13/13 组黑盒数据验证（n=10..46、部件 5/10/20 mm、居中/偏移/
贴边、立方/非立方域），实现见 `stpre_rules.auto1_inner_count` /
`auto1_axis_layout`。

### 5.3 曲面部件的 vertex detection 层级（tr03 叶轮 / ex4_e 电池）

- **all (0) > representative (1) > axis_plane (2) = minmax (3) =
  not_considered (4)**（按网格线数量）：
  - tr03 叶轮：all 59×118×121；rep 57×91×92；plane/minmax/none
    57×85×85（三者坐标相同）；
  - ex4_e 电池：all 89×66×28；rep 63×57×18；plane/minmax 61×57×18；
- threshold（limit）对 all/rep/plane 都生效：叶轮 rep thr0.1→57×91×92、
  thr0.5→57×90×89、thr2.0→33×41×42（2 mm 阈值滤除大量细部顶点线）；
  thr2.0 时 rep(33×41×42) 与 plane(32×46×47) 不再相同；
- 凸盒/旋转盒上各模式无区分度（§2.3），**必须用曲面/多特征部件**区分。

### 5.4 负面结论补充

- ex4_e **speaker（开放曲面/panel）**：所有模式 grid 相同（19×14×15）
  且 `part_boxes={}`——开放面/panel 部件不产生实体占用 cell，需
  panel/sheet 专用规则（原生 cab_mesh 同样需处理）；
- STL/polygon 部件即使补上 `<body_files><file type="stl">` 与
  `<parts><file> lshape.stl </file>` 仍不被 STpre API 网格化
  （stlreg 2 例均退化为 51³ 空域网格）——STpre API 的 relay 只认
  x_t body 部件。

## 6. DLL 反汇编结论（STpreBase_Bx64.dll，2026-08-08）

工具：lief 0.12.3 + capstone 5.0.7；导出函数按 RVA 定位，常量按
RIP-relative 解析。

### 6.1 `MeshBlock::SetElementNum`（RVA 0x1E3C40）— auto1 每轴分配

反汇编得到（非轴对称分支）：

```
nx = trunc(((Lx^2 / (Ly*Lz)) * N)^(1/3) + 0.5)
ny = trunc(nx * Ly / Lx + 0.5)
nz = trunc(nx * Lz / Lx + 0.5)
```

轴对称分支：`nx=trunc(sqrt((Lx/Lz)*N)+0.5)`、`nz=trunc(nx*Lz/Lx+0.5)`、
`ny=1`。已用黑盒实测验证：域 100×50×25、N=8000 → STpre 输出
41×21×11 点（40×20×10 cell），与公式完全一致；立方域即
`round(N^(1/3))`。实现见 `stpre_rules.auto1_per_axis_counts`。

### 6.2 `MeshBlock::CalcFineCoord`（RVA 0x1CB000）— 几何级数坐标

给定区间长 L、段数 n、比值 q，首间距：

```
g0 = L * (1 - q) / (1 - q^n)     （q==1 时 g0 = L/n）
```

坐标按 `x[i+1] = x[i] + g0; g0 *= q` 累加。这是“给定 q 反解 g0”的
路径（内区 ratio_in 的名义值再经 CalcRatio1 求实际 q）。

### 6.3 `MeshBlock::CalcRatio1/CalcRatio2`（RVA 0x1CB4F0 / 0x1CB840）

几何比求解器：q 从 1.01（或 0.99）起步、步长 0.01 扫描，容差
1e-5，随后 30 次牛顿精化（0x1CB770 循环），上限 500 次迭代；
常量 1.0 / 0.1 / 0.0001 / 1e-5 均在代码中确认。

### 6.4 已固化为可测试模块

`stpre_rules.py`：

- `auto1_per_axis_counts`（SetElementNum 公式，含轴对称分支）；
- `geometric_first_spacing` / `geometric_coords`（CalcFineCoord）；
- `split_outer_counts`（auto1 外区 L/R：枚举使 |g0L−g0R| 最小，
  §5.1 黑盒规则，反汇编确认存在 CalcRatio 求解器支撑）；
- `inner_segment_split`（顶点段 `n=trunc(len/std+0.5)`）；
- `calc_ratio`（几何和方程二分求解，对齐 CalcRatio 语义）。

验证：`tests/test_stpre_rules.py` 7 项，含非立方域 auto1 与
`split_outer_counts(25,15,14) → (8,6)` 对拍黑盒数据。

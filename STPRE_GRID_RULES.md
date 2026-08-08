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
- auto1 的“每轴 cell 数→内/外区分配”确切公式未定（可再扫
  目标数 × 部件尺寸/位置矩阵）；
- multiblock（RootBlock 之外的子块）与 cylinder/axial 坐标系未覆盖。

## 4. 与 cabdecoding 原生算法差距（后续改进点）

1. 原生内区固定等分；STpre 在 `ratio_in>1` 时用对称几何级数；
2. 原生 `_stpre_external` 已实现“首间距=std、q 二分求和”，与实测
   一致（可对拍 golden）；
3. 原生 vertex detection 需补充“顶点投影线分段拟合”逻辑（All/
   Representative 对旋转部件目前没有逐顶点投影线）；
4. auto1 的目标→每轴→内外区分配需按实测规则实现。

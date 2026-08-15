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
  顶点集是 B-rep 顶点的真子集**（25/59）。
- 子集判据排查（均被排除）：①尖角/光滑边（PK_EDGE_ask_convexity 正确
  3 参 ABI 后实测 DROP 与 KEEP 顶点凸性模式完全相同，均为 token
  0x5C2E/0x5C2D）；②面类型（平面 4001 / 圆柱 4002，两组混合无法区分）。
  判据仍未知——下一步：反汇编 STpreMesh MeshFineDivide 的顶点收集路径。
- 计数方向已自洽：STpre rough 顶点少（25 vs 我们的 33）→ 段更长 →
  细分点更多 → 总轴数更多（92 vs 88）。
- 当前 `representative_vertices` = 全顶点集（行为中立），待判据确认后启用。
- 阈值联动验证：thr 0.1→92、0.5→89、2.0→42（z 轴），阈值=合并容差，
  但 STpre 的合并比本实现温和（本实现 thr=2.0 得 38 线 vs STpre 42）。
- 外部区（部件 AABB 顶面 47.4651 → 域顶 120）为 ratio_out 1.2 的几何级数
  12 段 {1.0,1.18,1.39,…,10.07}，逐段间距实测与总和约束解一致。

工具：`tools/reprobe_tr03.py`（live STpre COM 重跑 vd_0/vd_1，与金标一致）。

### 2.3.2 tr03 全模式 S 线全景（P0-①，2026-08-15 二次深挖）

tools/probe_tr03_marks.py 重跑 tr03_imp vd_0..5 并捕获每轴 (值,标记) 对
（金标存 data/stpre_tr03_marks.json）。z 轴 S 线数：

| vd | 模式 | z 轴 S 线 | 内容 |
|---|---|---|---|
| 0 | all | 84 | 未知来源（见下） |
| 1 | representative | 26 | 25 个 B-rep 顶点投影 + AABB 顶 47.4651 |
| 2 | axis_plane | 3 | 面平面 +8.1026/+10.6026（只有正 z 面）+ AABB |
| 3/4 | minmax / not_considered | 1 | AABB 顶 47.4651（min z 在域外） |
| 5 | uniform | 0 | — |

- rep 不是 all 的子集：rep 的 27.2809、41.6617 不在 all 中 → 两种
  模式使用不同的顶点源，并非「all = rep + 额外」。
- all 的 84 线来源仍未知，本轮排除：①B-rep 顶点（仅 23/84 命中）；
  ②facet_2/GO 渲染 tess 顶点（tol 1e-5..1e-3、angle 5..30° 全扫，最高
  36/84 命中，且不随容差收敛）；③Case/Rotate 其它 body（Rotate 为
  3 面 2 边 0 顶点薄体，Case 仅贡献 1 线）；④x/y/z 投影混合（仅 +1）；
  ⑤面平面（axis_plane 只有 3 线）。all 的 x 轴 S = {-6.6667, 0, 6.6667,
  20, 22.5} 含非顶点值（0、±6.667=±20/3）——与「顶点投影」假设直接矛盾。
- 反汇编定位修正：MeshFineExecute(0x25690)/MeshFineDivide(0x25570)
  完整反汇编 + IAT 解析（tools/disasm_mesh.py、tools/resolve_iat.py）：
  MeshFineDivide = 选轴/选 id（GetSelectAxis/GetSelectId）+ 排序 +
  CalcFine(0x7c3f0)；MeshFineExecute = 细分坐标合并阶段——遍历
  [ctx+0x190] 链表中的 MeshBlock（Valid/IsSub 过滤），对每根 fine 坐标
  （AllocFineCoord/GetFineCoord + get_limit 阈值 + GetAttrAt 标记 8/1
  比较 + get_minmax 界内判定 + GetPeriodKind 周期合并）把未标记线写入，
  冲突时 virtual [rax+0x28] 取名 + 错误 0x103b → OutputMessage。
  顶点收集不在此函数——下一步应看 InnerRegionGrid/OuterRegionGrid/
  ExecDivide 或 MeshBlock 粗线收集路径（STpreBase_Bx64.dll 的
  ?SetParam/网格线插入实现）。
- MeshCoarseDivide(0x23be0) + 收集器(0x1ab90, ~8KB) 反汇编（本轮）：
  * 入口流程：GetMeshCtrl → GetRootBlock → SetupMeshBlock →
    GetCoordArray(每轴) → 0x1ab90(block, select_mode, num_parts,
    &coord 数组, &counts)。
  * 0x1ab90 结构：GetAnalysisMinMax 后按 |range|×1e-5(0x7d708) 双侧
    扩界（越界顶点微容差）；get_limit×0.01(0x7d720) 阈值换算；
    块 min/max 经 AddInitEntityAt 注册（attr 0x10/4/8 = B/普通/部件线）；
    [block+0x188] 实体表（GetCount/GetCoordAt/GetAttrAt/GetPartsAt）
    逐点注册；随后 QueryPreParts 部件循环：
    - vtable+0x7c8 返回 2/4/8/16/32 → 部件级 select_vertex 模式
      0/1/2/3/继承（**本轮已实现**：cab_grid._effective_detection +
      rough_grids/build_axes part_detections + GriddingDialog 接线）；
    - 部件类型 switch（ecx=type-0x10f, 42 分支跳表 @0x1cba0）分派
      GetBoundingBox1(porous)/顶点提取等路径；
    - select_mode([rbp-0x68]) > 4 → delete_all_ijk_list(-1)（uniform 跳过）。
  * 常量：0x7d750=2π（θ 周期合并）、0x7e5d8=0.501（round(x+0.501)）、
    0x7e5c0=1e-30（退化零）、0x7e680/0x7e690=±1。
  * 下一步：沿部件类型分支定位 all/rep 的顶点来源（当前 all=84 线
    金标仍未复现；非 tess/B-rep/面平面）。
- **vd_0 "all" 真身 = 显示网格顶点投影（SaveStlFile 铁证，本轮）**：
  STpreModel.SaveStlFile 导出 Impeller 显示网格（2206 三角 / 6618 顶点，
  文本 STL、米制、世界系；tools/probe_stl_mesh.py）。其 x/y/z 投影
  **100% 覆盖 vd_0 全部 5/82/84 条 S 线**（1e-3 容差）——all 模式的
  网格线就是显示网格顶点投影，无额外 AABB 线（AABB 极值与网格顶点重合）。
  且 rep ⊄ all 之谜同样解开：rep 用 B-rep 顶点、all 用显示网格顶点，
  两集合不同源，自然互不为子集。
- 剩余差距精确定位：本仓 facet_2/GO 在 1e-8..1e-2 × 0.06°..30° 全扫
  （含曲线容差）**无一覆盖 STpre 网格顶点**——默认 1e-4/12° 网格规模
  接近（2132 vs 2206 三角）但顶点位置差 ≤0.6mm，且 STpre 网格独有
  x=-6.667/0/+6.667 三个平面（我们的 tess 任意容差下 x 投影恒为 4 值）。
  → 下一步：反汇编 STpreBase_Bx64.dll 的 MakeFacetParam(0x293C20)/"
  "FacetParam::Get(0x36160) + ParasolidGW PKFaces_RenderV3 选项派生，"
  "拿到 STpre 精确 facet 参数（推测含 facet_plane_tol/min_facet_width/"
  "max_facet_width 组合，x=±20/3 平面正是宽度约束产物）。
- MakeFacetParam(0x293C20) 解码（本轮）：new(0x30) + 从入参 6 double
  结构拷贝 6 个容差，每个 ≤0 则钳为 -1.0（0xbff0000000000000，表示"默认/
  自动"）；MakeFacet(0x293A20 包装 / 0x293D00 主体) 构建 PreBody——
  PreFace(get_plane_type/get_facet/IndexedFaceSet::Mirror)、PreEdge(
  PrePolyLine::MirrorLine)、PreVertex(TransformVector + Set)——即显示模型
  由 面/边/顶点 三个 Pre 对象表组成，facet 网格本身来自 PreFace::
  get_facet 的 IndexedFaceSet（导入时生成）。
- 显示网格与工程设置无关（本轮实测）：project/precision 0..4 下
  SaveStlFile 恒为 2206 三角、同样的 7 个 x 平面——网格在导入时一次性
  生成，容差来源仍待追（MakeFacetParam 入参 6 double 的调用方）。
- x=±6.667=±20/3 平面的几何签名：6.667/20=1/3=cos(70.53°)——四面体角！
  叶片圆弧边按等参数采样且恰好含 ±70.53°（cos=±1/3），与 0°/±60° 系
  （cos=±1/2 → x=±10，STpre 网格中无 x=±10 线）互斥 → STpre 曲线采样
  规则为下一步突破口（反汇编 PreFace facet 生成 / IndexedFaceSet 构造
  或 ParasolidGW 的曲线 tess 调用）。
- **facet 参数管线全解码（本轮，P0-1 最后一公里）**：STpreBase
  MakeFacet(0x293A20) -> 按 GetPreCtrl 标志分派
  0x1b4380/0x1b4710（面片生成器）。0x1b4710 反汇编：
  * 容差来源 = **GetEnvironment 五字段**（偏移 0x29A8/0x29B0/0x29B8/
    0x29C0/0x29C8），角度字段经 pi/180 换算（默认 DEGREES），
    chord 字段钳制 <=0.001（m）；
  * 部件 facet_kind 开关（r8w）选默认角度分支：kind=2 -> 10 度，
    其余 7.5/10/15/30 度分支（常量 0x430160=15、0x444a18=10、
    0x444a10=7.5、0x431190=30 度 rad）；
  * 五值块 [rsp+0x80] -> 0x1b5620/0x1b5e80（按 part 类型）->
    0x1b8a30 + 0x3e8d66（lambda/vtable @0x585f80）——**STpre 自带
    三角化器**，非 PK_TOPOL_facet_2；本仓任意 PK 参数组合（含 10/15 度
    + curve ang + min/max width 全组合实测）均无法复现其顶点集。
  * 结论：all 模式顶点源=显示网格（已证）；参数管线（env 五字段 +
    facet_kind 角度分支 + chord 钳制）已解码；最终网格算法为 STpreBase
    私有三角化器（0x1b5620->0x1b8a30），完整复刻需按该函数逐行移植，
    列为长期项。env 五字段若出现在项目 XML/设置文件中即可直接读取
    （当前模板未见，推测来自 Option 详细设置，进程内全局）。
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


---

## 7. 圆柱 / 轴对称域（P0-②，2026-08-15 COM 探针对齐）

探针 tools/probe_cyl_domain.py：headless STpre 上 SetCylindricalDomain +
RootBlock SetParam(length/limit/ratio) + SetGridParam(minmax/detail) +
ExecuteGrid/ExecuteElement + 保存后逐字节读 mesh_block。金标保存在
tools/probe_work/cyldom_*.cab（tools/probe_work/ 已 gitignore）。

### 7.1 域存储

- <analysis_region type="cylinder">，无 base/size，用
  <radius unit="mm"> r1,r2 </radius>、<angle> t1,t2 </angle>（度）、
  <height unit="mm"> z1,z2 </height>。
- 轴对称：域仍为 cube（x=R、z=Z），<analysis_set><axissymmetry> 1
  ，Y 轴坍缩为 2 线，y_max = y_min + min(x_len, z_len)
  （"Maximum length in Y direction: Auto"）。
- SetCylindricalDomain 且 t1=t2=0 直接 COM 报错 —— 轴向域不是
  零角楔形，而是 cube + axissymmetry 标志。

### 7.2 mesh_block 存储

- <system> 1 </system>（cartesian 为 0）；
- 轴标签为 <r num unit="mm">、<t num unit="radian">（θ 存弧度）、
  <z num unit="mm">，子元素同 <g no> value,MARK </g>；
- min/max 为 r1,0,z1 / r2,θ2_rad,z2（θ 用弧度）；
- <parts no="N"> name </parts> 挂在对应轴上。

### 7.3 布点规则（金标对拍全部复现）

- R 轴 = 径向投影（r=√(x²+y²)）走与笛卡尔相同的内/外区 refine：
  - 部件 XY 包围盒含轴 → 径向 minmax 范围 [0, r_max]（r_min 取 0）；
    否则 r_min = 最小顶点半径；
  - r_min/r_max 为 S 线；内区按 std 等分（如 [0,14.142] std5 → 3×4.714）；
  - 外区几何级数、首间距=std、实际 q 精确填满区间（1.2 → 实测
    5.0, 5.905, 6.975, 8.240, 9.734）；
  - 环域（域 r=20..50、部件在 r<20 孔内）→ 全域按外区处理
    （首间距 std，q 填充 → 20,25,30.456,36.411,42.909,50）。
- Z 轴 = 部件 z 界（域内截断）的内/外区 refine，与笛卡尔一致。
- θ 轴 = 均匀，n = θ_span(度) / std（非弧长）：
  360/5→72、180/5→36、360/2.5→144；端点均 B 线，含 0 与 span。
- vertex detection 语义与笛卡尔一致（minmax 只放 min/max S 线；
  all/rep 追加各顶点径向投影）。

### 7.4 实现对齐

- cab_grid._build_cylindrical_axes：R/Z 内/外区 refine + θ=span/std；
  _radial_part_extent 实现「含轴 → r_min=0」规则；
- cab_grid._build_axial_axes：x/z 笛卡尔 refine + y 坍缩 2 线；
- cabxml.mesh_coordinate/mesh_axes/mesh_axis_entries/set_mesh_axis/
  set_mesh/set_root_block_range/root_block_bounds：r/t/z 族读写、
  θ 弧度↔度双向转换、system=1、min/max 弧度；
- cab_domain.apply_domain/domain_from_xml：radius/angle/height 存取 +
  axissymmetry 标志写删；
- 验证：tests/test_cylindrical_axes.py 11 项（R/Z 金标 4 组、θ 计数、
  环域、序列化往返、set_mesh_axis 弧度、域 XML 往返、轴向标志）。
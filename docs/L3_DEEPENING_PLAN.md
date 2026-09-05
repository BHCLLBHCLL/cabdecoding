# L3 深化计划 — UI / 几何建模 / CW 条件 / 导入导出 四域深度升级

> 立项：2026-09-05（v9.3 双口径刷新后）。
> 基线：整体 98.4%（满格 7 / 中间 5 / 差距 0）；四域现状
> D3 UI **L2**、D2 几何建模 **L2**、D6 CW 条件 **L2**、
> D12 导入导出 **L2–L3**。
> 方法学沿 pphdecoding §9.1：**L3 = 格式字节恒等 round-trip /
> 内核 ABI 签名级 / 与宿主黄金量化对拍**。
> 关联：[function_gap_analysis.md](function_gap_analysis.md) §0、
> [NYI_INVENTORY.md](NYI_INVENTORY.md)。

---

## 0. 四域 L3 验收口径（先钉死，否则永远达不到）

| 域 | L3 定义（本计划验收句） |
|---|---|
| D3 UI | 对话框字段 ↔ STpre 官方对话框字段**逐字段对照矩阵**自动生成并可再生（工具链，如 manual_coverage 模式），抽样域有官方样本件字段级对拍 |
| D2 几何建模 | 官方 .cab 零件元素经「读入 → 参数面编辑 → 写回」后**官方键语义保真**（14 kind × 官方样本矩阵测试）；代理 tessellation 与官方 x_t 做包络/体积**量化对拍**（公差断言） |
| D6 CW 条件 | **语料级发射 parity 矩阵**：官方 .cab 读入 → CW load/apply 空转 → build_sdat 与官方 .s diff 归零（抽样 ≥20 官方样本；ex4_e 单样本 parity 升级为矩阵） |
| D12 导入导出 | IFC/STEP/x_t 导入↔导出**闭环量化对拍**（几何恒等：体积/包络/质心公差断言），非仅"自产自销能读回" |

明确豁免（沿 NYI 册，不影响 L3 声明）：
STHM/POROUS_MEDIA/JOS 逐字直传的语义映射（NYI #5）、STEP/SAT writer
捆绑（NYI #11）、draft/midsurface 内核上限（NYI #2）。

---

## 1. 逐域现状 → L3 差距与工作项

### D3 UI（100% L2 → L3）

现状证据：8 菜单无 NYI、90+ 对话框、manual_coverage 708 页（页面级）。
L3 缺口：**字段级**对照不存在——对话框字段与官方对话框字段的对应
关系目前只散在实现注释里。

| # | 工作项 | 产出 | 量 |
|---|---|---|---|
| UI-1 | `tools/gen_ui_field_matrix.py`：静态扫描对话框类（QLineEdit/QSpinBox/QComboBox 标签行）→ 字段清单 JSON | `data/ui_field_matrix.json`（可再生） | M |
| UI-2 | 字段名 ↔ `HTML_STpre_Eng` 帮助页输入项自动对照（别名表 + 手工核对残留） | 矩阵报告：每对话框 × 每字段 = exact/alias/missing/extra | L |
| UI-3 | missing/extra 处置：missing 补字段或入册边界理由；extra（官方没有的字段）逐个裁决 | 矩阵清零或入册 | M |
| UI-4 | 抽样实机对拍：3 个高频对话框（Analysis Types/Part/Solver Parameters）与 STpre 实机截图逐字段核对 | 对拍记录入 docs | M（live-COM 窗口） |

### D2 几何建模（99% L2 → L3）

现状证据：官方键 schema 对齐（roundtrip 测试 14 kind）、cabxml 全文档
字节恒等、官方 x_t 成员 155 个在 cab 内。
L3 缺口：①参数面编辑后的**官方键语义保真**未做矩阵级验证；②代理
tessellation 与官方几何**无量化对拍**。

| # | 工作项 | 产出 | 量 |
|---|---|---|---|
| D2-1 | 官方零件参数保真矩阵：官方 cab 的 14 kind 样本件 → part_params 读 → set_part_params 原值写回 → 官方键子元素 diff 归零 | `tests/test_official_part_fidelity.py`（矩阵参数化） | M |
| D2-2 | 嵌套 boolean 子件解析（`<boolean><parts>` Cutout 组合体）读端支持 | 官方案例（exA07-5 Duct_case）往返测试 | M |
| D2-3 | tessellation 量化对拍：官方 x_t → Parasolid 包络/体积 vs 我们 tess 同量，公差断言（±1%） | `tests/test_tess_quantitative.py`（≥10 官方件） | L |
| D2-4 | 残余差距（非量化断言所能覆盖的代理近似）逐项入册 NYI 或定公差声明 | NYI 更新 | S |

### D6 CW 条件（97% L2 → L3）

现状证据：ex4_e 单样本黄金 parity（手工构造链）、195/195 语料命令
逐字节单卡定档、§30 全参数族 UI→存储→发射闭环。
L3 缺口：**官方样本级**的端到端 parity 矩阵不存在（单样本 → 矩阵）。

| # | 工作项 | 产出 | 量 |
|---|---|---|---|
| D6-1 | 语料 parity 驱动器：官方 .cab 读入 → （无 CW 交互下）build_sdat → 与官方 .s 逐行 diff → 差异分类（缺段/多段/数值差/注释差） | `tools/corpus_parity.py` + `data/corpus_parity.json` | M |
| D6-2 | 差异归零波次：按分类逐类修（预期大头：官方 .s 的注释行/未发射段在无存储时不发——与官方空转语义差异） | parity 率从基线爬升，报告入 data | L |
| D6-3 | parity 矩阵进 CI：≥20 样本 parity 断言（阈值随波次收紧） | `tests/test_corpus_parity.py` | M |
| D6-4 | hub-B 展示型子页：随 diff 暴露的缺参数逐个接通（由 D6-1 驱动，不再是盲扫） | 随波次 | 滚动 |

### D12 导入导出（100% L2–L3 → L3）

现状证据：IFC 三 profile 导出 roundtrip（自产自销）、STEP/SAT 三分支
B 级、x_t/stl/ecxml 官方样本双向。
L3 缺口：导出侧**无几何恒等量化断言**；IFC 导出对拍缺官方参照。

| # | 工作项 | 产出 | 量 |
|---|---|---|---|
| D12-1 | IFC 导入→导出→再导入闭环量化对拍：体积/包络/质心公差断言（复用 D2-3 对拍基建） | `tests/test_ifc_quantitative.py` | M |
| D12-2 | x_t 导出（官方 x_t 成员为黄金）：写端 → Parasolid 回读 → 包络对拍（官方件往返） | `tests/test_xt_roundtrip_quant.py` | M |
| D12-3 | STEP/SAT 保持 B 级 CLI 分支（NYI #11 豁免不变），但 CLI 分支在位时跑同一量化对拍 | 条件测试（skip 无 CLI） | S |

---

## 2. 波次依赖与顺序

```
波次 1（基建）：D6-1 parity 驱动器 + D2-1 保真矩阵
        │            （两者共享官方 cab 语料装载基建）
        ▼
波次 2（归零）：D6-2 差异分类修 + D2-2 boolean 子件 + UI-1/2 字段矩阵
        │
        ▼
波次 3（量化）：D2-3 tess 对拍 + D12-1 IFC 闭环 + D12-2 x_t 往返
        │
        ▼
波次 4（收口）：UI-3 矩阵清零 + D6-3 CI 阈值 + UI-4 实机抽样
        │            （UI-4/D12-3 需 live-COM/CLI 窗口，随环境）
        ▼
   四域 L3 声明 + gap §0 更新 + NYI 复核
```

依赖要点：
- D6-1 是最高杠杆——它的差异清单直接驱动 D6-2/D6-4，避免盲扫 hub-B；
- D2-3 与 D12-1/2 共享量化对拍基建（体积/包络/质心三件套）；
- UI-4 与 D12-3 依赖外部环境（live COM / STPRE_STEP_CLI），排最后随窗口。

## 3. 量预估与「假装 L3」禁区

| 波次 | 预估 |
|---|---|
| 1 | ~1 会话 |
| 2 | ~2 会话（D6-2 差异量未知，parity 驱动器出数后修正） |
| 3 | ~1.5 会话 |
| 4 | ~1 会话 + 环境窗口 |

禁区（不许出现的达标姿势）：
1. **D6** 不许用"官方 .s 含注释/顺序差异"当 parity 失败的 blanket
   豁免——diff 必须逐类归因，语义差异才可入册；
2. **D2** 不许把 tessellation 近似说成 L3——量化公差断言必须真实
   写出并跑红过（先证明断言会失败再修到位）；
3. **UI** 不许把字段矩阵做成一次性文档——必须是可再生工具
   （gen_*.py 模式，扫描再生不丢账）；
4. **D12** 不许用 roundtrip（自产自销）冒充对拍——必须有官方参照
   侧（官方 x_t / 官方 IFC 导入结果）。

## 4. 达成后的双口径预期

四域 L3 达成 → 深度谱 L3 ×9 + L2 ×2 + L2–L3 ×0，深度侧全谱 ≥L2 且
格式/验证面全 L3；完整度维持（D2 99% 的残余与 D6 97% 的 hub-B 跟随
不阻塞 L3——L3 是深度口径，与完整度的具名缺口并行）。

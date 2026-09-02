# R4：19 个部分覆盖条件页 — 现状态与补法（§27 Phase 3 残项）

> 2026-09-02 审计。每项给出：现状锚点 / 补法 / 规模。

| # | 手册页（部分覆盖） | 现状 | 补法 | 规模 |
|---|---|---|---|---|
| 1 | DEM Particle-Generation | `_CwParticlePage` 通用粒子页已有；无 DEM 专属生成字段 | DEM tab：生成个数率/分布/释放位置 | S |
| 2 | DEM Particle-Restitution | wall restitution 已有（_CwParticlePage 反弹系数） | 补 DEM 专属材料对反弹 | S |
| 3 | Fan Boundary | `_CwFlowBoundaryPage._new_fan` 已有参数对话框 | 已 A；缺 P-Q 表注册 UI（pq_table 字段已有） | S |
| 4 | Fixed Pressure | `_CwStabilizationPage` Fixed Pressure 完整 | 已 A | — |
| 5 | Porous-Moisture Source | `_CwPorousPage` 有 Isotropic/Anisotropic | 补 moisture 子类型切换 | S |
| 6 | Porous-Plate Fin/Solid-Solid | porous 通用 | 子类型深字段 | S |
| 7 | Porous-Particle | porous 通用 | 粒子释放子页 | S |
| 8 | Particle Heat Source | 无专属对话框 | `_CwParticlePage` 加热源组 | S |
| 9 | Particle Fixed Velocity | 无专属 | 初速组（PCLE_CREATE VSP 复用） | S |
| 10 | Particle Motion User-defined | 无专属 | UDF 引用字段 | S |
| 11 | Particle Statistics | 无专属 | 统计输出组（Particle Variable L File 页已有） | S |
| 12 | Pathline Output | File Spec 页 PCL 行已有 | 已 A（PCL_RESTRICTION 发射 R2 后已闭合） | — |
| 13 | MO-Humidity | `_CwMovingBodyPage` 基础 | 移动体湿度边界组 | S |
| 14 | MO-Contact Face Heat Transfer | 热边界组已有 | 移动体接触热组 | S |
| 15 | MO-Mass Transfer | `_commit_mo_mass_transfer` 已有 | 已 A | — |
| 16 | MO-Co sim | `_ALWAYS_DISABLED` | 按 C 定档保留 | — |
| 17 | Volumetric Objective Function | `_CwTopologyOptiPage` 已有 | 已 A（TOPOPT 主卡） | — |
| 18 | Area Objective Function | 未见独立面积目标 | 面积目标组（P3-3 拓扑区域族） | M |
| 19 | Bubble Nucleus | 无 | 沸腾/气泡核生成组（`_CwBoilPage` 扩展） | M |

**结论**：19 项中 6 项已闭合（#3/4/12/15/16/17），9 项 S 级（单页组字段），
2 项 M 级（#18/#19，需新页面布局）。剩余 13 项合计 ≈1 个会话工作量。

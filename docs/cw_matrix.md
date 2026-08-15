# Condition Wizard 支持矩阵（C4）

> 来源：`cab_wizards._CwAnalysisTypesPage`（Analysis Types 25 项）+
> `cab_cwizard_pages`（Source/条件页）+ STpre Pre_eng 手册。
> 图例：`支持` = 有产品页 + 写回 + 测试；`子集` = 有页但类型/参数为 STpre 子集；
> `禁用` = 无产品页，显式禁用 + 诚实 tooltip（非伪成功）。
> 生成时间：2026-08-14（HEAD 见 git log）。

## 1. Analysis Types（25 项）

| 分析类型 | key | 状态 | 说明 |
|---|---|---|---|
| Flow / Turbulence | (always on) | 支持 | 基础分析；LES/ke/层流选项 |
| Heat | heat | 支持 | 传热 + 辐射绑定 |
| Humidity | humidity | 支持 | 湿度 + 材料 |
| Porous media | porous_media | 支持 | 各向同性/正交/粒子 |
| Radiation | radiation_analysis | 支持 | VF/Flux/Monte Carlo |
| Free surface | free_surface | 支持 | MARS/VOF |
| Evaporation (free surf.) | evaporation | 禁用(待 FS) | 依赖 free_surface |
| Boil/condensation | boil | 禁用(待 FS) | 依赖 free_surface |
| Diffusion | diffusion | 支持 | 2026-08-15 后新增产品页（物种数/扩散系数/Schmidt） |
| Plant canopy | plant_canopy | 禁用 | 无产品页 |
| Moving object | moving_body | 禁用 | 无产品页 |
| Thermoregulation model | jos_model | 支持 | 2026-08-15 后新增产品页（代谢率 met/着衣 clo） |
| Solar radiation | sun_light | 支持 | 2026-08-15 新增产品页（Location/Date-Time/Absorptance） |
| Lamp | artificial_light | 禁用 | 无产品页 |
| Reaction | reaction | 禁用 | 无产品页 |
| Ventilation efficiency | ventilation | 支持 | 2026-08-15 后新增产品页（龄/换气效率/去除效率） |
| Solidification/melting | fusion | 禁用 | 无产品页 |
| Marangoni convection | marangoni | 禁用 | 无产品页 |
| Topology optimization | topology_opti | 禁用 | 无产品页 |
| Particle | particle | 支持 | 2026-08-15 后新增产品页（交互模型/粒径/密度） |
| Air conditioner unit | aircon_model | 禁用 | 无产品页 |
| Electric current | current | 支持 | 2026-08-15 后新增产品页（电导率 S/m） |
| Electrostatic field | electrostatic | 支持 | 2026-08-15 后新增产品页（相对介电常数） |
| Phase change material | pcm | 禁用 | 无产品页 |
| MSC CoSim | msc_cosim | 禁用 | 无产品页 |
| BCI-ROM | bci_rom | 禁用 | 无产品页 |

统计：支持 13（含 Flow）/ 禁用(待 FS) 2 / 禁用 11。

## 2. Source Condition 值类型（子集）

| 页 | 类型 | STpre 对齐 |
|---|---|---|
| Volumetric | volumetric_force / volumetric_pressure_loss / heat_source / source_term | 子集 |
| Area | area_pressure_loss / area_heat_source | 子集 |
| Perforated Plate | — | 支持 |

> 完整 STpre Source 类型（含 time series / 函数 / diffusion source 等）待 C2 补齐。

## 3. 条件页（~26 页）

Analysis Types / Basic / Fluid / Flow / Heat / Humidity / Porous / Initial /
4×Boundary Condition / Source / Fixed / Control(5) / Output(4) / File /
Condition List / Confirm。

已实现写回的深度页：Source（Volumetric/Area/Perforated + 面创建/多选）、
Humidity、Porous Media、Radiation Grouping、Initial（Power-law/Enclosure
A/B/eps）。高级物理（§1 禁用项）无产品页。

## 4. 解锁顺序（建议，C3）

Solar → Particle → Diffusion → Ventilation → Reaction → …（按产品需求）。

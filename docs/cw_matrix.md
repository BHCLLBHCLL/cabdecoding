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
| Plant canopy | plant_canopy | 支持 | 2026-08-15 COM 探针对齐：analysis_etc/plant_resistance（STpre SetAnalysisType "plant_resistance"）；冠层条件在 Source 页 |
| Moving object | moving_body | 支持 | 2026-08-15 COM 探针对齐：analysis_set moving_body=1/2（含传热）+ moving_body_file/list_position/gap_filling；运动定义属零件属性 |
| Thermoregulation model | jos_model | 支持 | 2026-08-15 后新增产品页（代谢率 met/着衣 clo） |
| Solar radiation | sun_light | 支持 | 2026-08-15 新增产品页（Location/Date-Time/Absorptance） |
| Lamp | artificial_light | 支持 | 2026-08-15 后新增产品页（点/线/面光源 + 光通量） |
| Reaction | reaction | 支持 | 2026-08-15 后新增产品页（单步/多步 + 速率） |
| Ventilation efficiency | ventilation | 支持 | 2026-08-15 后新增产品页（龄/换气效率/去除效率） |
| Solidification/melting | fusion | 支持 | 2026-08-15 后新增产品页（固/液相线 + 潜热） |
| Marangoni convection | marangoni | 支持 | 2026-08-15 COM 探针对齐：analysis_etc/marangoni/temp_coeff（N/(m·K)）+ marangoni 条件值 |
| Topology optimization | topology_opti | 支持 | 2026-08-15 COM 探针对齐：analysis_etc/topology_optimize 全 48 项 STpre 默认块 + 关键参数 UI |
| Particle | particle | 支持 | 2026-08-15 后新增产品页（交互模型/粒径/密度） |
| Air conditioner unit | aircon_model | 支持 | 2026-08-15 COM 探针对齐：analysis_set/aircon_model T/F（官方模板 tag）；AC 机组为零件模型 |
| Electric current | current | 支持 | 2026-08-15 后新增产品页（电导率 S/m） |
| Electrostatic field | electrostatic | 支持 | 2026-08-15 后新增产品页（相对介电常数） |
| Phase change material | pcm | 支持 | 2026-08-15 后新增产品页（熔点 + 潜热） |
| MSC CoSim | msc_cosim | 禁用(scFLOW) | scFLOW-only 连成分析（scFLOW 工程设置中配置）；scSTREAM .cab 不承载 |
| BCI-ROM | bci_rom | 禁用(scFLOW) | scFLOW-only ROM 导出；scSTREAM .cab 不承载 |

统计：支持 22（含 Flow）/ 禁用(待 FS) 2 / 禁用(scFLOW-only) 2。

> STpre 存储实证（2026-08-15 COM 探针 tools/probe_cw_types.py）：
> SetAnalysisType("plant_resistance"/"marangoni"/"topopt"/"move_body"/"aircon", "T")
> 保存后写 analysis_etc/plant_resistance、analysis_etc/marangoni/temp_coeff、
> analysis_etc/topology_optimize(48 项默认)、analysis_set/moving_body=1(2)
> + moving_body_file / moving_body_option / list_position / gap_filling；
> pcm/es_field 写 analysis_etc/phase_change_material /
> analysis_etc/partcile_echarge（2026-08-15 已迁移：PCM 页写
> phase_change_material 节、Electrostatic 页写 partcile_echarge 1|2 +
> 「每循环/仅起始」时机，Analysis Types 勾选联动同一存储，legacy 平铺
> 标记保留同步）。

## 2. Source Condition 值类型（子集）

| 页 | 类型 | STpre 对齐 |
|---|---|---|
| Volumetric | volumetric_force / volumetric_pressure_loss / heat_source / source_term / time_series / diffusion | 支持 |
| Area | area_pressure_loss / area_heat_source | 子集 |
| Perforated Plate | — | 支持 |

> 2026-08-15 COM 实证：expression 热源 = <express> 计算函数（kind
> VENT_source）+ value/source@type=express 引用；diffusion source =
> SetDiffusionCondition(name, no, "source", amount, 0) →
> <value type="diffusion"><kind>source</kind><no>N</no><diff_source unit>。
> diffusion 边界条件（"diffusion"/"transfer" → kind boundary +
> diff_param1/diff_param2）已探明，编辑器为后续项。

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

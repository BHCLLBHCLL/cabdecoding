# cab_gui 详细设计（对齐 scSTREAM Pre / STpre）

> 日期：2026-08-03  
> 参考：
> 1. STpre 实机 UI 截图（Tree/List + Control + Draw + Message）
> 2. Cradle CFD 2025.2 *scSTREAM User's Guide Preprocessor Reference*  
>    `C:\Program Files\Cradle\CradleCFD2025.2\Manuals\ST\HTML\Pre_eng\index.html`
> 3. `pphdecoding/pph_gui.py` + `nav_panels.py`（菜单/工具栏/`AppIcons`/`PaneFrame`/Message 实现范式）
> 4. 本仓库现有 `cab_gui.py`（P4 四窗格骨架）与 `DEV_SUMMARY.md` §P4

---

## 1. 设计目标与边界

### 1.1 目标

把 `cab_gui` 从当前「简易四 Dock」升级为 **STpre 主界面同构** 的 CAB 查看/轻量编辑器：

| 能力 | 目标 |
|------|------|
| 打开 / 另存 CAB | 对齐 `[File]-[Open/Save/Save As]`，Ctrl+O |
| 模型浏览 | `[Layout of Parts]` 树 + 勾选显隐（对齐 Tree/List View） |
| 条件浏览 | `[Conditions]` 标签列出 value / condition / region |
| 属性编辑 | 部件名 / 材料 / 颜色 / 变换摘要；写回 XML→重打包 |
| 3D 绘制 | Draw Window：部件盒 / 域框 / 线框·着色·半透明 / Fit·Reset |
| 导出 | `[File]-[Export]` → `.s` / `.xemt`（已有管线） |
| 日志 / 状态 | Message Window + Status Bar（坐标 / 选择模式） |

### 1.2 明确不做（标记 NYI，菜单保留入口）

完整 CAD 建模、Sketch 编辑、布尔、网格生成交互、Wizard 全页、Solver/Post 启动、库部件创建等。  
菜单项与工具栏按钮 **保留并对齐手册命名**，触发后写入 Message：`[name] not available in cab viewer (STpre-only / not yet mapped).`——与 `pph_gui._nyi` 一致。

---

## 2. 参考对照

### 2.1 STpre 主布局（截图 + 手册 *Layout / Window*）

```
┌─ Menu: File Edit View Part Wizard Mesh Option Help ──────────────┐
├─ [File] [Edit] [Parts] … … [Mouse] 工具栏 ──────────────────────┤
├────────────────┬─────────────────────────────────────────────────┤
│ Tree/List View │                                                 │
│ ┌ Layout of    │              Draw Window                        │
│ │ Parts      │                                                 │
│ │ Conditions ┘ │   网格 / 域框 / 部件 / 全局轴 / 草图轴            │
├────────────────┤                                                 │
│ Control Window │                                                 │
│ Show/Select    ├─────────────────────────────────────────────────┤
│ Sketch Layer   │ Message Window                                  │
│ Library …      │                                                 │
├────────────────┴─────────────────────────────────────────────────┤
│ Status: (x,y,z) ……  Part | Global mode                           │
└──────────────────────────────────────────────────────────────────┘
```

手册窗口清单（*Window* TOC）：

- **Draw window** — 主视口、部件右键菜单、1-button 鼠标模式
- **Tree/List View Window** — `Layout of Parts` / `Condition Setting`
- **Control Window** — `Show/Select` · `Sketch` · `Layer` · `Library` · `Active Part`
- **Status bar** — 左：提示/坐标；右：选择模式 / 操作模式 / 选择目标 / 新建组名
- **Message**（Environment Setting → Message Window）— 操作日志

### 2.2 与 pph_gui（scFLOWpre）差异

| 项 | STpre / cab_gui | scFLOWpre / pph_gui |
|----|-----------------|---------------------|
| 左侧主导航 | **无**独立 Navigation；流程在菜单/Wizard | Navigation：Prepare Parts / Build Analysis Model |
| 左上 | Tree/List View | Tree（Part Tree + Archive） |
| 左下 | **Control Window**（显示/选择） | Property + Status |
| 菜单 | File Edit View **Part Wizard Mesh** Option Help | File Edit Select View Condition Execute Option Help |
| 几何 | 结构化网格 + Parasolid 部件 | 非结构 OCT/GPH + MDL |

**复用 pph，不照搬布局**：图标引擎、`PaneFrame`、Message、样式表、工具栏构造、`_nyi`、Archive 成员树、离屏测试模式。

### 2.3 现状 `cab_gui.py` 差距

| 已有 | 缺失（本设计补齐） |
|------|-------------------|
| 左 Navigation Dock（非 STpre） | STpre 菜单 8 项 + 分组工具栏 |
| Model Tree 扁平部件列表 | `Layout of Parts` 层级（Domain / Group / Part / Region / Others） |
| 右 Property Dock | Control Window（Show/Select + Property 标签） |
| 中央 VTK | 坐标三联、网格底、域框开关、半透明 |
| 无 Message / 弱 Status | Message Window + 多段 Status Bar |
| 文字工具栏 | `AppIcons` 矢量图标 + TextUnderIcon |

---

## 3. 总体布局规格

### 3.1 窗体

- 类名：`CabViewer(QMainWindow)`（保留）
- 标题：`cabdecoding — STpre layout`（加载后追加 ` — {project}.cab`）
- 默认尺寸：`1600×900`（对齐 pph）
- 中央控件：**水平 `QSplitter`**
  - 左：垂直 splitter → Tree/List View | Control Window（比例约 3:2，默认 420/280）
  - 右：垂直 splitter → Draw | Message（比例约 5:1，默认 640/140）
- 禁止再使用「Navigation 独占左列」；cab 专属入口并入 Tree 的 **Archive** 标签与 File 菜单。

建议拉伸因子：`main=[0,1]`，左列最小宽 240，右列最小宽 480。

### 3.2 Pane 边框（复用 pph `PaneFrame`）

每个分区外套 `PaneFrame(title, body)`：

- `#PaneTitleBar`：灰底标题条（Tree/List View、Control、Draw Window、Message）
- `#PaneBody`：白底内容
- 样式表直接移植 `pph_gui._apply_style` 中 `#PaneFrame` / `#PaneTitleBar` / `QToolBar` / `QMenuBar` 段，背景 `#e8e8e8`。

### 3.3 模块拆分（建议文件）

| 文件 | 职责 |
|------|------|
| `cab_gui.py` | `CabViewer`：菜单/工具栏/布局/信号总线 |
| `cab_icons.py` | 从 pph 移植/裁剪 `AppIcons` + `CAB_NAV_ICONS` |
| `cab_panes.py` | `PaneFrame`、`MessageWindow`、`TreeListView`、`ControlWindow`、`PropertyPanel`、`StatusBarWidget` |
| `cab_view3d.py` | Draw Window：VTK 封装、显示模式、拾取钩子 |
| `cab_actions.py` | Action 表（id → slot / NYI），供菜单与工具栏共享 |

短期可先全部落在 `cab_gui.py`，按 pph 同文件大类组织；体量超 ~2k 行再拆。

---

## 4. 菜单设计（对齐手册 Menu Guide）

实现策略：**全量菜单骨架 + 分级启用**。

图例：✅ 实现　◐ 部分　⬜ NYI（记日志）

### 4.1 File(&F)

| 项 | 快捷键 | 状态 | 行为 |
|----|--------|------|------|
| Open… | Ctrl+O | ✅ | 打开 `.cab` |
| Save | Ctrl+S | ✅ | 写回当前路径（若无则 Save As） |
| Save As… | Ctrl+Shift+S | ✅ | 重打包 CAB |
| Import… | | ✅ | x_t 导入（独立成员 + `<body_files>` 登记 + 自动三角化）；STL 等格式后续扩展 |
| Export… | Ctrl+E | ✅ | 对话框：S File / XEMT File（手册 Export 子集） |
| Print | | ✅ | Draw 窗口截图预览 + Save PNG + 系统打印（QPrinter） |
| Execute Solver | | ✅ | 确认后导出临时 `.s/.xemt` 并启动 `stsol_Dx64net.exe` |
| Execute Post | | ✅ | 确认后启动 `scPOST_Dx64net.exe` |
| Recent Files | | ◐ | `QSettings` 最近 8 个 |
| Exit | Alt+F4 | ✅ | |

### 4.2 Edit(&E)

| 项 | 状态 | 映射 |
|----|------|------|
| Undo / Redo | ✅ Ctrl+Z/Y | XML 快照栈（50 层），覆盖导入/域/部件/网格/向导等全部改动 |
| Deletion of Parts | ✅ | 多选删除对话框（移除 `<parts>`/`<element>`/关联 condition） |
| Reset Computational Domain | ✅ | STpre 风格 [Edit Computational Domain] 对话框（Scale + Attribute/Condition） |
| Group | ✅ | 建组/移动部件对话框（空组名=回到根） |

### 4.3 View(&V)

| 项 | 状态 | 行为 |
|----|------|------|
| Fit to DrawWindow | ✅ Ctrl+F | `ResetCamera` 到可见部件 |
| Reset DrawWindow | ✅ | 相机到计算域整体 |
| XY / XZ / YZ Plane | ✅ | 正交视图 |
| (Toolbar) File/Edit/Parts/Mouse/Display | ✅ | `QToolBar.setVisible` |
| Show Message Window / Show Status Bar | ✅ | checkable 开关 |

### 4.4 Part(&P)

对齐手册标准件入口（Cube/Cylinder/Sphere/Panel）。  
✅ Cuboid/Cylinder/Sphere/Panel：`cab_parts.CreatePartDialog` 创建对话框，
写入 `<parts type="cube|cylinder|sphere|panel">` + 几何参数，生成 TessPart
3D 预览并参与 Meshing；重开时按 XML 参数重建几何（不依赖 x_t）。
✅ Sketch Part：`cab_sketch.SketchPartDialog`（Panel/Extrusion，点序列/
矩形/圆），基于 sketch plane 生成几何并持久化。
⬜ Fan：保持 NYI（记日志）。

Sketch plane：Control Window 新增 [Sketch] 页（原点/U·W 向量/网格
Delta·Snap·范围/Gridsnap·Minus），Reset（Zmin）/Fit to computational
domain/Update；Show/Select 的 Sketch plane 与 Axis (Sketch) 开关显示
平面网格与 U/V/W 轴（`cab_vtk.sketch_plane_actor`）。

### 4.5 Wizard(&W)

| 项 | 状态 | 行为 |
|----|------|------|
| Initial Setting… | ✅ | STpre Initial Wizard（`cab_wizards.InitialWizard`）：Project → Import CAD Data → Computational Domain → Analysis Type → Initial Value/Gravity → Purpose of Analysis → Conditions for Computational Domain Boundary → Confirm Settings；写回 `project`/`analysis_region`/`analysis_set`/`condition`+`value` |
| Condition Setting… | ✅ | STpre Condition Wizard 子集（`cab_wizards.ConditionWizard`）：左导航树 + Analysis Types / Basic Settings / Fluid Region / Flow / Heat / Initial Condition / BC(Flow·Wall·Thermal·Symmetrical) / Analysis Control / File Specification / Condition List / Setting Confirmation |

### 4.6 Mesh(&G)

| 项 | 状态 | 行为 |
|----|------|------|
| Gridding… | ✅ | `Mesh:Set division` 六标签对话框（Basic Setting / Parameter / Detail meshing / Edit / Deletion / Others） |
| Meshing | ✅ | 基于 `mesh_block` + CAD 曲面生成 `element`（状态栏进度） |
| Checking Parts Interferences | ✅ | `InterferenceDialog`：Select 部件 + Interference/Contact/Separation 列表 + Separation only + Confirm/Reconstruct |
| Editing Mesh… | ✅ | `EditMeshDialog`：Active block / I·J·K 层选择 / `->Effective`·`->Ineffective` 编辑单元属性 |
| Showing Element Cross-Section… | ✅ | `SectionDialog`：Axis + 滑块 + Show/Hide fluid，Draw 窗口实时显示截面 |
| Checking S-File… | ✅ | `SFileCheckDialog`：Open S file + 树形列表 checkbox 控制 3D 显隐 |

### 4.7 Option(&O)

| 项 | 状态 | 行为 |
|----|------|------|
| (Mouse) | ◐ | Cradle 3-Button / 1-Button 切换（见 §7） |
| Environment Settings | ✅ | `OptionsDialog`（Basic/Parts/Mesh/Message/User Interface），QSettings 持久化 + 即时生效 |
| Detailed Program Settings | ✅ | 同一 `OptionsDialog`（详细标题），覆盖手册 13 页的子集 |

### 4.8 Help(&H)

| 项 | 状态 | 行为 |
|----|------|------|
| User's Guide | ✅ | `os.startfile` → ST `Pre_eng\index.html` |
| Version | ✅ | cabdecoding git 短哈希 / Python / Qt / VTK / pskernel 内核版本 |
| About | ✅ | 版本 + 布局说明 |

---

## 5. 工具栏设计

风格对齐 pph：`ToolButtonTextUnderIcon`，图标 22px，`AppIcons` 绘制。

### 5.1 [File] Toolbar（手册 File Toolbar）

| 按钮 | 图标名 | 动作 |
|------|--------|------|
| Open | `open` | Open |
| Save | `save` | Save |
| Export | `xml` 或新建 `export` | Export .s/.xemt |
| Reload | `reload` | 重新加载当前 cab |

### 5.2 [Edit] Toolbar（手册 Edit Toolbar 子集）

| 按钮 | 图标名 | 动作 |
|------|--------|------|
| Undo / Redo | 新建 | NYI |
| XY / XZ / YZ | 新建 `plane_xy` 等 | 正交视图 |
| Fit | `fit` | Fit to DrawWindow |
| Reset | `show_all` | Reset DrawWindow |
| Rubber | 新建 `rubber` | 框选（后期） |

### 5.3 [Parts] Toolbar

手册完整标准件列表过长。cab **第一期只放一行占位**（Cube / Cylinder / Sphere / Panel）全部 NYI，或 View→隐藏该栏。  
不实现「By Dialog / By Mouse / Sketch coordinate」切换。

### 5.4 [Mouse] Toolbar（1-button 模式时显示）

| 按钮 | 动作 |
|------|------|
| Select | 选择模式 |
| 3D Rotate | 旋转 |
| Pan | 平移 |
| Zoom | 缩放 |

默认推荐 **Cradle 3-Button**（中键旋转、右键缩放等，见手册 *Table of Mouse Operations*），此时 Mouse 工具栏可隐藏（与 STpre 一致）。

### 5.5 [Display] Toolbar（pph 实践，STpre 对应 Control Drawing mode）

`QComboBox`：`Line` / `Shading` / `Translucent` —— 与 Control Window 单选双向同步。

---

## 6. Tree/List View Window

### 6.1 标签页

1. **Layout of Parts**（主）  
2. **Conditions**（手册 Condition Setting 列表）  
3. **Archive**（cab 扩展，来自 pph Member Tree：`ex4_e.xml` / `_ex4_e_property.xml` / `_ex4_e_all.x_t`）

### 6.2 Layout of Parts 树结构

对齐截图与手册：

```
▼ Parts                              [checkbox]
  ▼ Computational_Domain
      Domain(cuboid)                 → 打开域属性
      RootBlock                      → mesh_block 摘要
  ▼ {GroupName}                      （来自 stpre groups）
      {PartName}                     → PartInfo；勾选=3D 显隐
  ▼ Region
      Xmin / Xmax / Ymin / Ymax / Zmin / Zmax
      {自定义 Part Face / region}
  ▼ Others
      Drawing / Image / Gerber（无数据则空）
```

数据源：`StpreModel.groups/parts/regions/mesh_block/analysis_region`。

### 6.3 勾选语义（手册）

- 部件 checkbox → actor 显隐（已有）
- 组 checkbox → 组内全部部件
- Domain frame / Mesh 等图层改由 **Control → Drawing ON/OFF** 控制，不在树上重复（除非手册要求）

### 6.4 右键菜单（一期子集）

| 菜单 | 状态 |
|------|------|
| Refer to Part | ✅ 选中并聚焦 Property |
| Display Part / Hide Part | ✅ |
| Show Parts List Dialog | ◐ 简单表格对话框 |
| Delete Part | ◐ |
| Create Group / Search Part / Extract… | ⬜ |
| Reset computational domain | ◐ 只读 |
| Edit block | ◐ 只读网格参数 |

### 6.5 Conditions 标签

列表/树：

- Values（`model.values()`）
- Conditions（`model.conditions()`）
- 选中 → Control/Property 显示可编辑参数（`set_value_param`）

---

## 7. Control Window

标签顺序对齐手册，按实现优先级裁剪：

| 标签 | 一期 | 内容 |
|------|------|------|
| **Show/Select** | ✅ | 见下 |
| **Property** | ✅ | cab 扩展：选中项键值编辑（替代 STpre 多数字对话框） |
| **Library** | ◐ | 材料库只读列表（`PropertyModel.material_names`） |
| Sketch | ⬜ | 隐藏或 NYI 页 |
| Layer | ⬜ | 隐藏或 NYI 页 |
| Active Part | ⬜ | |

### 7.1 Show/Select（手册原文控件）

**Drawing ON/OFF**（`QGroupBox` + checkbox）：

| 控件 | 默认 | 绑定 |
|------|------|------|
| Part | ON | 全部部件图层 |
| Mesh Block | OFF | 网格块线框（若有） |
| Condition | OFF | 条件箭头（后期） |
| Sketch plane | OFF | |
| Domain frame | ON | `cab_vtk.domain_frame` |
| Mesh | OFF | CXYZ 网格线稀疏显示（可选） |
| Axis (Global) | ON | VTK AxesActor |
| Axis (Sketch) | OFF | |
| Origin | ON | |
| Aspect ratio | OFF | |

**Drawing mode**（互斥，对齐手册）：`Line` | `Shading` | `Translucent`

**Target of selection**：`Part` | `Face` | `Vertice` | `Domain boundary`  
一期仅 **Part** 生效；其余写入 Status 并 NYI。

### 7.2 Property 标签

| 选中类型 | 可编辑字段 |
|----------|------------|
| Part | 名称、材料（combo←材料库）、颜色 RGBA、显示属性只读（体积/类型） |
| Region | 名称只读；关联 condition 名 |
| Value/Condition | 关键参数文本（`set_value_param`） |
| Project / Domain | 只读摘要 |
| Material entry | 密度/导热等（`PropertyModel.set_entry_value`） |

底部 **Apply** / **Revert**；成功后 Message 提示「另存为 cab 后持久化」。

---

## 8. Draw Window

### 8.1 视觉

- 背景：浅灰 `#ededf0`（贴近 STpre）
- 可选地面网格（XY，随域范围）
- 左下角：方向三联 `vtkOrientationMarkerWidget`（X/Y/Z）
- 域框：蓝色线框（现有）
- 部件：盒体或后续 x_t 面片；颜色来自 XML

### 8.2 交互

| 模式 | 3-Button（默认） | 1-Button |
|------|------------------|----------|
| 旋转 | 中键拖 | Mouse 工具栏 3DRotate |
| 平移 | 中+右 或 Shift+中 | Pan |
| 缩放 | 右键拖 / 滚轮 | Zoom |
| 选择 | 左键 | Select |

拾取：左键高亮部件 → 同步 Tree 选中 + Property。

### 8.3 右键（一期）

Refer to Part / Hide Part / Display parts only / Fit — 其余 NYI。

### 8.4 堆叠页（可选，pph 经验）

`QStackedWidget`：`draw` | `dashboard`（成员统计）| `text`（XML 只读/高亮）。默认 draw。

---

## 9. Message Window & Status Bar

### 9.1 Message

移植 `pph_gui.MessageWindow`：

- 只读 `QPlainTextEdit`，`maximumBlockCount=2000`
- 格式：`[HH:MM:SS] LEVEL: msg`
- 级别：INFO / WARN / ERROR
- 打开/保存/导出/NYI/异常均写入

### 9.2 Status Bar（手册四段信息）

| 区 | 内容 |
|----|------|
| 左 | 菜单 tip **或** 指针坐标 `(x, y, z)` |
| 右1 | 选择模式：`Part` / `Mesh` / `Region` |
| 右2 | 操作模式：`Selection` / `Edit` / … |
| 右3 | 选择目标：`Part` / `Face` |
| 右4 | 当前插入组名或 `Global mode` |

实现：`QStatusBar` + 多个 `QLabel` permanent widget。

---

## 10. 图标体系（移植 pph `AppIcons`）

### 10.1 直接复用

`open` `save` `reload` `part` `folder` `group` `region` `project` `mesh` `fit` `show_all` `display` `xml` `script` `snapshot` `dashboard` `param` `section` `body` `fluid`

### 10.2 cab/STpre 新增绘制

| 名 | 用途 |
|----|------|
| `export` | 导出 S/XEMT |
| `domain` | Computational Domain |
| `cube` `cylinder` `sphere` `panel` | Parts 工具栏 |
| `select` `rotate` `pan` `zoom` | Mouse 工具栏 |
| `plane_xy` `plane_xz` `plane_yz` | 正交视图 |
| `condition` | Conditions 树 |
| `library` | 材料库 |
| `wire` `shade` `glass` | 显示模式（可选） |

缓存键 `(name, size)`，与 pph 相同。

---

## 11. 数据与命令流

```
.cab ─► CabArchive ─► StpreModel + PropertyModel + x_t
                │
                ├─ TreeListView.populate()
                ├─ ControlWindow.sync_layers()
                └─ View3D.rebuild(part_boxes, domain_frame)

Tree/Draw 选中 ─► PropertyPanel.set_target()
Apply ─► StpreModel / PropertyModel 突变
Save ─► serialize XML ─► archive.to_bytes() ─► 写文件
Export ─► build_sdat / build_emt
```

脏标记：`self._dirty`；标题加 `*`；关闭前提示保存。

---

## 12. 实现分期

### M1 — 骨架对齐（优先）

1. 替换 Dock 为 STpre splitter 布局 + PaneFrame  
2. 菜单 8 顶栏 + File/Edit/Display 工具栏 + AppIcons  
3. Tree：Layout of Parts 层级 + Conditions + Archive  
4. Control：Show/Select + Property  
5. Message + 多段 Status  
6. Draw：Shading/Line/Translucent、Domain/Axis 开关、Fit/Reset/正交  
7. 离屏测试更新（`tests/test_gui.py`）

### M2 — 编辑闭环

- 材料 combo、颜色、重命名、条件参数  
- Save / dirty / Recent  
- Export 对话框（S / XEMT）  
- 右键 Hide/Show/Refer  

### M3 — 增强

- Mesh 网格线预览、S-File check 报告  
- Wizard 只读摘要  
- 1-button Mouse 工具栏  
- Dashboard / XML 文本页  
- 剪贴板截图  

### 不做（长期）

Parts 真实创建、Sketch、布尔、完整 Condition Wizard、启动 Solver/Post。

---

## 13. 测试计划

| 用例 | 断言 |
|------|------|
| `test_build_ui_headless` | 无 VTK 也可构建；存在 menu File/Part/Wizard/Mesh |
| `test_layout_panes` | 找到 Tree/List、Control、Message、Draw 标题 |
| `test_open_ex4e` | Layout 树含 Computational_Domain、Region、部件数=模型 |
| `test_visibility_checkbox` | 取消勾选 → actor 不可见 |
| `test_drawing_mode` | Line/Shading/Translucent 切换不抛错 |
| `test_edit_apply_save` | 改名 → Save As → 重开一致 |
| `test_export_actions` | Export 写出 .s/.xemt |
| `test_nyi_logs` | 点击 NYI 菜单 → Message 含 WARN |

---

## 14. 与手册条目的追溯表（核心）

| 手册页 | cab_gui 落点 |
|--------|--------------|
| *Layout* | §3 主分割 |
| *Tree/List View Window* | §6 |
| *Control Window - Show/Select* | §7.1 |
| *Draw window* | §8 |
| *Status bar* | §9.2 |
| *File / Edit / View / … menu* | §4 |
| *File / Edit / Parts / Mouse Toolbar* | §5 |
| *Table of Mouse Operations* | §8.2 |
| *File - Export* | §4.1 Export |
| *File - Open* | §4.1 Open |

完整 Wizard/Part 子页仅作菜单占位，不逐页实现。

---

## 15. 验收标准

1. 冷启动窗口分区与 STpre 截图一致（左树+控制 / 中绘制 / 底消息 / 顶菜单工具栏）。  
2. 打开 `tests/ex4_e.cab`：树层级正确，域框可见，部件可显隐。  
3. 修改部件材料 → Apply → Save As → 重开数值一致。  
4. Export 的 `.s`/`.xemt` 通过现有 `test_sxemt_export` 语义。  
5. Help → User's Guide 能打开本地 ST Pre HTML。  
6. `pytest tests/test_gui.py` 全绿。

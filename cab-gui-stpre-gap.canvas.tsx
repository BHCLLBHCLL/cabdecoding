import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  TodoList,
  UsageBar,
  useHostTheme,
} from "cursor/canvas";

type Depth = "impl" | "partial" | "chrome" | "missing";

const AREA_COVERAGE = [
  {
    area: "File",
    stpre: 11,
    ui: 11,
    useful: 9,
    note: "Import/Export 格式子集；无 3DfindIT",
  },
  {
    area: "Edit",
    stpre: 24,
    ui: 24,
    useful: 12,
    note: "菜单齐全；半数 CAD 为 AABB/chrome",
  },
  {
    area: "View",
    stpre: 13,
    ui: 13,
    useful: 13,
    note: "相机/工具栏齐；缺 Setting/Dialog 项",
  },
  {
    area: "Part",
    stpre: 30,
    ui: 14,
    useful: 14,
    note: "基础体+风扇+草图；缺热设计专用件",
  },
  {
    area: "Wizard",
    stpre: 2,
    ui: 2,
    useful: 2,
    note: "IW 强；CW 导航约 26/150+ 页",
  },
  {
    area: "Mesh",
    stpre: 6,
    ui: 6,
    useful: 6,
    note: "表面齐；multiblock/cut-cell 弱",
  },
  {
    area: "Option",
    stpre: 10,
    ui: 4,
    useful: 4,
    note: "缺 Distance/Cut Cell/Selection 等",
  },
  {
    area: "Help",
    stpre: 2,
    ui: 3,
    useful: 3,
    note: "含 Version/About",
  },
];

const DEPTH_ROWS: {
  area: string;
  item: string;
  depth: Depth;
  gap: string;
}[] = [
  {
    area: "File",
    item: "Open / Save / New",
    depth: "impl",
    gap: "冷启动 Initial Wizard 已对齐",
  },
  {
    area: "File",
    item: "Import",
    depth: "partial",
    gap: "有 XT/STL/STEP/SAT；缺 MDL/DXF/OBJ/IDF/主流 CAD",
  },
  {
    area: "File",
    item: "Export",
    depth: "partial",
    gap: "仅 .s/.xemt；缺 XT/STL/Neutral/XML",
  },
  {
    area: "File",
    item: "Execute Solver / Post",
    depth: "partial",
    gap: "能启动；Kicker/环境文件不完整",
  },
  {
    area: "Edit",
    item: "Undo/Redo / Group / Deletion / Reset Domain",
    depth: "impl",
    gap: "快照 Undo ≠ Parasolid 历史",
  },
  {
    area: "Edit",
    item: "Mirror / Align / Place / Conversion / Sweep / Cutting",
    depth: "partial",
    gap: "变换/包围盒近似，非完整 B-rep",
  },
  {
    area: "Edit",
    item: "Boolean / Edit Solid / Wrap / Simplify / Paneling / Wiring",
    depth: "chrome",
    gap: "对话框齐；内核级几何未接通",
  },
  {
    area: "View",
    item: "Fit / Planes / Toolbars / Message",
    depth: "impl",
    gap: "—",
  },
  {
    area: "View",
    item: "Clipping / Hide / Thermal Display / Part lists",
    depth: "missing",
    gap: "Setting + Dialog 子菜单缺失",
  },
  {
    area: "Part",
    item: "Cuboid…Pipe / Fans / Sketch",
    depth: "impl",
    gap: "Tess 原语，非完整 Parasolid 实体编辑",
  },
  {
    area: "Part",
    item: "Enclosure / Fin / Peltier / AC / Diffuser…",
    depth: "missing",
    gap: "约 16+ 专用件未进菜单",
  },
  {
    area: "Wizard",
    item: "Initial Setting",
    depth: "partial",
    gap: "6 步可用；CAD Import/边界自动较好",
  },
  {
    area: "Wizard",
    item: "Condition Setting",
    depth: "partial",
    gap: "核心 BC 有；湿度/辐射/多孔等深度不足",
  },
  {
    area: "Mesh",
    item: "Gridding / Meshing / Interference…",
    depth: "partial",
    gap: "规则逼近中；cut-cell/multiblock 弱",
  },
  {
    area: "Option",
    item: "Environment / Detailed",
    depth: "partial",
    gap: "5 页 vs STpre ~13 Environment 页",
  },
  {
    area: "Option",
    item: "Cut Cell / Distance / Reference / Selection / Viewer",
    depth: "missing",
    gap: "未挂菜单",
  },
  {
    area: "Control",
    item: "Face/Vertex/Edge 选择目标",
    depth: "chrome",
    gap: "多为 _nyi；阻塞 Edit/Measure",
  },
];

const CROSS_CUTTING = [
  {
    gap: "Parasolid 忠实 Edit CAD（Boolean/Solid/Wrap/Simplify/Paneling）",
    severity: "Blocker",
    why: "当前 AABB/chrome，无法做真实 CAD 准备",
  },
  {
    gap: "交互式面/边拾取管线",
    severity: "High",
    why: "Face Paneling、Distance、Reference、Sweep 依赖",
  },
  {
    gap: "Import/Export 格式矩阵",
    severity: "High",
    why: "工业 CAD 进出不齐",
  },
  {
    gap: "Meshing cut-cell / multiblock / 金标占用",
    severity: "High",
    why: "求解前网格质量与 STpre 仍有差",
  },
  {
    gap: "Condition Wizard 深度（~150 页）",
    severity: "High",
    why: "产品完整度；Basic Exercise 可先子集",
  },
  {
    gap: "View Setting/Dialog + Option 工具菜单",
    severity: "Medium",
    why: "显示/测量工作流缺口",
  },
  {
    gap: "Part 热设计专用库",
    severity: "Medium",
    why: "电子散热场景常用",
  },
  {
    gap: "Solver/Post 产品化集成",
    severity: "Medium",
    why: "启动可用，环境/重启选项不足",
  },
  {
    gap: "Undo 与 Parasolid 会话一致性",
    severity: "Medium",
    why: "XML 快照无法回滚内核实体",
  },
  {
    gap: "i18n / 3DfindIT 等",
    severity: "Low",
    why: "非核心工作流",
  },
];

const MILESTONES = [
  {
    id: "M24",
    title: "Edit 内核脊柱",
    status: "pending" as const,
    items: [
      "pskernel Boolean unite/subtract/intersect",
      "Facet reconstruct → PK_TOPOL_facet_2 重三角化",
      "Draw 面拾取 → Flip / Paneling / Sweep",
    ],
  },
  {
    id: "M25",
    title: "选择 / 测量 / View Setting",
    status: "pending" as const,
    items: [
      "Control Target: Face / Vertex / Edge",
      "Option Distance + Reference",
      "View Hide/Display All + Clipping",
    ],
  },
  {
    id: "M26",
    title: "Import/Export 核心格式",
    status: "pending" as const,
    items: [
      "Import: MDL / DXF / OBJ（+ IGES 若 OCC）",
      "Export: XT（活动部件）/ STL / Property XML",
      "格式矩阵回归测试",
    ],
  },
  {
    id: "M27",
    title: "Mesh 保真",
    status: "pending" as const,
    items: [
      "Multiblock create/insert；Gridding Select 拾取",
      "Meshing 与金标 cab 占用差收敛",
      "Cut Cell Option MVP",
    ],
  },
  {
    id: "M28",
    title: "Condition Wizard 扩展",
    status: "pending" as const,
    items: [
      "Humidity / Source 细节 / Porous",
      "Radiation grouping 优先",
      "未实现物理显式 chrome + 测试写回",
    ],
  },
  {
    id: "M29",
    title: "Option / Environment 补全",
    status: "pending" as const,
    items: [
      "Environment 页映射逼近 13/13",
      "Selection mode / Viewer Mode",
      "设置持久化",
    ],
  },
  {
    id: "M30",
    title: "Part 专用件包",
    status: "pending" as const,
    items: [
      "Enclosure / Plate·Pin Fin / Peltier·2R",
      "按场景增量扩展菜单",
    ],
  },
  {
    id: "M31",
    title: "Solver/Post 产品化",
    status: "pending" as const,
    items: [
      "环境文件路径 / 工作目录 / restart",
      "Post 打开场数据",
      "启动矩阵文档化",
    ],
  },
];

function depthTone(d: Depth): "success" | "warning" | "neutral" | "info" {
  if (d === "impl") return "success";
  if (d === "partial") return "warning";
  if (d === "chrome") return "info";
  return "neutral";
}

function sevTone(s: string): "danger" | "warning" | "info" | "neutral" {
  if (s === "Blocker") return "danger";
  if (s === "High") return "warning";
  if (s === "Medium") return "info";
  return "neutral";
}

export default function CabGuiStpreGap() {
  const theme = useHostTheme();

  const uiPct = Math.round(
    (AREA_COVERAGE.reduce((a, r) => a + r.ui, 0) /
      AREA_COVERAGE.reduce((a, r) => a + r.stpre, 0)) *
      100,
  );
  const usefulPct = Math.round(
    (AREA_COVERAGE.reduce((a, r) => a + Math.min(r.useful, r.stpre), 0) /
      AREA_COVERAGE.reduce((a, r) => a + r.stpre, 0)) *
      100,
  );

  const chartUi = AREA_COVERAGE.map((r) => ({
    label: r.area,
    value: Math.round((r.ui / r.stpre) * 100),
  }));
  const chartUseful = AREA_COVERAGE.map((r) => ({
    label: r.area,
    value: Math.round((Math.min(r.useful, r.stpre) / r.stpre) * 100),
  }));

  return (
    <Stack gap={20} style={{ padding: 20, maxWidth: 1100 }}>
      <Stack gap={6}>
        <H1>cab_gui vs STpre 功能差距</H1>
        <Text tone="secondary" size="small">
          对照 CradleCFD 2025.2 Pre_eng toc + cab_gui.py / cab_edit_* /
          cab_parts / wizards。区分「菜单 chrome」与「内核可用」。
        </Text>
      </Stack>

      <Callout tone="warning" title="总判">
        菜单表面覆盖已较高（Edit 24/24、Mesh 6/6、Wizard 2/2），但内核忠实度明显偏低：Edit
        CAD、面拾取、Import/Export 广度、Condition Wizard 深度仍是主要差距。
      </Callout>

      <Grid columns={4} gap={12}>
        <Stat
          value={`${uiPct}%`}
          label="菜单 UI 覆盖（加权）"
          tone="info"
        />
        <Stat
          value={`${usefulPct}%`}
          label="可用实现覆盖（加权）"
          tone="warning"
        />
        <Stat value="24/24" label="Edit 菜单项" tone="success" />
        <Stat value="14/30+" label="Part 种类" tone="warning" />
      </Grid>

      <UsageBar
        segments={[
          { label: "可用/近似", value: usefulPct, tone: "success" },
          {
            label: "仅 chrome / 缺口",
            value: Math.max(0, 100 - usefulPct),
            tone: "neutral",
          },
        ]}
      />
      <Text tone="secondary" size="small">
        Source: Pre_eng toc.csv + cabdecoding main · 加权按菜单叶子项粗算
      </Text>

      <H2>分区覆盖</H2>
      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>菜单 UI 覆盖率 (%)</CardHeader>
          <CardBody>
            <BarChart
              categories={chartUi.map((d) => d.label)}
              series={[{ name: "UI %", data: chartUi.map((d) => d.value) }]}
              height={220}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>可用实现覆盖率 (%)</CardHeader>
          <CardBody>
            <BarChart
              categories={chartUseful.map((d) => d.label)}
              series={[
                {
                  name: "Useful %",
                  data: chartUseful.map((d) => d.value),
                },
              ]}
              height={220}
            />
          </CardBody>
        </Card>
      </Grid>

      <Table
        headers={["区域", "STpre", "cab UI", "可用", "备注"]}
        rows={AREA_COVERAGE.map((r) => [
          r.area,
          String(r.stpre),
          String(r.ui),
          String(r.useful),
          r.note,
        ])}
      />

      <H2>深度差距（chrome ≠ 内核）</H2>
      <Table
        headers={["区域", "能力", "深度", "差距说明"]}
        rows={DEPTH_ROWS.map((r) => [
          r.area,
          r.item,
          <Pill key={r.item} tone={depthTone(r.depth)} size="sm">
            {r.depth}
          </Pill>,
          r.gap,
        ])}
      />
      <Row gap={8} style={{ flexWrap: "wrap" }}>
        <Pill tone="success" size="sm">
          impl
        </Pill>
        <Text size="small">可用</Text>
        <Pill tone="warning" size="sm">
          partial
        </Pill>
        <Text size="small">近似</Text>
        <Pill tone="info" size="sm">
          chrome
        </Pill>
        <Text size="small">对话框/意图</Text>
        <Pill tone="neutral" size="sm">
          missing
        </Pill>
        <Text size="small">未挂菜单</Text>
      </Row>

      <H2>跨切面缺口（按严重度）</H2>
      <Table
        headers={["缺口", "严重度", "影响"]}
        rows={CROSS_CUTTING.map((r) => [
          r.gap,
          <Pill key={r.gap} tone={sevTone(r.severity)} size="sm">
            {r.severity}
          </Pill>,
          r.why,
        ])}
      />

      <H2>改进计划（M24+）</H2>
      <Text tone="secondary" size="small">
        优先打通内核与拾取，再补格式与网格，然后 Wizard/Option/专用件。
      </Text>
      <Spacer size={8} />
      <Grid columns={2} gap={12}>
        {MILESTONES.map((m) => (
          <Card key={m.id}>
            <CardHeader trailing={<Pill size="sm">{m.id}</Pill>}>
              {m.title}
            </CardHeader>
            <CardBody>
              <TodoList
                todos={m.items.map((t, i) => ({
                  id: `${m.id}-${i}`,
                  text: t,
                  status: m.status,
                }))}
              />
            </CardBody>
          </Card>
        ))}
      </Grid>

      <Divider />
      <H3>当前优势（保持）</H3>
      <Text>
        CAB 读写、STpre 布局 chrome、XT facet 显示、Domain/Gridding 规则逼近、Mesh
        菜单表面、Initial Wizard、原语 Part 创建、快照 Undo。这些是后续里程碑的底座，不宜推倒重来。
      </Text>
      <Spacer size={4} />
      <Text tone="secondary" size="small">
        建议下一迭代直接从 M24（Boolean + 面拾取 + Facet 重建）开工；完成后 Edit
        从「对话框齐」跃迁到「CAD 准备可用」。
      </Text>
    </Stack>
  );
}

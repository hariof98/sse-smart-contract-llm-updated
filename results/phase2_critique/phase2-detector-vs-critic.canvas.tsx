import {
  Stack,
  Row,
  Grid,
  H1,
  H2,
  H3,
  Text,
  Code,
  Pill,
  Stat,
  Callout,
  Table,
  Divider,
  BarChart,
  useCanvasState,
} from "cursor/canvas";

// ── Data (from results/critique_gpt4o-mini_to_gpt4o_chain_of_thought_20260619T154837Z.json) ──
// Per class: [precision, recall, f1, TP, FP, FN]
const METRICS = {
  detector: {
    reentrancy: [0.625, 0.968, 0.759, 30, 18, 1],
    access_control: [0.353, 1.0, 0.522, 18, 33, 0],
    timestamp_dependency: [0.714, 1.0, 0.833, 5, 2, 0],
    micro: [0.5, 0.981, 0.663, 53, 53, 1],
    macro: [0.564, 0.989, 0.705],
  },
  critic: {
    reentrancy: [0.879, 0.935, 0.906, 29, 4, 2],
    access_control: [0.533, 0.889, 0.667, 16, 14, 2],
    timestamp_dependency: [0.714, 1.0, 0.833, 5, 2, 0],
    micro: [0.714, 0.926, 0.806, 50, 20, 4],
    macro: [0.709, 0.941, 0.802],
  },
} as const;

type Row10 = [string, string, string, number, string, number, string, string, string, number];

// [file, actual, detector, detOk, critic, critOk, removed, added, effect, criticErr]
const ROWS: Row10[] = [
  ["FibonacciBalance.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["arbitrary_location_write_simple.sol", "access_control", "access_control", 1, "access_control", 1, "", "", "same", 0],
  ["incorrect_constructor_name1.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["incorrect_constructor_name2.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["incorrect_constructor_name3.sol", "access_control", "access_control/reentrancy", 0, "-", 0, "access_control/reentrancy", "", "mixed", 0],
  ["mapping_write.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["multiowned_vulnerable.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["mycontract.sol", "access_control", "access_control", 1, "access_control", 1, "", "", "same", 0],
  ["parity_wallet_bug_1.sol", "access_control", "access_control/reentrancy/timestamp_dependency", 0, "access_control", 1, "reentrancy/timestamp_dependency", "", "helped", 0],
  ["parity_wallet_bug_2.sol", "access_control", "access_control/reentrancy", 0, "-", 0, "access_control/reentrancy", "", "mixed", 0],
  ["phishable.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["proxy.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["rubixi.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["simple_suicide.sol", "access_control", "access_control", 1, "access_control", 1, "", "", "same", 0],
  ["unprotected0.sol", "access_control", "access_control", 1, "access_control", 1, "", "", "same", 0],
  ["wallet_02_refund_nosub.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["wallet_03_wrong_constructor.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["wallet_04_confused_sign.sol", "access_control", "access_control/reentrancy", 0, "access_control", 1, "reentrancy", "", "helped", 0],
  ["0x01f8c4e3…091d3f.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0x23a91059…70deb4.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0x4320e6f8…b3a5a1.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0x4e73b32e…ecc106.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0x561eac93…5cbf31.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0x627fa62c…e17839.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0x7541b76c…4bf615.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy/timestamp_dependency", 0, "access_control", "timestamp_dependency", "mixed", 0],
  ["0x7a8721a9…dc9782.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0x7b368c4e…662cf3.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0x8c7777c4…550344.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0x93c32845…5c2ab5.sol", "reentrancy", "access_control/reentrancy/timestamp_dependency", 0, "reentrancy/timestamp_dependency", 0, "access_control", "", "helped", 0],
  ["0x941d2252…f95e9e.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0x96edbe86…f1b78b.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0xaae1f51c…44b0b8.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0xb5e1b1ee…f1bd12.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0xb93430ce…3fd89e.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0xbaf51e76…8c8a4f.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0xbe4041d5…7e3888.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 0],
  ["0xcead721e…e66b6e.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["0xf015c356…5aad68.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["etherbank.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["etherstore.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["modifier_reentrancy.sol", "reentrancy", "access_control/reentrancy", 0, "-", 0, "access_control/reentrancy", "", "mixed", 0],
  ["reentrance.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["reentrancy_bonus.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["reentrancy_cross_function.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["reentrancy_dao.sol", "reentrancy", "access_control/reentrancy", 0, "reentrancy", 1, "access_control", "", "helped", 0],
  ["reentrancy_insecure.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 1],
  ["reentrancy_simple.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 1],
  ["simple_dao.sol", "reentrancy", "access_control/reentrancy", 0, "access_control/reentrancy", 0, "", "", "same", 1],
  ["spank_chain_payment.sol", "reentrancy", "-", 0, "-", 0, "", "", "same", 1],
  ["ether_lotto.sol", "timestamp_dependency", "reentrancy/timestamp_dependency", 0, "reentrancy/timestamp_dependency", 0, "", "", "same", 1],
  ["governmental_survey.sol", "timestamp_dependency", "access_control/reentrancy/timestamp_dependency", 0, "access_control/reentrancy/timestamp_dependency", 0, "", "", "same", 1],
  ["lottopollo.sol", "timestamp_dependency", "access_control/reentrancy/timestamp_dependency", 0, "access_control/reentrancy/timestamp_dependency", 0, "", "", "same", 1],
  ["roulette.sol", "timestamp_dependency", "access_control/reentrancy/timestamp_dependency", 0, "access_control/reentrancy/timestamp_dependency", 0, "", "", "same", 1],
  ["timed_crowdsale.sol", "timestamp_dependency", "timestamp_dependency", 1, "timestamp_dependency", 1, "", "", "same", 1],
];

const CLASS_SHORT: Record<string, string> = {
  reentrancy: "reentrancy",
  access_control: "access_control",
  timestamp_dependency: "timestamp_dependency",
  "": "—",
  "-": "—",
};

function pct(v: number): string {
  return v.toFixed(3);
}

function displayEffect(effect: string, err: number): string {
  if (err) return "rate-limited";
  return effect;
}

export default function Phase2DetectorVsCritic() {
  const [filter, setFilter] = useCanvasState<string>("effectFilter", "all");

  const rowEffect = (r: Row10) => displayEffect(r[8], r[9]);

  const counts = {
    all: ROWS.length,
    helped: ROWS.filter((r) => rowEffect(r) === "helped").length,
    mixed: ROWS.filter((r) => rowEffect(r) === "mixed").length,
    same: ROWS.filter((r) => rowEffect(r) === "same").length,
    "rate-limited": ROWS.filter((r) => rowEffect(r) === "rate-limited").length,
  };

  const filtered = filter === "all" ? ROWS : ROWS.filter((r) => rowEffect(r) === filter);

  const filters: { id: string; label: string }[] = [
    { id: "all", label: `All (${counts.all})` },
    { id: "helped", label: `Helped (${counts.helped})` },
    { id: "mixed", label: `Mixed (${counts.mixed})` },
    { id: "same", label: `Unchanged (${counts.same})` },
    { id: "rate-limited", label: `Rate-limited (${counts["rate-limited"]})` },
  ];

  // Charts
  const classCats = ["reentrancy", "access_control", "timestamp_dep.", "micro-avg"];
  const f1Detector = [
    METRICS.detector.reentrancy[2],
    METRICS.detector.access_control[2],
    METRICS.detector.timestamp_dependency[2],
    METRICS.detector.micro[2],
  ];
  const f1Critic = [
    METRICS.critic.reentrancy[2],
    METRICS.critic.access_control[2],
    METRICS.critic.timestamp_dependency[2],
    METRICS.critic.micro[2],
  ];

  const confCats = ["True Pos", "False Pos", "False Neg"];
  const confDetector = [METRICS.detector.micro[3], METRICS.detector.micro[4], METRICS.detector.micro[5]];
  const confCritic = [METRICS.critic.micro[3], METRICS.critic.micro[4], METRICS.critic.micro[5]];

  const effectTone = (eff: string): "success" | "danger" | "warning" | "info" | "neutral" | undefined => {
    if (eff === "helped") return "success";
    if (eff === "mixed") return "warning";
    if (eff === "hurt") return "danger";
    if (eff === "rate-limited") return "info";
    return undefined;
  };

  const okPill = (ok: number) =>
    ok ? (
      <Pill tone="success" size="sm" active>
        Y
      </Pill>
    ) : (
      <Pill tone="neutral" size="sm">
        N
      </Pill>
    );

  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 1180 }}>
      <Stack gap={4}>
        <H1>Phase 2 — does the critic earn its cost?</H1>
        <Text tone="secondary">
          Detector <Code>gpt4o-mini</Code> → Critic <Code>gpt4o</Code> · chain-of-thought · SmartBugs
          Curated (54 contracts) · class-only matching
        </Text>
        <Text tone="tertiary" size="small">
          Source: results/critique_gpt4o-mini_to_gpt4o_chain_of_thought_20260619T154837Z.json · "after-critic" =
          critic's revised list scored against ground truth
        </Text>
      </Stack>

      {/* Headline numbers */}
      <Grid columns={4} gap={12}>
        <Stat value="0.663 → 0.806" label="Micro-F1  (+0.144)" tone="success" />
        <Stat value="53 → 20" label="False positives removed" tone="success" />
        <Stat value="5 → 33" label="Exactly-correct contracts (of 54)" tone="success" />
        <Stat value="9" label="Critic calls rate-limited" tone="warning" />
      </Grid>

      <Callout tone="info" title="What the critic actually does here">
        The cheap detector over-flags — it tagged <Text weight="semibold">reentrancy</Text> and{" "}
        <Text weight="semibold">access_control</Text> on almost every contract (53 false positives). The
        stronger critic is mostly a <Text weight="semibold">false-positive remover</Text>: it cut 33 of them,
        lifting precision 0.50 → 0.71. The cost is small — it wrongly dropped 3 true positives (recall 0.98 →
        0.93). Net F1 rises +0.144.
      </Callout>

      {/* Charts */}
      <Grid columns={2} gap={16}>
        <Stack gap={6}>
          <H3>F1 by class — detector vs after-critic</H3>
          <BarChart
            categories={classCats}
            series={[
              { name: "Detector only", data: f1Detector, tone: "neutral" },
              { name: "After critic", data: f1Critic, tone: "success" },
            ]}
            height={240}
          />
          <Text tone="tertiary" size="small">
            Y axis: F1 score (0–1). Higher is better. Critic lifts reentrancy and access_control; timestamp
            unchanged.
          </Text>
        </Stack>
        <Stack gap={6}>
          <H3>Confusion counts (micro) — detector vs after-critic</H3>
          <BarChart
            categories={confCats}
            series={[
              { name: "Detector only", data: confDetector, tone: "neutral" },
              { name: "After critic", data: confCritic, tone: "info" },
            ]}
            height={240}
          />
          <Text tone="tertiary" size="small">
            Y axis: contract-class count across all 54 contracts. The big win is the False-Positive column
            collapsing 53 → 20.
          </Text>
        </Stack>
      </Grid>

      {/* Metrics table */}
      <Stack gap={6}>
        <H2>Metrics before vs after critique</H2>
        <Table
          headers={[
            "Class",
            "Det P",
            "Det R",
            "Det F1",
            "Crit P",
            "Crit R",
            "Crit F1",
            "Δ F1",
          ]}
          columnAlign={["left", "right", "right", "right", "right", "right", "right", "right"]}
          rowTone={["neutral", "neutral", "neutral", undefined, "success"]}
          rows={[
            ["reentrancy", pct(0.625), pct(0.968), pct(0.759), pct(0.879), pct(0.935), pct(0.906), "+0.147"],
            ["access_control", pct(0.353), pct(1.0), pct(0.522), pct(0.533), pct(0.889), pct(0.667), "+0.145"],
            ["timestamp_dependency", pct(0.714), pct(1.0), pct(0.833), pct(0.714), pct(1.0), pct(0.833), "·"],
            ["micro-average", pct(0.5), pct(0.981), pct(0.663), pct(0.714), pct(0.926), pct(0.806), "+0.144"],
            ["macro-average", pct(0.564), pct(0.989), pct(0.705), pct(0.709), pct(0.941), pct(0.802), "+0.097"],
          ]}
        />
        <Text tone="tertiary" size="small">
          P = precision, R = recall, F1 = harmonic mean. Last two rows are aggregates across classes.
        </Text>
      </Stack>

      {/* Cost */}
      <Grid columns={3} gap={12}>
        <Stat value="138,079" label="Total tokens (58k detector + 80k critic)" />
        <Stat value="2,762" label="Tokens per true positive" />
        <Stat value="~$0.38" label="Est. cost (OpenAI list price)" />
      </Grid>

      <Divider />

      {/* Per-contract */}
      <Stack gap={8}>
        <Row align="center" justify="space-between" wrap>
          <H2>Per-contract: did the detector catch it, and did the critic change it?</H2>
        </Row>
        <Row gap={8} wrap>
          {filters.map((f) => (
            <Pill key={f.id} active={filter === f.id} onClick={() => setFilter(f.id)}>
              {f.label}
            </Pill>
          ))}
        </Row>
        <Table
          stickyHeader
          striped
          headers={["Contract", "Actual bug", "Detector", "det✓", "After critic", "crit✓", "Critic removed", "Effect"]}
          columnAlign={["left", "left", "left", "center", "left", "center", "left", "left"]}
          rowTone={filtered.map((r) => effectTone(rowEffect(r)))}
          rows={filtered.map((r) => [
            <Text size="small" truncate="start" style={{ maxWidth: 200 }}>
              {r[0]}
            </Text>,
            CLASS_SHORT[r[1]] ?? r[1],
            <Text size="small" tone={r[3] ? "primary" : "secondary"}>
              {r[2]}
            </Text>,
            okPill(r[3]),
            <Text size="small" weight={r[5] ? "semibold" : "normal"}>
              {r[4]}
            </Text>,
            okPill(r[5]),
            r[6] ? <Text size="small" tone="secondary">−{r[6]}</Text> : <Text tone="quaternary">·</Text>,
            <Pill size="sm" tone={effectTone(rowEffect(r)) ?? "neutral"} active={rowEffect(r) !== "same"}>
              {rowEffect(r)}
            </Pill>,
          ])}
        />
        <Text tone="tertiary" size="small">
          det✓ / crit✓ = prediction exactly equals the ground-truth class. "rate-limited" rows: the critic call
          failed (free-tier quota), so after-critic fell back to the detector's output — the true critic effect
          is understated by 9 contracts.
        </Text>
      </Stack>
    </Stack>
  );
}

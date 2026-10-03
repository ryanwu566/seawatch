import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { DICTIONARIES } from "../../i18n/dictionaries";
import { findForbiddenTerm } from "./forbiddenTerms";
import type {
  DecisionBrief,
  ScenarioContext,
  ScenarioListResponse,
} from "./logisticsTypes";

// ---------------------------------------------------------------------------
// Slice K — deterministic SENSE → SURVIVE → RESPOND demo (frontend).
//
// SENSE  : the existing maritime-awareness product remains (LIVE MAP view);
//          this test focuses on the RESPOND/SURVIVE surface of the logistics
//          feature without altering the live dashboard.
// SURVIVE: the read-only Phase 8 operating-context banner shows CLOUD_LIVE /
//          EDGE_LIVE / EDGE_REPLAY labels.
// RESPOND: the Kaohsiung disruption brief renders the exact golden allocations,
//          Decision Brief, trade-offs, and an always-visible TruthBadge.
//
// Everything is driven by fixed fixtures — no randomness, no network, no LLM.
// ---------------------------------------------------------------------------

// The golden RESPOND result, mirroring the backend engine output locked in
// tests/integration/test_logistics_kaohsiung_demo.py.
const DEMO_BRIEF: DecisionBrief = {
  scenario_id: "kaohsiung-disruption",
  summary_zh:
    "高雄港中斷情境的建議配置：共 120 單位改由替代民用港口承接，0 單位未能滿足。最高優先的 medical 需求優先經由 taichung。以上為供人工審查的規劃估計值，並非指示。",
  summary_en:
    "Recommended allocation for the Kaohsiung Port Disruption scenario: 120 unit(s) routed to alternative civilian ports, 0 unit(s) unmet. Highest-priority medical demand is prioritized via taichung. These are planning estimates for human review, not an instruction.",
  recommended_allocations: [
    {
      demand_id: "medical-south",
      assignments: [
        { port_id: "taichung", route_id: "taichung->south-node", units: 30, eta_hours: 9.5, cost: 2.2, risk: 0.21 },
      ],
      satisfied_units: 30,
      unmet_units: 0,
      score: 0.042,
    },
    {
      demand_id: "food-south",
      assignments: [
        { port_id: "taichung", route_id: "taichung->south-node", units: 30, eta_hours: 9.5, cost: 2.2, risk: 0.21 },
        { port_id: "keelung", route_id: "keelung->south-node", units: 20, eta_hours: 15, cost: 2.6, risk: 0.28 },
      ],
      satisfied_units: 50,
      unmet_units: 0,
      score: 0.656,
    },
    {
      demand_id: "fuel-south",
      assignments: [
        { port_id: "keelung", route_id: "keelung->south-node", units: 40, eta_hours: 15, cost: 2.6, risk: 0.28 },
      ],
      satisfied_units: 40,
      unmet_units: 0,
      score: 0.656,
    },
  ],
  alternatives: [
    {
      port_id: "taichung",
      port_label: "臺中港 Taichung",
      eta_hours: 9.5,
      distance_km: 185.8,
      per_unit_cost: 2.2,
      capacity_units: 60,
      capacity_utilization: 1.0,
      risk: 0.21,
      schematic: true,
      schematic_label: "SCHEMATIC CONNECTOR / 示意連線",
      route_source_type: "derived",
    },
    {
      port_id: "keelung",
      port_label: "基隆港 Keelung",
      eta_hours: 15,
      distance_km: 314.7,
      per_unit_cost: 2.6,
      capacity_units: 70,
      capacity_utilization: 0.8571,
      risk: 0.28,
      schematic: true,
      schematic_label: "SCHEMATIC CONNECTOR / 示意連線",
      route_source_type: "derived",
    },
  ],
  trade_offs: [
    "food: split across taichung, keelung because no single alternative port had enough remaining capacity; this is a planning estimate for human review.",
  ],
  unmet_demand: [],
  provenance_note:
    "此為供人工審查的情境規劃估計值，並非真實作業資料，也非對真實事件的預測。 Scenario-based planning estimates for human review; not real operational data and not a prediction of a real event.",
  assumptions: [
    "Weights: time 0.35 / cost 0.25 / risk 0.20 / capacity 0.20 (normalized to sum 1).",
    "Capacity is abstract planning units/day (synthetic), never real port throughput.",
    "ETA, cost and risk are scenario/synthetic planning indices for human review.",
    "Distances are derived great-circle values between public civilian coordinates.",
    "Priority ordering: lower priority number allocated first (medical-south, food-south, fuel-south).",
  ],
  provenance_summary: { official: 3, derived: 2, scenario: 7, synthetic: 0 },
};

const DEMO_CONTEXT: ScenarioContext = {
  scenario: {
    id: "kaohsiung-disruption",
    name_zh: "高雄港中斷情境",
    name_en: "Kaohsiung Port Disruption",
    disrupted_ports: ["kaohsiung"],
    description_zh: "規劃情境",
    description_en: "planning scenario",
    source_type: "scenario",
  },
  affected_demands: [
    { id: "medical-south", commodity: "medical", priority: 1, quantity_units: 30, origin_demand_node: "south-node", source_type: "scenario" },
    { id: "food-south", commodity: "food", priority: 2, quantity_units: 50, origin_demand_node: "south-node", source_type: "scenario" },
    { id: "fuel-south", commodity: "fuel", priority: 3, quantity_units: 40, origin_demand_node: "south-node", source_type: "scenario" },
  ],
  candidate_ports: ["taichung", "keelung"],
  candidate_routes: [],
  provenance_summary: { official: 3, derived: 2, scenario: 7, synthetic: 0 },
};

const SCENARIOS: ScenarioListResponse = {
  count: 1,
  scenarios: [
    {
      id: "kaohsiung-disruption",
      name_zh: "高雄港中斷情境",
      name_en: "Kaohsiung Port Disruption",
      disrupted_ports: ["kaohsiung"],
      source_type: "scenario",
    },
  ],
};

// Deterministic logistics API: fixed fixtures, no network, no randomness.
const fetchScenarios = vi.fn(async () => SCENARIOS);
const fetchScenarioContext = vi.fn(async () => DEMO_CONTEXT);
const runSimulation = vi.fn(async () => DEMO_BRIEF);

vi.mock("./logisticsApi", () => ({
  fetchScenarios: () => fetchScenarios(),
  fetchScenarioContext: () => fetchScenarioContext(),
  runSimulation: () => runSimulation(),
}));

// Reuse the shared MapCanvas seam without MapLibre in jsdom (do NOT modify it).
vi.mock("../../components/MapCanvas", () => ({
  MapCanvas: () => <div data-testid="logistics-map" />,
}));

// SURVIVE: the read-only Phase 8 operating-mode hook is mocked per test.
let operatingMode: string | null = null;
function resilienceStatus(mode: string | null) {
  if (!mode) return null;
  const edge = mode === "EDGE_LIVE" || mode === "EDGE_REPLAY";
  return {
    mode,
    coverage: mode === "CLOUD_LIVE" ? "taiwan_wide_network_feed" : edge ? "local_rf" : "none",
    simulated: mode === "EDGE_REPLAY",
    internet_available: mode === "CLOUD_LIVE",
    power_mode: "external",
    cloud: { source: "open_waters", fresh: mode === "CLOUD_LIVE", message_age_seconds: 3, vessel_count: 10, connected: mode === "CLOUD_LIVE", input_kind: null },
    edge: { source: mode === "EDGE_REPLAY" ? "edge_replay" : "edge_ais", fresh: edge, message_age_seconds: edge ? 4 : null, vessel_count: edge ? 3 : 0, connected: edge, input_kind: mode === "EDGE_REPLAY" ? "replay" : edge ? "udp" : "disabled" },
  };
}
vi.mock("./useOperatingMode", () => ({
  useOperatingMode: () => ({ mode: operatingMode, status: resilienceStatus(operatingMode) }),
}));

import { LogisticsView } from "./LogisticsView";
import { LogisticsPanel } from "./LogisticsPanel";

function renderDemo() {
  return render(
    <I18nProvider>
      <LogisticsView
        demoMode
        initialScenarioId="kaohsiung-disruption"
        renderResult={({ context, brief }) => (
          <LogisticsPanel context={context} brief={brief} />
        )}
      />
    </I18nProvider>,
  );
}

async function runToResult() {
  const utils = renderDemo();
  const runLabel = DICTIONARIES.en.logistics.runSimulation;
  const button = await utils.findByRole("button", { name: runLabel });
  button.click();
  await waitFor(() =>
    expect(utils.getByTestId("logistics-panel")).toBeInTheDocument(),
  );
  return utils;
}

beforeEach(() => {
  fetchScenarios.mockClear();
  fetchScenarioContext.mockClear();
  runSimulation.mockClear();
  operatingMode = null;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Resilience demo — RESPOND (Kaohsiung disruption)", () => {
  it("1. renders the expected demo allocations (medical→taichung, food split, fuel→keelung)", async () => {
    const utils = await runToResult();
    const panel = utils.getByTestId("logistics-panel");

    const medicalRows = panel.querySelectorAll('tr[data-demand="medical-south"]');
    expect(medicalRows.length).toBe(1);
    expect(within(medicalRows[0] as HTMLElement).getByText("taichung")).toBeInTheDocument();
    expect(within(medicalRows[0] as HTMLElement).getByText("30")).toBeInTheDocument();

    const foodRows = panel.querySelectorAll('tr[data-demand="food-south"]');
    expect(foodRows.length).toBe(2); // deterministic split
    const foodPorts = Array.from(foodRows).map((r) => r.querySelectorAll("td")[1].textContent);
    expect(foodPorts).toEqual(["taichung", "keelung"]);

    const fuelRows = panel.querySelectorAll('tr[data-demand="fuel-south"]');
    expect(fuelRows.length).toBe(1);
    expect(within(fuelRows[0] as HTMLElement).getByText("keelung")).toBeInTheDocument();
    expect(within(fuelRows[0] as HTMLElement).getByText("40")).toBeInTheDocument();

    // Alternatives metrics (ETA / distance / cost / capacity / risk).
    const alt = utils.getByLabelText(DICTIONARIES.en.logistics.alternatives);
    const taichung = within(alt).getByText("Taichung").closest("tr")!;
    expect(within(taichung).getByText(/185.8/)).toBeInTheDocument();
    expect(within(taichung).getByText("100%")).toBeInTheDocument(); // util 1.0
    const keelung = within(alt).getByText("Keelung").closest("tr")!;
    expect(within(keelung).getByText(/314.7/)).toBeInTheDocument();

    // Decision Brief + trade-offs render from structured fields.
    expect(utils.getByText(/split across taichung, keelung/)).toBeInTheDocument();
  });

  it("2. same input produces identical rendered output (deterministic)", async () => {
    const first = await runToResult();
    const firstHtml = first.getByTestId("logistics-panel").innerHTML;
    first.unmount();

    // Fresh, isolated render with the same fixtures.
    const second = await runToResult();
    const secondHtml = second.getByTestId("logistics-panel").innerHTML;

    expect(secondHtml).toBe(firstHtml);
  });

  it("3. provenance / truth labels remain (TruthBadge always visible with exact counts)", async () => {
    const utils = await runToResult();
    const badge = utils.getByTestId("truth-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toContain("human review");
    expect(badge.querySelector('[data-source-class="official"] .truth-badge-count')?.textContent).toBe("3");
    expect(badge.querySelector('[data-source-class="derived"] .truth-badge-count')?.textContent).toBe("2");
    expect(badge.querySelector('[data-source-class="scenario"] .truth-badge-count')?.textContent).toBe("7");
    expect(badge.querySelector('[data-source-class="synthetic"] .truth-badge-count')?.textContent).toBe("0");
    // Schematic connectors remain labeled, never presented as measured routes.
    expect(utils.getAllByText(/SCHEMATIC CONNECTOR/).length).toBeGreaterThan(0);
  });

  it("4. rendered demo output contains no prohibited autonomous-command wording", async () => {
    const utils = await runToResult();
    const text = utils.container.textContent ?? "";
    expect(findForbiddenTerm(text)).toBeNull();
    expect(text).not.toMatch(/[\u3400-\u9fff]/u);
  });
});

describe("Resilience demo — SURVIVE (read-only Phase 8 operating context)", () => {
  it("5. Phase 8 integration is read-only: no banner, no auto-trigger when mode absent", async () => {
    operatingMode = null;
    const utils = renderDemo();
    await waitFor(() => expect(fetchScenarios).toHaveBeenCalled());
    // No operating-context banner is shown when the status is unavailable.
    expect(utils.queryByTestId("operating-status-panel")).toBeNull();
    // The demo never auto-runs a simulation from any Phase 8 signal.
    expect(runSimulation).not.toHaveBeenCalled();
  });

  it("6. renders Cloud / Edge / Replay mode labels correctly", async () => {
    const cases: Array<[string, string]> = [
      ["CLOUD_LIVE", DICTIONARIES.en.modeCloud],
      ["EDGE_LIVE", DICTIONARIES.en.modeEdge],
      ["EDGE_REPLAY", DICTIONARIES.en.modeReplay],
      ["NO_LIVE_SOURCE", DICTIONARIES.en.modeNoSource],
    ];
    for (const [mode, label] of cases) {
      operatingMode = mode;
      const { unmount } = renderDemo();
      const banner = await screen.findByTestId("operating-status-panel");
      expect(banner).toHaveAttribute("data-mode", mode);
      expect(banner.textContent).toContain(label);
      unmount();
    }
  });
});

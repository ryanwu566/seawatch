import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { LogisticsPanel } from "./LogisticsPanel";
import { findForbiddenTerm } from "./forbiddenTerms";
import type { DecisionBrief, ScenarioContext } from "./logisticsTypes";

const context: ScenarioContext = {
  scenario: {
    id: "kaohsiung-disruption",
    name_zh: "高雄港中斷情境",
    name_en: "Kaohsiung Port Disruption",
    disrupted_ports: ["kaohsiung"],
    description_zh: "x",
    description_en: "x",
    source_type: "scenario",
  },
  affected_demands: [],
  candidate_ports: ["taichung", "keelung"],
  candidate_routes: [],
  provenance_summary: {},
};

function brief(overrides: Partial<DecisionBrief> = {}): DecisionBrief {
  return {
    scenario_id: "kaohsiung-disruption",
    summary_zh: "摘要：供人工審查的規劃估計值。",
    summary_en: "Summary: planning estimates for human review.",
    recommended_allocations: [
      {
        demand_id: "medical-south",
        assignments: [
          { port_id: "taichung", route_id: "taichung->south-node", units: 30, eta_hours: 9.5, cost: 2.2, risk: 0.21 },
        ],
        satisfied_units: 30,
        unmet_units: 0,
        score: 0.1,
      },
      {
        demand_id: "food-south",
        assignments: [
          { port_id: "taichung", route_id: "taichung->south-node", units: 30, eta_hours: 9.5, cost: 2.2, risk: 0.21 },
          { port_id: "keelung", route_id: "keelung->south-node", units: 20, eta_hours: 15, cost: 2.6, risk: 0.28 },
        ],
        satisfied_units: 50,
        unmet_units: 0,
        score: 0.4,
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
        capacity_utilization: 0.82,
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
        capacity_utilization: 0.4,
        risk: 0.28,
        schematic: true,
        schematic_label: "SCHEMATIC CONNECTOR / 示意連線",
        route_source_type: "derived",
      },
    ],
    trade_offs: ["food: split across taichung, keelung; planning estimate for human review."],
    unmet_demand: [],
    provenance_note: "Scenario-based planning estimates for human review; not real operational data.",
    assumptions: ["Weights: time 0.35 / cost 0.25 / risk 0.20 / capacity 0.20 (normalized to sum 1)."],
    provenance_summary: { official: 3, derived: 2, scenario: 7, synthetic: 2 },
    ...overrides,
  };
}

function renderPanel(b: DecisionBrief | null) {
  return render(
    <I18nProvider>
      <LogisticsPanel context={context} brief={b} />
    </I18nProvider>,
  );
}

describe("LogisticsPanel", () => {
  it("renders nothing when there is no brief", () => {
    const { container } = renderPanel(null);
    expect(container.querySelector('[data-testid="logistics-panel"]')).toBeNull();
  });

  it("renders the alternatives table with all metric columns", () => {
    renderPanel(brief());
    const alt = screen.getByLabelText("替代港口"); // zh-Hant default
    const taichung = within(alt).getByText(/臺中港 Taichung/);
    const row = taichung.closest("tr")!;
    expect(within(row).getByText(/9.5/)).toBeInTheDocument(); // ETA
    expect(within(row).getByText(/185.8/)).toBeInTheDocument(); // distance
    expect(within(row).getByText("2.2")).toBeInTheDocument(); // scenario cost
    expect(within(row).getByText("82%")).toBeInTheDocument(); // capacity utilization
    expect(within(row).getByText("0.21")).toBeInTheDocument(); // risk
  });

  it("renders split allocation as separate rows", () => {
    renderPanel(brief());
    const foodRows = document.querySelectorAll('tr[data-demand="food-south"]');
    expect(foodRows.length).toBe(2); // split across taichung + keelung
    const ports = Array.from(foodRows).map((r) => r.querySelectorAll("td")[1].textContent);
    expect(ports).toEqual(expect.arrayContaining(["taichung", "keelung"]));
  });

  it("renders the decision brief summary and trade-offs", () => {
    renderPanel(brief());
    expect(screen.getByText(/供人工審查的規劃估計值/)).toBeInTheDocument();
    expect(screen.getByText(/split across taichung, keelung/)).toBeInTheDocument();
  });

  it("shows unmet demand when present", () => {
    renderPanel(
      brief({
        unmet_demand: [{ demand_id: "fuel-south", commodity: "fuel", unmet_units: 10 }],
      }),
    );
    const unmet = document.querySelector('[data-unmet="fuel-south"]');
    expect(unmet).not.toBeNull();
    expect(unmet?.textContent).toContain("10");
  });

  it("shows the no-unmet message when all demand satisfied", () => {
    renderPanel(brief());
    expect(screen.getByText(/所有需求皆可滿足/)).toBeInTheDocument();
  });

  it("ALWAYS renders the TruthBadge with any result", () => {
    renderPanel(brief());
    const badge = screen.getByTestId("truth-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toContain("human review");
    // Counts reflect provenance_summary.
    expect(badge.querySelector('[data-source-class="scenario"] .truth-badge-count')?.textContent).toBe("7");
    expect(badge.querySelector('[data-source-class="synthetic"] .truth-badge-count')?.textContent).toBe("2");
  });

  it("TruthBadge is present even with empty provenance summary", () => {
    renderPanel(brief({ provenance_summary: {} }));
    const badge = screen.getByTestId("truth-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.querySelector('[data-source-class="official"] .truth-badge-count')?.textContent).toBe("0");
  });

  it("rendered output contains no prohibited wording (frontend language guard)", () => {
    const { container } = renderPanel(brief());
    const text = container.textContent ?? "";
    expect(findForbiddenTerm(text)).toBeNull();
  });

  it("flags schematic connectors in the alternatives table", () => {
    renderPanel(brief());
    expect(screen.getAllByText(/SCHEMATIC CONNECTOR \/ 示意連線/).length).toBeGreaterThan(0);
  });
});

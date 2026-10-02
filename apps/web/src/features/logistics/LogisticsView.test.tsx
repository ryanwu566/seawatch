import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { DICTIONARIES } from "../../i18n/dictionaries";

const scenariosResponse = {
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

const contextResponse = {
  scenario: {
    id: "kaohsiung-disruption",
    name_zh: "高雄港中斷情境",
    name_en: "Kaohsiung Port Disruption",
    disrupted_ports: ["kaohsiung"],
    description_zh: "x",
    description_en: "x",
    source_type: "scenario",
  },
  affected_demands: [
    { id: "medical-south", commodity: "medical", priority: 1, quantity_units: 30, origin_demand_node: "south-node", source_type: "scenario" },
  ],
  candidate_ports: ["taichung", "keelung"],
  candidate_routes: [],
  provenance_summary: { official: 3, derived: 2, scenario: 7, synthetic: 0 },
};

const briefResponse = {
  scenario_id: "kaohsiung-disruption",
  summary_zh: "摘要",
  summary_en: "summary",
  recommended_allocations: [],
  alternatives: [],
  trade_offs: [],
  unmet_demand: [],
  provenance_note: "note for human review",
  assumptions: [],
  provenance_summary: { official: 3, derived: 2, scenario: 7, synthetic: 0 },
};

const fetchScenarios = vi.fn(async (_signal?: AbortSignal) => scenariosResponse);
const fetchScenarioContext = vi.fn(async (_id: string, _signal?: AbortSignal) => contextResponse);
const runSimulation = vi.fn(async (_id: string, _weights?: unknown, _signal?: AbortSignal) => briefResponse);

vi.mock("./logisticsApi", () => ({
  fetchScenarios: (signal?: AbortSignal) => fetchScenarios(signal),
  fetchScenarioContext: (id: string, signal?: AbortSignal) =>
    fetchScenarioContext(id, signal),
  runSimulation: (id: string, weights?: unknown, signal?: AbortSignal) =>
    runSimulation(id, weights, signal),
}));

import { LogisticsView } from "./LogisticsView";

function renderView(renderResult?: Parameters<typeof LogisticsView>[0]["renderResult"]) {
  return render(
    <I18nProvider>
      <LogisticsView renderResult={renderResult} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  fetchScenarios.mockClear();
  fetchScenarioContext.mockClear();
  runSimulation.mockClear();
  window.localStorage.clear();
});

describe("LogisticsView", () => {
  it("loads scenarios into the dropdown", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "高雄港中斷情境" })).toBeInTheDocument();
    });
    expect(fetchScenarios).toHaveBeenCalled();
  });

  it("loads context for the selected scenario", async () => {
    renderView();
    await waitFor(() => expect(fetchScenarioContext).toHaveBeenCalledWith(
      "kaohsiung-disruption",
      expect.anything(),
    ));
    await waitFor(() => {
      expect(screen.getByText(/kaohsiung/i)).toBeInTheDocument();
    });
  });

  it("Run Simulation calls POST /simulate and transitions to a result state", async () => {
    let received: unknown = "none";
    renderView(({ brief }) => {
      received = brief;
      return brief ? <div data-testid="result">done</div> : <div data-testid="noresult" />;
    });
    const runLabel = DICTIONARIES["zh-Hant"].logistics.runSimulation;
    await waitFor(() => expect(fetchScenarioContext).toHaveBeenCalled());

    const button = await screen.findByRole("button", { name: runLabel });
    fireEvent.click(button);

    await waitFor(() => expect(runSimulation).toHaveBeenCalledWith(
      "kaohsiung-disruption",
      undefined,
      expect.anything(),
    ));
    await waitFor(() => expect(screen.getByTestId("result")).toBeInTheDocument());
    expect(received).toMatchObject({ scenario_id: "kaohsiung-disruption" });
  });

  it("renders English and Chinese nav/title copy from the dictionary", async () => {
    const { rerender } = renderView();
    // Default is zh-Hant.
    expect(screen.getByRole("heading", { name: DICTIONARIES["zh-Hant"].logistics.title })).toBeInTheDocument();
    // The English copy exists in the dictionary (switch verified in App nav test).
    expect(DICTIONARIES.en.logistics.navLogistics).toBe("RESILIENCE LOGISTICS");
    expect(DICTIONARIES["zh-Hant"].logistics.navLogistics).toBe("韌性物流");
    rerender(
      <I18nProvider>
        <LogisticsView />
      </I18nProvider>,
    );
  });
});

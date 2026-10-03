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

// The logistics map reuses the shared MapCanvas; mock it so the view test does
// not spin up MapLibre in jsdom. We expose the overlay source ids so the test
// can assert the generic seam is fed.
vi.mock("../../components/MapCanvas", () => ({
  MapCanvas: (props: { overlays?: { sources: Record<string, unknown> } | null }) => (
    <div
      data-testid="logistics-map"
      data-overlay-sources={props.overlays ? Object.keys(props.overlays.sources).join(",") : ""}
    />
  ),
}));

// Slice J read-only integration seam: the operating-mode hook is mocked so the
// view test controls whether a Phase 8 resilience mode is present or absent.
let operatingMode: string | null = null;
function operatingStatus(mode: string | null) {
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
  useOperatingMode: () => ({ mode: operatingMode, status: operatingStatus(operatingMode) }),
}));

import { LogisticsView } from "./LogisticsView";

function renderView(
  renderResult?: Parameters<typeof LogisticsView>[0]["renderResult"],
  props: Partial<Parameters<typeof LogisticsView>[0]> = {},
) {
  return render(
    <I18nProvider>
      <LogisticsView renderResult={renderResult} {...props} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  fetchScenarios.mockClear();
  fetchScenarioContext.mockClear();
  runSimulation.mockClear();
  window.localStorage.clear();
  operatingMode = null;
});

describe("LogisticsView", () => {
  it("loads scenarios into the dropdown", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Kaohsiung Port Disruption" })).toBeInTheDocument();
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
      expect(screen.getAllByText(/kaohsiung/i).length).toBeGreaterThan(0);
    });
  });

  it("Run Simulation calls POST /simulate and transitions to a result state", async () => {
    let received: unknown = "none";
    renderView(({ brief }) => {
      received = brief;
      return brief ? <div data-testid="result">done</div> : <div data-testid="noresult" />;
    });
    const runLabel = DICTIONARIES.en.logistics.runSimulation;
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

  it("feeds logistics overlays into the shared MapCanvas seam", async () => {
    renderView();
    const map = await screen.findByTestId("logistics-map");
    await waitFor(() => expect(fetchScenarioContext).toHaveBeenCalled());
    await waitFor(() => {
      const sources = map.getAttribute("data-overlay-sources") ?? "";
      expect(sources).toContain("logistics-disrupted-ports");
      expect(sources).toContain("logistics-selected-routes");
    });
  });

  it("renders English by default while retaining the supported Chinese dictionary", async () => {
    const { rerender } = renderView();
    expect(screen.getByRole("heading", { name: DICTIONARIES.en.logistics.title })).toBeInTheDocument();
    expect(DICTIONARIES.en.logistics.navLogistics).toBe("RESILIENCE LOGISTICS");
    expect(DICTIONARIES["zh-Hant"].logistics.navLogistics).toBe("韌性物流");
    rerender(
      <I18nProvider>
        <LogisticsView />
      </I18nProvider>,
    );
  });

  it("shows the full Phase 8 operating status when it is available", async () => {
    operatingMode = "EDGE_REPLAY";
    renderView();
    const panel = await screen.findByTestId("operating-status-panel");
    expect(panel.textContent).toContain(DICTIONARIES.en.modeReplay);
    expect(panel.textContent).toContain("edge_replay");
    expect(panel.textContent).toContain(DICTIONARIES.en.provenanceReplay);
    expect(panel).toHaveAttribute("data-mode", "EDGE_REPLAY");
  });

  it("preselects the approved resilience demo scenario but never runs it automatically", async () => {
    renderView(undefined, {
      demoMode: true,
      initialScenarioId: "kaohsiung-disruption",
    });

    const select = await screen.findByRole("combobox", {
      name: DICTIONARIES.en.logistics.selectScenario,
    });
    await waitFor(() => expect(select).toHaveValue("kaohsiung-disruption"));
    expect(runSimulation).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Illustrative workflow")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: DICTIONARIES.en.logistics.runSimulation,
      }),
    );
    await waitFor(() => expect(runSimulation).toHaveBeenCalledTimes(1));
  });

  it("renders no operating-status panel when the status is unavailable (graceful fallback)", async () => {
    operatingMode = null;
    renderView();
    await waitFor(() => expect(fetchScenarios).toHaveBeenCalled());
    expect(screen.queryByTestId("operating-status-panel")).toBeNull();
  });
});

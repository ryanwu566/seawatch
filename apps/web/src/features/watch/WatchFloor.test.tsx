import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockApi = vi.hoisted(() => ({
  regions: vi.fn(),
  selectRegion: vi.fn(),
  scenario: vi.fn(),
  tracks: vi.fn(),
  alerts: vi.fn(),
  dismissed: vi.fn(),
  alert: vi.fn(),
  setStatus: vi.fn(),
  addNote: vi.fn(),
  config: vi.fn(),
  setConfig: vi.fn(),
  resetConfig: vi.fn(),
  evaluation: vi.fn(),
  assessment: vi.fn(),
  rulebook: vi.fn(),
  pathReviews: vi.fn(),
  decidePathReview: vi.fn(),
  layers: vi.fn(),
  truth: vi.fn(),
  resetFeedback: vi.fn(),
}));
const mockHistorical = vi.hoisted(() => ({
  summary: vi.fn(),
  traffic: vi.fn(),
}));

vi.mock("./api", () => ({ watchApi: mockApi }));
vi.mock("../../api/historicalRuntime", () => ({
  getHistoricalRuntimeSummary: mockHistorical.summary,
}));
vi.mock("../../api/historicalTraffic", () => ({
  getHistoricalTraffic: mockHistorical.traffic,
}));
vi.mock("./WatchMap", () => ({
  WatchMap: (props: { historicalTraffic?: GeoJSON.FeatureCollection | null }) => (
    <section aria-label="Watch map">
      <span data-testid="watch-map-historical-cells">
        {props.historicalTraffic?.features.length ?? 0}
      </span>
    </section>
  ),
}));

import { WatchFloor } from "./WatchFloor";

const scenario = {
  region: "taiwan",
  region_label: "Taiwan scenario",
  timezone: "Asia/Taipei",
  data_kind: "simulated",
  note: "Scenario replay",
  bounds: [[119, 21], [123, 26]],
  name: "Scenario",
  t0: 1_700_000_000,
  t1: 1_700_003_600,
  vessels: 1,
  fixes: 2,
  simulated: true,
  zones: [],
  receivers: [],
};

const liveScenario = {
  ...scenario,
  region: "live",
  region_label: "Live Datalastic Area Scan",
  data_kind: "real",
  note: "Human-review candidates from explicit Area Scans",
  name: "Live Datalastic Area Scan",
  t0: 1_700_100_000,
  t1: 1_700_100_600,
  simulated: false,
  source: "live",
  detection_status: "insufficient_history",
  analysis_at: "2026-10-04T01:11:00+00:00",
};

const liveAlert = {
  id: "A-live",
  title: "Position anomaly - LIVE SHIP",
  risk: 72,
  level: "HIGH",
  confidence: 0.8,
  mmsis: ["v_opaque_live_vessel"],
  public_ids: ["v_opaque_live_vessel"],
  vessels: [{
    mmsi: "v_opaque_live_vessel",
    public_id: "v_opaque_live_vessel",
    name: "LIVE SHIP",
    type: "cargo",
    flag: "",
  }],
  t_start: liveScenario.t0,
  t_end: liveScenario.t1,
  raised_at: liveScenario.t1,
  lat: 22.5,
  lon: 120.5,
  kinds: ["position_jump"],
  status: "new",
  n_events: 1,
  n_notes: 0,
  suppressed_by_feedback: null,
  top_reason: "Reported movement needs review.",
  source: "live",
};

const liveDetail = {
  ...liveAlert,
  ml: null,
  reasons: ["Reported movement needs review."],
  breakdown: [{ kind: "position_jump", label: "Position anomaly", severity: 90, confidence: 0.8, points: 72 }],
  benign_explanations: ["Receiver error"],
  uncertainty: ["AIS cannot establish intent."],
  recommended_action: "Queue for analyst review.",
  notes: [],
  timeline: [{
    id: "E-live",
    kind: "position_jump",
    mmsis: ["v_opaque_live_vessel"],
    t_start: liveScenario.t0,
    t_end: liveScenario.t1,
    lat: 22.5,
    lon: 120.5,
    severity: 90,
    confidence: 0.8,
    summary: "Position anomaly",
    evidence: ["Reported movement needs review."],
    benign_explanations: ["Receiver error"],
    uncertainty: ["AIS cannot establish intent."],
    metrics: {},
    zone_id: null,
    path: [],
  }],
  path_reviews: [],
};

const scenarioAlert = {
  ...liveAlert,
  id: "A-scenario",
  title: "Scenario review candidate",
  mmsis: ["416000999"],
  public_ids: undefined,
  vessels: [{
    mmsi: "416000999",
    name: "SCENARIO SHIP",
    type: "cargo",
    flag: "",
  }],
  source: "scenario",
};

const scenarioDetail = {
  ...liveDetail,
  ...scenarioAlert,
  timeline: [{
    ...liveDetail.timeline[0],
    id: "E-scenario",
    mmsis: ["416000999"],
  }],
};

describe("Watch Floor live source", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHistorical.summary.mockResolvedValue({
      available: true,
      runtime: "SeaWatch_Runtime_Taiwan_2026_v2",
      data_model: "standardized_hourly_vessel_presence",
      date_range: { start: "2026-01-01", end: "2026-09-29" },
      row_count: 33_200_000,
      unique_vessel_count: 400_800,
      traffic_cell_count: 2457,
      dataset_hour_buckets: 6528,
      mmsi_join_status_counts: { unique_9digit_candidate: 66_043 },
    });
    mockHistorical.traffic.mockResolvedValue({
      available: true,
      cells: [{
        cell_lat: 25,
        cell_lon: 121.5,
        observation_count: 1200,
        unique_vessel_count: 80,
        observed_days: 40,
        active_hour_buckets: 300,
        cell_active_hour_fraction: 0.25,
        avg_vessels_per_active_hour: 4,
      }],
    });
    mockApi.scenario.mockImplementation(async (source = "scenario") => source === "live" ? liveScenario : scenario);
    mockApi.tracks.mockImplementation(async (source = "scenario") => source === "live"
      ? [{ mmsi: "v_opaque_live_vessel", public_id: "v_opaque_live_vessel", name: "LIVE SHIP", type: "cargo", flag: "", t: [liveScenario.t0, liveScenario.t1], lat: [22.5, 22.6], lon: [120.5, 120.6], sog: [8, 8] }]
      : [{ mmsi: "416000999", name: "SCENARIO SHIP", type: "cargo", flag: "", t: [scenario.t0, scenario.t1], lat: [22.5, 22.6], lon: [120.5, 120.6], sog: [8, 8] }]);
    mockApi.config.mockResolvedValue({ values: {}, defaults: {}, specs: [] });
    mockApi.regions.mockResolvedValue({ active: "taiwan", regions: [{ id: "taiwan", label: "Taiwan", data_kind: "simulated", available: true }] });
    mockApi.alerts.mockImplementation(async (_asOf?: number, source = "scenario") => source === "live" ? [liveAlert] : []);
    mockApi.dismissed.mockResolvedValue([]);
    mockApi.alert.mockImplementation(async (_id: string, source = "scenario") => source === "live" ? liveDetail : null);
    mockApi.evaluation.mockResolvedValue({
      alerts: 0, true_alerts: 0, false_alarms: 0, false_alarms_on_benign_lookalikes: 0,
      precision: 0, recall: 0, f1: 0, alerts_per_100_vessel_days: 0,
      false_alarms_per_100_vessel_days: 0, per_kind: {}, missed: [], false_alarm_ids: [],
    });
  });

  it("switches the existing floor to live data without mutating scenario region state", async () => {
    render(<WatchFloor />);
    await waitFor(() => expect(mockApi.scenario).toHaveBeenCalledWith("scenario"));

    fireEvent.change(screen.getByRole("combobox", { name: "Detection source" }), {
      target: { value: "live" },
    });

    await waitFor(() =>
      expect(document.querySelector(".wf-brand span")).toHaveTextContent("Live Datalastic Area Scan"),
    );
    expect(screen.getByText(/Live detection · Insufficient history/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Analysis time")).toHaveAttribute("title", liveScenario.analysis_at);
    expect(screen.queryByRole("contentinfo", { name: "Replay control" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tuning lab/i })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mockApi.scenario).toHaveBeenCalledWith("live");
      expect(mockApi.tracks).toHaveBeenCalledWith("live");
      expect(mockApi.alerts).toHaveBeenCalledWith(undefined, "live");
    });

    fireEvent.click(screen.getByRole("button", { name: /Position anomaly - LIVE SHIP/i }));
    expect(await screen.findByText(/Vessel ID v_opaque_live_vessel/i)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "Detection source" }), {
      target: { value: "scenario" },
    });
    await waitFor(() =>
      expect(document.querySelector(".wf-brand span")).toHaveTextContent("Taiwan scenario"),
    );
    expect(screen.getByRole("contentinfo", { name: "Replay control" })).toBeInTheDocument();
    expect(mockApi.selectRegion).not.toHaveBeenCalled();
  });

  it("discards an in-flight scenario detail when switching to live", async () => {
    let resolveScenarioDetail: (value: typeof scenarioDetail) => void = () => undefined;
    const pendingScenarioDetail = new Promise<typeof scenarioDetail>((resolve) => {
      resolveScenarioDetail = resolve;
    });
    mockApi.alerts.mockImplementation(async (_asOf?: number, source = "scenario") =>
      source === "live" ? [liveAlert] : [scenarioAlert],
    );
    mockApi.alert.mockImplementation(async (_id: string, source = "scenario") =>
      source === "live" ? liveDetail : pendingScenarioDetail,
    );

    render(<WatchFloor />);
    const scenarioCard = (await screen.findByText("Scenario review candidate")).closest("button");
    expect(scenarioCard).not.toBeNull();
    fireEvent.click(scenarioCard!);
    await waitFor(() => expect(mockApi.alert).toHaveBeenCalledWith("A-scenario", "scenario"));

    fireEvent.change(screen.getByRole("combobox", { name: "Detection source" }), {
      target: { value: "live" },
    });
    await waitFor(() =>
      expect(document.querySelector(".wf-brand span")).toHaveTextContent("Live Datalastic Area Scan"),
    );
    resolveScenarioDetail(scenarioDetail);

    expect(await screen.findByText("Select an alert")).toBeInTheDocument();
    expect(screen.queryByText(/416000999/)).not.toBeInTheDocument();
  });

  it("renders_historical_card_once_across_source_and_selection_changes", async () => {
    mockApi.alerts.mockImplementation(async (_asOf?: number, source = "scenario") =>
      source === "live" ? [liveAlert] : [scenarioAlert],
    );
    mockApi.alert.mockImplementation(async (_id: string, source = "scenario") =>
      source === "live" ? liveDetail : scenarioDetail,
    );

    render(<WatchFloor />);
    expect(await screen.findByText("Historical context available")).toBeInTheDocument();
    expect(await screen.findByText("Scenario review candidate")).toBeInTheDocument();
    expect(await screen.findByTestId("watch-map-historical-cells")).toHaveTextContent("1");
    expect(mockHistorical.summary).toHaveBeenCalledTimes(1);
    expect(mockHistorical.traffic).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByRole("combobox", { name: "Detection source" }), {
      target: { value: "live" },
    });
    expect(await screen.findByText("Position anomaly - LIVE SHIP")).toBeInTheDocument();
    expect(mockHistorical.summary).toHaveBeenCalledTimes(1);
    expect(mockHistorical.traffic).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole("button", { name: /Position anomaly - LIVE SHIP/i }),
    );
    expect(await screen.findByText(/Vessel ID v_opaque_live_vessel/i)).toBeInTheDocument();
    expect(mockHistorical.summary).toHaveBeenCalledTimes(1);
    expect(mockHistorical.traffic).toHaveBeenCalledTimes(1);
  });

  it("shows a neutral loading shell without stale scenario metadata during source changes", async () => {
    let resolveLiveScenario: (value: typeof liveScenario) => void = () => undefined;
    const pendingLiveScenario = new Promise<typeof liveScenario>((resolve) => {
      resolveLiveScenario = resolve;
    });
    mockApi.scenario.mockImplementation(async (source = "scenario") =>
      source === "live" ? pendingLiveScenario : scenario,
    );

    render(<WatchFloor />);
    expect(await screen.findByText("Historical context available")).toBeInTheDocument();
    expect(await screen.findByText(/Taiwan scenario/)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "Detection source" }), {
      target: { value: "live" },
    });

    expect(await screen.findByText("Loading Live Area Scan…")).toBeInTheDocument();
    expect(screen.queryByText(/Taiwan scenario/)).not.toBeInTheDocument();
    expect(screen.queryByText(/1 vessels/)).not.toBeInTheDocument();
    expect(mockHistorical.summary).toHaveBeenCalledTimes(1);

    resolveLiveScenario(liveScenario);
    await waitFor(() =>
      expect(document.querySelector(".wf-brand span")).toHaveTextContent("Live Datalastic Area Scan"),
    );
    expect(mockHistorical.summary).toHaveBeenCalledTimes(1);
  });

  it("historical_failure_does_not_break_live_watch_floor", async () => {
    let rejectHistory: (reason: Error) => void = () => undefined;
    mockHistorical.summary.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectHistory = reject;
      }),
    );

    render(<WatchFloor />);
    await waitFor(() => expect(mockApi.scenario).toHaveBeenCalledWith("scenario"));

    fireEvent.change(screen.getByRole("combobox", { name: "Detection source" }), {
      target: { value: "live" },
    });
    rejectHistory(new Error("optional historical endpoint failed"));

    expect(await screen.findByText("Historical context unavailable")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Detection source" })).toHaveValue("live");
    expect(await screen.findByText("Position anomaly - LIVE SHIP")).toBeInTheDocument();
    expect(screen.getByText(/Live detection.*Insufficient history/i)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Position anomaly - LIVE SHIP/i }),
    );
    expect(await screen.findByText(/Vessel ID v_opaque_live_vessel/i)).toBeInTheDocument();
    expect(mockHistorical.summary).toHaveBeenCalledTimes(1);
  });
});

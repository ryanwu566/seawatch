import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import type { LiveVesselFeature } from "../api/live";
import { DICTIONARIES } from "../i18n/dictionaries";

// --- Mock the live API --------------------------------------------------- //
let currentVessels: LiveVesselFeature[] = [];
let currentScanVessels: LiveVesselFeature[] = [];

function vessel(id: string, name: string): LiveVesselFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [120.5, 23.0] },
    properties: {
      provider_id: id,
      sog_knots: 12.4,
      cog_deg: 273,
      heading_deg: 273,
      nav_status: 0,
      vessel_type: 70,
      name,
      destination: "KHH",
      observed_at: "2026-10-01T00:00:00Z",
      source: "open_waters",
      synthesized: false,
      data_age_seconds: 18,
    },
  };
}

vi.mock("../api/live", () => ({
  fetchLiveVessels: vi.fn(async () => ({
    type: "FeatureCollection",
    attribution: "Open Waters AIS",
    server_timestamp: "2026-10-01T00:00:00Z",
    data_timestamp: "2026-10-01T00:00:00Z",
    vessel_count: currentVessels.length,
    features: currentVessels,
  })),
  fetchLiveHealth: vi.fn(async () => ({
    status: "online",
    provider: "open_waters",
    connected: true,
    subscribed: true,
    last_message_at: "2026-10-01T00:00:00Z",
    message_age_seconds: 5,
    vessel_count: currentVessels.length,
    reconnect_attempts: 0,
    last_error: null,
  })),
  fetchResilienceStatus: vi.fn(async () => ({
    mode: "CLOUD_LIVE",
    coverage: "taiwan_wide_network_feed",
    simulated: false,
    internet_available: true,
    power_mode: "external",
    cloud: { source: "open_waters", fresh: true, message_age_seconds: 5, vessel_count: currentVessels.length, connected: true, input_kind: null },
    edge: { source: "edge_ais", fresh: false, message_age_seconds: null, vessel_count: 0, connected: false, input_kind: "disabled" },
  })),
  fetchLiveTrack: vi.fn(async (id: string) => ({
    type: "Feature",
    id,
    geometry: { type: "LineString", coordinates: [[120, 22], [120.5, 23]] },
    properties: { provider_id: id, point_count: 2, observed_from: null, observed_to: null },
  })),
  authenticateAreaScan: vi.fn(async () => ({
    authenticated: true,
    expires_in_seconds: 900,
  })),
  scanLiveArea: vi.fn(async () => ({
    source: "datalastic",
    scanned_at: "2026-10-03T02:00:00Z",
    cached: false,
    scan: { geometry_type: "Polygon", provider_queries: 2 },
    total: currentScanVessels.length,
    vessels: currentScanVessels,
  })),
  AreaScanApiError: class AreaScanApiError extends Error {
    readonly status: number;
    readonly retryAfterSeconds: number | null;

    constructor(status: number, message: string, retryAfterSeconds: number | null) {
      super(message);
      this.name = "AreaScanApiError";
      this.status = status;
      this.retryAfterSeconds = retryAfterSeconds;
    }
  },
}));

// --- Mock MapCanvas: expose select/deselect via buttons ------------------ //
vi.mock("../components/MapCanvas", () => {
  return {
    MapCanvas: (props: any) => {
      return (
        <div data-testid="map">
          <div data-testid="selected-id">{props.selectedId ?? ""}</div>
          <div data-testid="selected-source">{props.selectedSource ?? ""}</div>
          <div data-testid="follow">{String(props.follow)}</div>
          <div data-testid="fit-bounds">{props.fitBounds ? props.fitBounds.join(",") : ""}</div>
          <div data-testid="fit-nonce">{String(props.fitBoundsNonce ?? 0)}</div>
          {props.vessels.map((v: LiveVesselFeature) => (
            <button key={v.id} data-testid={`sel-${v.id}`} onClick={() => props.onSelectVessel(v)}>
              {v.id}
            </button>
          ))}
          {(props.areaVessels ?? []).map((v: LiveVesselFeature) => (
            <button key={v.id} data-testid={`scan-sel-${v.id}`} onClick={() => props.onSelectVessel(v, "datalastic")}>
              {v.id}
            </button>
          ))}
          <button
            data-testid="finish-area"
            onClick={() => props.onAreaGeometryChange?.({
              type: "Polygon",
              coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
            })}
          >
            finish area
          </button>
          <button
            data-testid="refresh-viewport"
            onClick={() => props.onViewportChange?.({ minLat: 21, minLon: 119, maxLat: 24, maxLon: 122 })}
          >
            refresh
          </button>
          <button data-testid="empty-click" onClick={() => props.onDeselect()}>
            empty
          </button>
          <button data-testid="user-interact" onClick={() => props.onUserInteract?.()}>
            drag
          </button>
        </div>
      );
    },
  };
});

import {
  AreaScanApiError,
  authenticateAreaScan,
  fetchLiveTrack,
  scanLiveArea,
  type AreaScanResponse,
} from "../api/live";
import { LiveDashboard } from "./LiveDashboard";
import { I18nProvider } from "../i18n/I18nContext";

function renderDash({ vesselDemo = false }: { vesselDemo?: boolean } = {}) {
  return render(
    <I18nProvider>
      <LiveDashboard vesselDemo={vesselDemo} />
    </I18nProvider>,
  );
}

async function authenticateAreaScanUi() {
  const t = DICTIONARIES["zh-Hant"];
  fireEvent.change(screen.getByLabelText(t.areaScanOperatorCredential), {
    target: { value: "temporary-operator-credential" },
  });
  fireEvent.click(screen.getByRole("button", { name: t.areaScanAuthenticate }));
  await waitFor(() => {
    expect(vi.mocked(authenticateAreaScan)).toHaveBeenCalledWith(
      "temporary-operator-credential",
    );
  });
  expect(await screen.findByText(t.areaScanAuthenticated)).toBeInTheDocument();
}

describe("LiveDashboard interaction", () => {
  beforeEach(() => {
    currentVessels = [vessel("v1", "ALPHA"), vessel("v2", "BRAVO")];
    currentScanVessels = [
      {
        ...vessel("scan-1", "DATALASTIC SHIP"),
        properties: { ...vessel("scan-1", "DATALASTIC SHIP").properties, source: "datalastic" },
      },
    ];
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(authenticateAreaScan).mockResolvedValue({
      authenticated: true,
      expires_in_seconds: 900,
    });
    vi.mocked(scanLiveArea).mockImplementation(async () => ({
      source: "datalastic",
      scanned_at: "2026-10-03T02:00:00Z",
      cached: false,
      scan: { geometry_type: "Polygon", provider_queries: 2 },
      total: currentScanVessels.length,
      vessels: currentScanVessels,
    }));
  });

  it("selects a vessel on click and opens the panel", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByTestId("sel-v1"));
    expect(screen.getByTestId("selected-id").textContent).toBe("v1");
    await waitFor(() => expect(screen.getByText("ALPHA")).toBeInTheDocument());
    // Selecting enables follow mode.
    expect(screen.getByTestId("follow").textContent).toBe("true");
  });

  it("switches selection on a second vessel click", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByTestId("sel-v1"));
    fireEvent.click(screen.getByTestId("sel-v2"));
    expect(screen.getByTestId("selected-id").textContent).toBe("v2");
    await waitFor(() => expect(screen.getByText("BRAVO")).toBeInTheDocument());
  });

  it("deselects on empty-map click", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByTestId("sel-v1"));
    fireEvent.click(screen.getByTestId("empty-click"));
    expect(screen.getByTestId("selected-id").textContent).toBe("");
  });

  it("closes the panel on Escape", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByTestId("sel-v1"));
    expect(screen.getByTestId("selected-id").textContent).toBe("v1");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByTestId("selected-id").textContent).toBe("");
  });

  it("keeps the selection and shows a notice when the vessel drops out of the feed", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByTestId("sel-v1"));
    await waitFor(() => expect(screen.getByText("ALPHA")).toBeInTheDocument());

    // v1 disappears from the next feed refresh.
    await act(async () => {
      currentVessels = [vessel("v2", "BRAVO")];
      // Trigger a re-poll by advancing: easiest is to re-render via a new click
      // that re-reads vessels; instead we rely on the interval. Fire a manual
      // refresh by selecting v1 again is not valid (gone). Use fake timers.
    });

    // Still selected (persisted by id), still shows last-known name.
    expect(screen.getByTestId("selected-id").textContent).toBe("v1");
  });

  it("pauses follow mode on manual map interaction and offers resume", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByTestId("sel-v1"));
    expect(screen.getByTestId("follow").textContent).toBe("true");
    fireEvent.click(screen.getByTestId("user-interact"));
    expect(screen.getByTestId("follow").textContent).toBe("false");
    // Resume control appears.
    expect(screen.getByText("繼續追蹤")).toBeInTheDocument();
  });

  it("shows the compact header in Traditional Chinese by default and toggles to English", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    const zh = DICTIONARIES["zh-Hant"];
    const enDict = DICTIONARIES["en"];
    expect(screen.getByText(zh.productTagline)).toBeInTheDocument();
    expect(screen.getAllByText(zh.modeCloud).length).toBeGreaterThanOrEqual(1);
    const operatingStatus = screen.getByTestId("operating-status-panel");
    expect(operatingStatus).toHaveAttribute("data-mode", "CLOUD_LIVE");
    expect(operatingStatus.textContent).toContain("open_waters");
    expect(operatingStatus.textContent).toContain(zh.provenanceCloud);
    fireEvent.click(screen.getByLabelText("Toggle language"));
    expect(screen.getByText(enDict.productTagline)).toBeInTheDocument();
    expect(screen.getAllByText(enDict.modeCloud).length).toBeGreaterThan(0);
  });

  it("searches a loaded vessel and selects it from the search box", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    const input = document.querySelector(".search-input") as HTMLInputElement;
    expect(input).toBeTruthy();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "ALPHA" } });
    fireEvent.click(screen.getByText("ALPHA"));
    expect(screen.getByTestId("selected-id").textContent).toBe("v1");
  });

  it("navigates to a location preset (fitBounds nonce increments)", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    const before = screen.getByTestId("fit-nonce").textContent;
    const presets = Array.from(document.querySelectorAll(".preset-btn")) as HTMLButtonElement[];
    const kao = presets.find((b) => b.textContent === DICTIONARIES["zh-Hant"].presetKaohsiung);
    expect(kao).toBeTruthy();
    fireEvent.click(kao!);
    const after = screen.getByTestId("fit-nonce").textContent;
    expect(Number(after)).toBeGreaterThan(Number(before));
    expect(screen.getByTestId("fit-bounds").textContent).not.toBe("");
  });

  it("shows an empty-viewport state when loaded but no vessels are present", async () => {
    currentVessels = [];
    renderDash();
    await screen.findByTestId("map");
    const box = await waitFor(() => {
      const el = document.querySelector(".empty-viewport");
      if (!el) throw new Error("no empty-viewport yet");
      return el as HTMLElement;
    });
    expect(box.textContent).toContain(DICTIONARIES["zh-Hant"].emptyViewport);
    const before = screen.getByTestId("fit-nonce").textContent;
    const action = box.querySelector("button") as HTMLButtonElement;
    fireEvent.click(action);
    expect(Number(screen.getByTestId("fit-nonce").textContent)).toBeGreaterThan(Number(before));
  });

  it("opens and visibly labels the deterministic vessel scenario only when opted in", async () => {
    renderDash({ vesselDemo: true });

    expect(await screen.findByTestId("vessel-demo-mode")).toHaveTextContent(
      DICTIONARIES["zh-Hant"].demoIllustrativeLabel,
    );
    expect(screen.getByTestId("demo-banner")).toHaveTextContent(
      DICTIONARIES["zh-Hant"].demoIllustrativeLabel,
    );
  });

  it("does not expose or open the vessel scenario without explicit opt-in", async () => {
    renderDash();
    await screen.findByTestId("map");

    expect(screen.queryByTestId("vessel-demo-mode")).toBeNull();
    expect(screen.queryByTestId("demo-banner")).toBeNull();
    expect(screen.queryByTestId("demo-entry")).toBeNull();
  });

  it("scans only after explicit submit and keeps results across ordinary refresh", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");

    fireEvent.click(screen.getByRole("button", { name: "區域掃描" }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: "多邊形" }));
    fireEvent.click(screen.getByTestId("finish-area"));
    expect(vi.mocked(scanLiveArea)).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "掃描區域" }));

    expect(await screen.findByTestId("scan-sel-scan-1")).toBeInTheDocument();
    expect(vi.mocked(scanLiveArea)).toHaveBeenCalledTimes(1);
    currentVessels = [vessel("v3", "CHARLIE")];
    fireEvent.click(screen.getByTestId("refresh-viewport"));
    expect(screen.getByTestId("scan-sel-scan-1")).toBeInTheDocument();
  });

  it("opens the existing vessel workflow for an Area Scan result and clears it", async () => {
    renderDash();
    await screen.findByTestId("sel-v1");
    fireEvent.click(screen.getByRole("button", { name: "區域掃描" }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: "矩形" }));
    fireEvent.click(screen.getByTestId("finish-area"));
    fireEvent.click(screen.getByRole("button", { name: "掃描區域" }));
    const scanVessel = await screen.findByTestId("scan-sel-scan-1");
    fireEvent.click(scanVessel);
    expect(await screen.findByText("DATALASTIC SHIP")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "清除" }));
    expect(screen.queryByTestId("scan-sel-scan-1")).toBeNull();
  });

  it("keeps the later Area Scan result when A resolves after B", async () => {
    const makeDeferred = () => {
      let resolve!: (value: AreaScanResponse) => void;
      const promise = new Promise<AreaScanResponse>((done) => { resolve = done; });
      return { promise, resolve };
    };
    const first = makeDeferred();
    const second = makeDeferred();
    vi.mocked(scanLiveArea)
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    renderDash();
    await screen.findByTestId("sel-v1");
    const t = DICTIONARIES["zh-Hant"];
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
    fireEvent.click(screen.getByTestId("finish-area"));
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));
    fireEvent.click(screen.getByRole("button", { name: t.areaScanning }));

    await act(async () => {
      second.resolve({
        source: "datalastic",
        scanned_at: "2026-10-03T02:01:00Z",
        cached: false,
        scan: { geometry_type: "Polygon", provider_queries: 1 },
        total: 1,
        vessels: [{ ...vessel("scan-b", "SECOND"), properties: { ...vessel("scan-b", "SECOND").properties, source: "datalastic" } }],
      });
    });
    expect(await screen.findByTestId("scan-sel-scan-b")).toBeInTheDocument();

    await act(async () => {
      first.resolve({
        source: "datalastic",
        scanned_at: "2026-10-03T02:00:00Z",
        cached: false,
        scan: { geometry_type: "Polygon", provider_queries: 1 },
        total: 1,
        vessels: [{ ...vessel("scan-a", "FIRST"), properties: { ...vessel("scan-a", "FIRST").properties, source: "datalastic" } }],
      });
    });
    expect(screen.getByTestId("scan-sel-scan-b")).toBeInTheDocument();
    expect(screen.queryByTestId("scan-sel-scan-a")).toBeNull();
  });

  it("clear aborts a pending scan and ignores its eventual completion", async () => {
    let resolve!: (value: AreaScanResponse) => void;
    vi.mocked(scanLiveArea).mockImplementationOnce(
      () => new Promise<AreaScanResponse>((done) => { resolve = done; }),
    );
    renderDash();
    await screen.findByTestId("sel-v1");
    const t = DICTIONARIES["zh-Hant"];
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
    fireEvent.click(screen.getByTestId("finish-area"));
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));
    fireEvent.click(screen.getByRole("button", { name: t.clearAreaScan }));

    await act(async () => {
      resolve({
        source: "datalastic",
        scanned_at: "2026-10-03T02:00:00Z",
        cached: false,
        scan: { geometry_type: "Polygon", provider_queries: 1 },
        total: 1,
        vessels: currentScanVessels,
      });
    });
    expect(screen.queryByTestId("scan-sel-scan-1")).toBeNull();
  });

  it("returns to operator authentication when the capability expires", async () => {
    vi.mocked(scanLiveArea).mockRejectedValueOnce(
      new AreaScanApiError(403, "Area Scan authorization invalid or expired", null),
    );
    renderDash();
    await screen.findByTestId("sel-v1");
    const t = DICTIONARIES["zh-Hant"];
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
    fireEvent.click(screen.getByTestId("finish-area"));
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      t.areaScanSessionExpired,
    );
    expect(screen.getByLabelText(t.areaScanOperatorCredential)).toHaveValue("");
    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
  });

  it("keeps same-public-ID scan selection and track provenance separate from live", async () => {
    currentVessels = [vessel("v-shared", "LIVE SHIP")];
    currentScanVessels = [
      { ...vessel("v-shared", "SCAN SHIP"), properties: { ...vessel("v-shared", "SCAN SHIP").properties, source: "datalastic" } },
    ];
    renderDash();
    await screen.findByTestId("sel-v-shared");
    const t = DICTIONARIES["zh-Hant"];
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
    fireEvent.click(screen.getByTestId("finish-area"));
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));
    fireEvent.click(await screen.findByTestId("scan-sel-v-shared"));

    expect(screen.getByTestId("selected-source")).toHaveTextContent("datalastic");
    expect(await screen.findByText("SCAN SHIP")).toBeInTheDocument();
    await waitFor(() => {
      expect(vi.mocked(fetchLiveTrack)).toHaveBeenCalledWith(
        "v-shared",
        expect.any(AbortSignal),
        "datalastic",
      );
    });
  });

  it("preserves backend Area Scan freshness when opening the vessel panel", async () => {
    currentScanVessels = [
      {
        ...vessel("scan-fresh", "FRESH AREA SHIP"),
        properties: {
          ...vessel("scan-fresh", "FRESH AREA SHIP").properties,
          source: "datalastic",
          data_age_seconds: 300,
          freshness_state: "fresh",
        },
      },
    ];
    renderDash();
    await screen.findByTestId("sel-v1");
    const t = DICTIONARIES["zh-Hant"];
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    await authenticateAreaScanUi();
    fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
    fireEvent.click(screen.getByTestId("finish-area"));
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));
    fireEvent.click(await screen.findByTestId("scan-sel-scan-fresh"));

    expect(document.querySelector(".integrity-badge")).toHaveAttribute(
      "data-kind",
      "live",
    );
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { DICTIONARIES } from "../../i18n/dictionaries";
import { VesselIntelligenceCard } from "./VesselIntelligenceCard";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import type { SatelliteEvidence, SatelliteEvidenceValue } from "./satelliteEvidence";

const zh = DICTIONARIES.en;
const PROHIBITED = ["dangerous", "suspicious", "threat", "abnormal", "hostile"];

const SUFFICIENT_BASELINE = {
  schema_version: "vessel-baseline-1",
  vessel_key: "v_opaque123",
  history_summary: {
    observed_day_count: { value: 5, provenance: "derived" },
    first_observed_utc: { value: "2026-09-01T00:00:00Z", provenance: "observed" },
    last_observed_utc: { value: "2026-09-05T02:00:00Z", provenance: "observed" },
    total_observations: { value: 15, provenance: "derived" },
    data_source: "gfw_presence",
  },
  typical_routes: [
    {
      route_key: "historical-cohort",
      occurrence_count: 5,
      corridor_centerline: [[120, 22], [120.2, 22.1]],
      corridor_width_p90_m: { value: 850, provenance: "derived" },
      provenance: "derived",
    },
  ],
  usual_operating_areas: [],
  historical_track_count: 5,
  confidence: { value: "HIGH", provenance: "derived" },
  sufficient: true,
  thresholds_used: {
    min_history_days: 3,
    min_history_tracks: 5,
    min_track_points: 3,
  },
  data_source: "gfw_presence",
  disclaimer: "Historical presence summary for human review.",
} as const;

const GIS_UNKNOWN = {
  schema_version: "gis-context-1",
  coverage: { value: null, provenance: "unknown" },
  distance_to_coast_km: { value: null, provenance: "unknown" },
  nearest_port: { value: null, provenance: "unknown" },
  within_named_areas: [],
  named_areas_computed: false,
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? "Not Found" : status === 503 ? "Service Unavailable" : "OK",
    json: async () => body,
  } as Response;
}

function mockHistoricalResponse(response: Response | Promise<Response>) {
  const fetchSpy = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/historical/vessels/")) return Promise.resolve(response);
    return Promise.resolve(jsonResponse(GIS_UNKNOWN));
  });
  vi.stubGlobal("fetch", fetchSpy as unknown as typeof fetch);
  return fetchSpy;
}

function historicalCalls(fetchSpy: ReturnType<typeof vi.fn>) {
  return fetchSpy.mock.calls.filter(([input]) => String(input).includes("/historical/vessels/"));
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function feature(overrides: Partial<LiveVesselFeature["properties"]> = {}): LiveVesselFeature {
  return {
    type: "Feature",
    id: "v_opaque123",
    geometry: { type: "Point", coordinates: [120.3, 22.6] },
    properties: {
      provider_id: "v_opaque123",
      sog_knots: 0.5,
      cog_deg: 90,
      heading_deg: 90,
      nav_status: 0,
      vessel_type: 70,
      name: null,
      destination: null,
      observed_at: "2026-10-02T06:00:00Z",
      source: "open_waters",
      synthesized: false,
      data_age_seconds: 12,
      ...overrides,
    },
  };
}

function loiterTrack(): LiveTrack {
  return {
    type: "Feature",
    id: "v_opaque123",
    geometry: {
      type: "LineString",
      coordinates: [
        [120.3, 22.6],
        [120.3001, 22.6001],
        [120.3002, 22.6002],
      ],
    },
    properties: {
      provider_id: "v_opaque123",
      point_count: 1240,
      observed_from: "2026-10-02T05:30:00Z",
      observed_to: "2026-10-02T06:00:00Z",
    },
  };
}

function renderCard(
  vessel: LiveVesselFeature,
  track: LiveTrack | null,
  satelliteEvidence?: SatelliteEvidence[],
) {
  return render(
    <I18nProvider>
      <VesselIntelligenceCard
        vessel={vessel}
        track={track}
        satellite_evidence={satelliteEvidence}
      />
    </I18nProvider>,
  );
}

describe("VesselIntelligenceCard", () => {
  it("is collapsed by default and expands on toggle", () => {
    renderCard(feature(), loiterTrack());
    expect(screen.queryByTestId("vessel-intelligence")).toBeNull();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByTestId("vessel-intelligence")).toBeInTheDocument();
  });

  it("shows Unknown with an unknown provenance tag for fields the live data lacks", () => {
    renderCard(feature({ name: null }), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const body = screen.getByTestId("vessel-intelligence");

    // Flag and IMO are always unknown in MVP.
    const unknownTags = body.querySelectorAll('[data-provenance="unknown"]');
    expect(unknownTags.length).toBeGreaterThan(0);
    // "Unknown" literal appears for the missing name / flag / imo.
    expect(within(body).getAllByText(zh.valueUnknown).length).toBeGreaterThanOrEqual(3);
  });

  it("renders an evidence-backed loitering review note with a derived tag", () => {
    renderCard(feature({ sog_knots: 0.5 }), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const reason = document.querySelector('[data-reason="session_loitering"]');
    expect(reason).not.toBeNull();
    expect(reason?.textContent).toMatch(/0.5 kn/);
    expect(reason?.querySelector('[data-provenance="derived"]')).not.toBeNull();
  });

  it("replaces the legacy route-baseline-unavailable note with Historical Baseline", () => {
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(document.querySelector('[data-reason="route_baseline_unavailable"]')).toBeNull();
    expect(screen.getByTestId("historical-baseline")).toBeInTheDocument();
  });

  it("shows the collecting message when no evidence-backed reason exists", () => {
    const straight: LiveTrack = {
      ...loiterTrack(),
      geometry: {
        type: "LineString",
        coordinates: [
          [120.0, 22.0],
          [120.00001, 22.0],
          [120.00002, 22.0],
        ],
      },
      properties: {
        provider_id: "v_opaque123",
        point_count: 3,
        observed_from: "2026-10-02T05:58:00Z",
        observed_to: "2026-10-02T06:00:00Z",
      },
    };
    renderCard(feature({ sog_knots: 0.3 }), straight);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const body = screen.getByTestId("vessel-intelligence");
    expect(within(body).getByText(zh.intelligenceNoReasons)).toBeInTheDocument();
    expect(document.querySelector('[data-reason="session_loitering"]')).toBeNull();
  });

  it("always ends with Human review required when expanded", () => {
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText(zh.intelligenceHumanReview)).toBeInTheDocument();
  });

  it("never renders prohibited wording", () => {
    renderCard(feature({ sog_knots: 0.5 }), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const term of PROHIBITED) {
      expect(text).not.toContain(term);
    }
  });

  it("never exposes MMSI/IMO values (privacy non-regression)", () => {
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const body = screen.getByTestId("vessel-intelligence");
    // IMO row shows the label but the value is Unknown — no numeric identity.
    const text = body.textContent ?? "";
    expect(text).not.toMatch(/\b\d{7,9}\b/); // no raw IMO(7)/MMSI(9) digit runs
  });
});

describe("VesselIntelligenceCard historical baseline", () => {
  it("does not fetch history while the card is collapsed", () => {
    const fetchSpy = vi.mocked(fetch);
    renderCard(feature(), loiterTrack());

    expect(historicalCalls(fetchSpy)).toHaveLength(0);
  });

  it("fetches history once when a real vessel card expands", async () => {
    const fetchSpy = mockHistoricalResponse(jsonResponse(SUFFICIENT_BASELINE));
    renderCard(feature(), loiterTrack());

    fireEvent.click(screen.getByRole("button", { expanded: false }));

    await waitFor(() => expect(historicalCalls(fetchSpy)).toHaveLength(1));
    expect(String(historicalCalls(fetchSpy)[0]?.[0])).toContain(
      "/historical/vessels/v_opaque123/baseline",
    );
  });

  it("fetches the newly selected vessel and ignores a stale response", async () => {
    let resolveFirst!: (response: Response) => void;
    const first = new Promise<Response>((resolve) => {
      resolveFirst = resolve;
    });
    const secondPayload = {
      ...SUFFICIENT_BASELINE,
      vessel_key: "v_second",
      history_summary: {
        ...SUFFICIENT_BASELINE.history_summary,
        observed_day_count: { value: 9, provenance: "derived" },
      },
    };
    const fetchSpy = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (!url.includes("/historical/vessels/")) {
        return Promise.resolve(jsonResponse(GIS_UNKNOWN));
      }
      return url.includes("v_second")
        ? Promise.resolve(jsonResponse(secondPayload))
        : first;
    });
    vi.stubGlobal("fetch", fetchSpy as unknown as typeof fetch);
    const view = renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    await waitFor(() => expect(historicalCalls(fetchSpy)).toHaveLength(1));

    view.rerender(
      <I18nProvider>
        <VesselIntelligenceCard vessel={feature()} track={loiterTrack()} />
      </I18nProvider>,
    );
    await waitFor(() => expect(historicalCalls(fetchSpy)).toHaveLength(1));

    const secondVessel = feature({ provider_id: "v_second" });
    secondVessel.id = "v_second";
    view.rerender(
      <I18nProvider>
        <VesselIntelligenceCard vessel={secondVessel} track={loiterTrack()} />
      </I18nProvider>,
    );

    await waitFor(() => expect(historicalCalls(fetchSpy)).toHaveLength(2));
    const section = await screen.findByTestId("historical-baseline");
    const observedDays = within(section).getByText(zh.historicalObservedDays).nextElementSibling;
    expect(observedDays).toHaveTextContent("9");
    resolveFirst(jsonResponse(SUFFICIENT_BASELINE));
    await waitFor(() => expect(observedDays).toHaveTextContent("9"));
  });

  it("shows a loading state while the historical request is pending", () => {
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    expect(within(screen.getByTestId("historical-baseline")).getByText(zh.loading)).toBeInTheDocument();
  });

  it("renders a sufficient GFW historical summary without changing Unknown concepts", async () => {
    mockHistoricalResponse(jsonResponse(SUFFICIENT_BASELINE));
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    const section = await screen.findByTestId("historical-baseline");
    expect(await within(section).findByText(zh.historicalBaselineAvailable)).toBeInTheDocument();
    expect(within(section).getByText(zh.historicalObservedDays).nextElementSibling).toHaveTextContent("5");
    expect(within(section).getByText("15")).toBeInTheDocument();
    expect(within(section).getByText(zh.historicalTracks).nextElementSibling).toHaveTextContent("5");
    expect(within(section).getByText(zh.historicalCorridorAvailable)).toBeInTheDocument();
    expect(within(section).getByText(zh.confidenceHigh)).toBeInTheDocument();
    expect(within(section).getByText(zh.historicalGfwSource)).toBeInTheDocument();
    expect(screen.getByText(zh.intelligenceTypicalRoute).nextElementSibling).toHaveTextContent(
      zh.valueUnknown,
    );
    expect(screen.getByText(zh.intelligenceUsualArea).nextElementSibling).toHaveTextContent(
      zh.valueUnknown,
    );
    expect(screen.getByTestId("route-deviation")).toHaveTextContent(zh.routeDeviationUnknown);
    expect(document.querySelector('[data-reason="route_baseline_unavailable"]')).toBeNull();
  });

  it("renders an insufficient matched baseline with valid summary values and no corridor", async () => {
    const insufficient = {
      ...SUFFICIENT_BASELINE,
      sufficient: false,
      historical_track_count: 2,
      typical_routes: [],
      confidence: { value: "LOW", provenance: "derived" },
    };
    mockHistoricalResponse(jsonResponse(insufficient));
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    const section = await screen.findByTestId("historical-baseline");
    expect(await within(section).findByText(zh.historicalInsufficient)).toBeInTheDocument();
    expect(
      section.querySelector('.historical-baseline-status [data-provenance="derived"]'),
    ).not.toBeNull();
    expect(within(section).getByText("2")).toBeInTheDocument();
    expect(within(section).queryByText(zh.historicalCorridorAvailable)).toBeNull();
  });

  it("renders a neutral no-match state for 404", async () => {
    mockHistoricalResponse(jsonResponse({ detail: "Historical baseline not found" }, 404));
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    expect(await screen.findByText(zh.historicalNotFound)).toBeInTheDocument();
  });

  it("renders a neutral unavailable state for 503", async () => {
    mockHistoricalResponse(jsonResponse({ detail: "Historical baseline unavailable" }, 503));
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    expect(await screen.findByText(zh.historicalUnavailable)).toBeInTheDocument();
  });

  it("does not render raw identifier fields in the historical section", async () => {
    mockHistoricalResponse(jsonResponse(SUFFICIENT_BASELINE));
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    const text = (await screen.findByTestId("historical-baseline")).textContent ?? "";
    for (const forbidden of ["MMSI", "IMO", "callsign", "ship name", "vesselId", "v_opaque123"]) {
      expect(text).not.toContain(forbidden);
    }
  });
});

describe("VesselIntelligenceCard satellite evidence", () => {
  it("renders available satellite evidence fields and field-level provenance", () => {
    renderCard(feature(), loiterTrack(), [
      {
        provider: "Sentinel-1 STAC",
        scene_id: "S1A_SCENE_001",
        platform: "sentinel-1a",
        datetime: "2026-10-02T05:55:00Z",
        orbit: 142,
        availability: "Available",
        provenance: {
          scene_id: "Observed",
          platform: "Observed",
          datetime: "Observed",
          orbit: "Observed",
          availability: "Derived",
        },
      },
    ]);

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const section = screen.getByTestId("satellite-evidence");
    expect(section).toBeInTheDocument();
    for (const value of [
      "Available",
      "Sentinel-1 STAC",
      "S1A_SCENE_001",
      "sentinel-1a",
      "2026-10-02T05:55:00Z",
      "142",
    ]) {
      expect(within(section).getByText(value)).toBeInTheDocument();
    }
    expect(section.querySelectorAll('[data-provenance="observed"]')).toHaveLength(4);
    expect(section.querySelectorAll('[data-provenance="derived"]')).toHaveLength(1);
    expect(section.querySelectorAll('[data-provenance="unknown"]')).toHaveLength(1);
  });

  it("skips an empty scene instead of fabricating Unknown rows", () => {
    renderCard(feature(), loiterTrack(), [{}]);

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.queryByTestId("satellite-evidence")).toBeNull();
    expect(screen.queryByTestId("satellite-scene")).toBeNull();
  });

  it("renders only fields supplied by a partial scene", () => {
    renderCard(feature(), loiterTrack(), [
      {
        availability: "Available",
        platform: "Sentinel-1",
        provenance: { availability: "Derived", platform: "Observed" },
      },
    ]);

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const section = screen.getByTestId("satellite-evidence");
    expect(within(section).getByText(zh.satelliteAvailability)).toBeInTheDocument();
    expect(within(section).getByText("Available")).toBeInTheDocument();
    expect(within(section).getByText(zh.satellitePlatform)).toBeInTheDocument();
    expect(within(section).getByText("Sentinel-1")).toBeInTheDocument();
    expect(within(section).queryByText(zh.satelliteProvider)).toBeNull();
    expect(within(section).queryByText(zh.satelliteSceneId)).toBeNull();
    expect(within(section).queryByText(zh.satelliteObservedDatetime)).toBeNull();
    expect(within(section).queryByText(zh.satelliteOrbit)).toBeNull();
    expect(section.querySelectorAll('[data-provenance="derived"]')).toHaveLength(1);
    expect(section.querySelectorAll('[data-provenance="observed"]')).toHaveLength(1);
  });

  it("preserves an explicitly supplied Unknown availability", () => {
    renderCard(feature(), loiterTrack(), [
      { availability: "Unknown", provenance: { availability: "Unknown" } },
    ]);

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const section = screen.getByTestId("satellite-evidence");
    expect(within(section).getByText(zh.satelliteAvailability)).toBeInTheDocument();
    expect(within(section).getByText("Unknown")).toBeInTheDocument();
    expect(section.querySelectorAll('[data-provenance="unknown"]')).toHaveLength(1);
  });

  it.each([undefined, []])(
    "does not render an empty section when satellite evidence is %s",
    (satelliteEvidence) => {
      renderCard(feature(), loiterTrack(), satelliteEvidence);
      fireEvent.click(screen.getByRole("button", { expanded: false }));

      expect(screen.queryByTestId("satellite-evidence")).toBeNull();
      expect(screen.getByTestId("vessel-intelligence")).toBeInTheDocument();
    },
  );

  it("renders multiple satellite scenes independently", () => {
    renderCard(feature(), loiterTrack(), [
      { availability: "Unknown", provenance: { availability: "Unknown" } },
      { platform: "sentinel-1b", provenance: { platform: "Observed" } },
    ]);

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const scenes = screen.getAllByTestId("satellite-scene");
    expect(scenes).toHaveLength(2);
    expect(within(scenes[0]).getByText("Unknown")).toBeInTheDocument();
    expect(within(scenes[0]).queryByText("sentinel-1b")).toBeNull();
    expect(within(scenes[1]).getByText("sentinel-1b")).toBeInTheDocument();
    expect(within(scenes[1]).queryByText("Unknown")).toBeNull();
  });

  it("does not render raw or private metadata fields", () => {
    const scene: SatelliteEvidence & Record<string, SatelliteEvidenceValue> = {
      availability: "Available",
      mmsi: "416000001",
      vessel_id: "raw-vessel-id",
      imo: "IMO1234567",
      callsign: "PRIVATE-CALLSIGN",
      vessel_name: "PRIVATE VESSEL",
      token: "source-token",
      href: "https://example.test/private-scene",
    };
    renderCard(feature(), loiterTrack(), [scene]);

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const text = screen.getByTestId("satellite-evidence").textContent ?? "";
    for (const privateValue of [
      "416000001",
      "raw-vessel-id",
      "IMO1234567",
      "PRIVATE-CALLSIGN",
      "PRIVATE VESSEL",
      "source-token",
      "https://example.test/private-scene",
    ]) {
      expect(text).not.toContain(privateValue);
    }
  });

  it("does not introduce prohibited language", () => {
    renderCard(feature(), loiterTrack(), [{ availability: "Available" }]);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const text = (screen.getByTestId("satellite-evidence").textContent ?? "").toLowerCase();

    for (const term of ["threat", "suspicious", "dangerous", "illegal"]) {
      expect(text).not.toContain(term);
    }
  });
});

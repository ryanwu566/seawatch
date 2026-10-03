import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { DICTIONARIES } from "../../i18n/dictionaries";
import { VesselIntelligenceCard } from "./VesselIntelligenceCard";
import { readRouteDeviation, UNKNOWN_ROUTE_DEVIATION } from "./routeDeviation";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import type { GeographicContext, RouteDeviationEvidence } from "./geographicTypes";

const zh = DICTIONARIES.en;
// Forbidden words per task spec, plus the broader card guard list.
const PROHIBITED = ["threat", "suspicious", "dangerous", "illegal", "abnormal", "hostile"];

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

function baseTrack(): LiveTrack {
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

function deviationEvidence(): RouteDeviationEvidence {
  return {
    schemaVersion: "route-deviation-1",
    track_ref: "v_opaque123",
    route_key: "keelung->taichung",
    deviation_distance_m: {
      value: 4100,
      provenance: "derived",
      note: "max cross-track to historical median corridor",
    },
    deviation_p95_m: { value: 3900, provenance: "derived" },
    deviation_ratio: { value: 2.4, provenance: "derived" },
    baseline_source: {
      value: {
        method: "Historical median corridor",
        contributing_track_count: 12,
        corridor_width_p90_m: 1700,
      },
      provenance: "derived",
    },
    confidence: "HIGH",
    evidence: [
      {
        id: "cross_track",
        statement:
          "Current track departs from the historical median corridor for this origin–destination pair.",
        confidence: "HIGH",
        source: "trajectory_derived",
        provenance: "derived",
        evidence: "max 4.1 km (p95 3.9 km) vs ~1.7 km corridor",
      },
    ],
    disclaimer: "Decision support for human review only.",
  };
}

/** A track carrying optional route-deviation evidence (backend-attached shape). */
function trackWithDeviation(ev: RouteDeviationEvidence): LiveTrack {
  const t = baseTrack();
  return { ...t, properties: { ...t.properties, route_deviation: ev } as LiveTrack["properties"] };
}

function gisInCoverage(): GeographicContext {
  return {
    schema_version: "gis-context-1",
    coverage: { value: "in_coverage", provenance: "derived" },
    distance_to_coast_km: { value: 2.3, provenance: "derived", source: "Natural Earth" },
    nearest_port: {
      value: { id: "kaohsiung", name_zh: "高雄港", name_en: "Kaohsiung", distance_km: 5.1 },
      provenance: "derived",
      source: "COMMERCIAL_PORTS",
    },
    within_named_areas: [
      {
        id: "kaohsiung_approach",
        name_zh: "高雄港進場區",
        name_en: "Kaohsiung approach",
        kind: "approach",
      },
    ],
    named_areas_computed: true,
    disclaimer: "Geographic context for human review only.",
  };
}

function mockFetchJson(payload: unknown, ok = true): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      status: ok ? 200 : 500,
      statusText: ok ? "OK" : "Error",
      json: async () => payload,
    })) as unknown as typeof fetch,
  );
}

function renderCard(vessel: LiveVesselFeature, track: LiveTrack | null) {
  return render(
    <I18nProvider>
      <VesselIntelligenceCard vessel={vessel} track={track} />
    </I18nProvider>,
  );
}

function expand(): void {
  fireEvent.click(screen.getByRole("button", { expanded: false }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("readRouteDeviation", () => {
  it("defaults to an all-Unknown view when the track is null", () => {
    expect(readRouteDeviation(null)).toEqual(UNKNOWN_ROUTE_DEVIATION);
  });

  it("defaults to Unknown when the track carries no route-deviation evidence", () => {
    expect(readRouteDeviation(baseTrack())).toEqual(UNKNOWN_ROUTE_DEVIATION);
  });

  it("surfaces derived evidence with distance in km, baseline, confidence and source", () => {
    const view = readRouteDeviation(trackWithDeviation(deviationEvidence()));
    expect(view.statusKey).toBe("route_deviation_detected");
    expect(view.statusProvenance).toBe("derived");
    expect(view.deviationKm).toBe(4.1);
    expect(view.deviationProvenance).toBe("derived");
    expect(view.baseline).toBe("Historical median corridor");
    expect(view.baselineProvenance).toBe("derived");
    expect(view.confidence).toBe("HIGH");
    expect(view.source).toBe("Trajectory derived");
  });

  it("stays Unknown when the backend produced an unknown (insufficient baseline) result", () => {
    const ev = deviationEvidence();
    const unknownEv: RouteDeviationEvidence = {
      ...ev,
      deviation_distance_m: { value: null, provenance: "unknown", note: "insufficient" },
      deviation_ratio: { value: null, provenance: "unknown" },
      baseline_source: { value: { method: "historical median corridor" }, provenance: "unknown" },
      confidence: "LOW",
      evidence: [
        {
          id: "baseline_insufficient",
          statement: "No sufficient historical baseline is available for this route.",
          confidence: "LOW",
          source: "trajectory_derived",
          provenance: "unknown",
        },
      ],
    };
    const view = readRouteDeviation(trackWithDeviation(unknownEv));
    expect(view.deviationKm).toBeNull();
    expect(view.deviationProvenance).toBe("unknown");
    expect(view.statusProvenance).toBe("unknown");
    expect(view.confidence).toBeNull();
  });
});

describe("Route Deviation section (rendered)", () => {
  it("renders the five fields with values when evidence is present", async () => {
    mockFetchJson(gisInCoverage());
    renderCard(feature(), trackWithDeviation(deviationEvidence()));
    expand();
    const section = screen.getByTestId("route-deviation");
    expect(within(section).getByText(zh.routeDeviationDetected)).toBeInTheDocument();
    expect(section.querySelector('[data-field="distance"]')?.textContent).toMatch(/4\.1 km/);
    expect(section.querySelector('[data-field="baseline"]')?.textContent).toMatch(
      /Historical median corridor/,
    );
    expect(section.querySelector('[data-field="confidence"]')?.textContent).toContain(
      zh.confidenceHigh,
    );
    expect(section.querySelector('[data-field="source"]')?.textContent).toContain(
      "Trajectory derived",
    );
    // Status/distance/baseline carry a derived provenance tag.
    expect(section.querySelector('[data-provenance="derived"]')).not.toBeNull();
  });

  it("shows Unknown for every field and an unknown note when no evidence exists", async () => {
    mockFetchJson(gisInCoverage());
    renderCard(feature(), baseTrack());
    expand();
    const section = screen.getByTestId("route-deviation");
    expect(within(section).getByText(zh.routeDeviationUnknown)).toBeInTheDocument();
    expect(section.querySelector('[data-field="distance"]')?.textContent).toContain(
      zh.valueUnknown,
    );
    expect(section.querySelector('[data-field="status"]')?.textContent).toContain(zh.valueUnknown);
    expect(section.querySelectorAll('[data-provenance="unknown"]').length).toBeGreaterThan(0);
  });
});

describe("Geographic Context section (rendered)", () => {
  it("renders coast distance, nearest port, distance to port and maritime area", async () => {
    mockFetchJson(gisInCoverage());
    renderCard(feature(), baseTrack());
    expand();
    const section = screen.getByTestId("geographic-context");
    await waitFor(() =>
      expect(section.querySelector('[data-field="coast"]')?.textContent).toMatch(/2\.3 km/),
    );
    expect(section.querySelector('[data-field="port"]')?.textContent).toContain("Kaohsiung");
    expect(section.querySelector('[data-field="port-distance"]')?.textContent).toMatch(/5\.1 km/);
    expect(section.querySelector('[data-field="area"]')?.textContent).toContain("Kaohsiung approach");
    // Port name is official; distance derived.
    expect(section.querySelector('[data-provenance="official"]')).not.toBeNull();
    expect(section.querySelector('[data-provenance="derived"]')).not.toBeNull();
  });

  it("renders Unknown + outside-coverage note when the position is outside coverage", async () => {
    const unknownGis: GeographicContext = {
      schema_version: "gis-context-1",
      coverage: { value: null, provenance: "unknown", note: "outside coverage" },
      distance_to_coast_km: { value: null, provenance: "unknown" },
      nearest_port: { value: null, provenance: "unknown" },
      within_named_areas: [],
      named_areas_computed: false,
      disclaimer: "Geographic context for human review only.",
    };
    mockFetchJson(unknownGis);
    renderCard(feature(), baseTrack());
    expand();
    const section = screen.getByTestId("geographic-context");
    await waitFor(() =>
      expect(within(section).getByText(zh.gisOutsideCoverage)).toBeInTheDocument(),
    );
    expect(section.querySelector('[data-field="coast"]')?.textContent).toContain(zh.valueUnknown);
    expect(section.querySelectorAll('[data-provenance="unknown"]').length).toBeGreaterThan(0);
  });

  it('distinguishes "not within a named area" (derived) from Unknown', async () => {
    const emptyAreas: GeographicContext = { ...gisInCoverage(), within_named_areas: [] };
    mockFetchJson(emptyAreas);
    renderCard(feature(), baseTrack());
    expand();
    const section = screen.getByTestId("geographic-context");
    await waitFor(() =>
      expect(section.querySelector('[data-field="area"]')?.textContent).toContain(
        zh.gisNotWithinArea,
      ),
    );
  });

  it("falls back to Unknown when the context fetch fails", async () => {
    mockFetchJson(null, false);
    renderCard(feature(), baseTrack());
    expand();
    const section = screen.getByTestId("geographic-context");
    await waitFor(() =>
      expect(within(section).getByText(zh.gisOutsideCoverage)).toBeInTheDocument(),
    );
  });
});

describe("Forbidden-word guard across the new sections", () => {
  it("never renders threat/suspicious/dangerous/illegal, even with evidence present", async () => {
    mockFetchJson(gisInCoverage());
    renderCard(feature(), trackWithDeviation(deviationEvidence()));
    expand();
    await waitFor(() =>
      expect(screen.getByTestId("geographic-context")).toBeInTheDocument(),
    );
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const term of PROHIBITED) {
      expect(text).not.toContain(term);
    }
  });

  it("keeps Human review required present with the new sections", async () => {
    mockFetchJson(gisInCoverage());
    renderCard(feature(), trackWithDeviation(deviationEvidence()));
    expand();
    expect(screen.getByText(zh.intelligenceHumanReview)).toBeInTheDocument();
  });
});

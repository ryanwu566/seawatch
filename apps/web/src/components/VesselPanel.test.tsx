import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { DICTIONARIES } from "../i18n/dictionaries";
import { VesselPanel } from "./VesselPanel";
import type { LiveVesselFeature, LiveTrack } from "../api/live";
import { getDemoScenario } from "../features/intelligence/demoScenario";

const zh = DICTIONARIES["zh-Hant"];

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function feature(
  overrides: Partial<LiveVesselFeature["properties"]> = {},
): LiveVesselFeature {
  return {
    type: "Feature",
    id: "v_opaque123",
    geometry: { type: "Point", coordinates: [120.3, 22.6] },
    properties: {
      provider_id: "v_opaque123",
      sog_knots: 12.3,
      cog_deg: 90,
      heading_deg: 90,
      nav_status: 0,
      vessel_type: 70,
      name: "DEMO VESSEL",
      destination: "KHH",
      observed_at: "2026-10-02T06:00:00Z",
      source: "open_waters",
      synthesized: false,
      data_age_seconds: 12,
      ...overrides,
    },
  };
}

function track(): LiveTrack {
  return {
    type: "Feature",
    id: "v_opaque123",
    geometry: {
      type: "LineString",
      coordinates: [
        [120.3, 22.6],
        [120.4, 22.7],
      ],
    },
    properties: {
      provider_id: "v_opaque123",
      point_count: 2,
      observed_from: "2026-10-02T05:30:00Z",
      observed_to: "2026-10-02T06:00:00Z",
    },
  };
}

function renderPanel(vessel: LiveVesselFeature | null) {
  return render(
    <I18nProvider>
      <VesselPanel
        vessel={vessel}
        track={vessel ? track() : null}
        trackLoading={false}
        demo={false}
        onClose={() => {}}
      />
    </I18nProvider>,
  );
}

describe("VesselPanel non-regression with the intelligence card", () => {
  it("renders the existing header, metrics, and sections", () => {
    renderPanel(feature());
    // Header name + speed metric still present.
    expect(screen.getByText("DEMO VESSEL")).toBeInTheDocument();
    expect(screen.getByText("12.3")).toBeInTheDocument();
    // Existing review-priority placeholder still present.
    expect(screen.getByText(zh.collectingForAnalysis)).toBeInTheDocument();
    // Advanced analysis toggle still present.
    expect(
      screen.getByRole("button", { name: new RegExp(zh.advancedAnalysis) }),
    ).toBeInTheDocument();
  });

  it("adds the collapsed Vessel Intelligence section without expanding it", () => {
    renderPanel(feature());
    expect(
      screen.getByRole("button", { name: new RegExp(zh.intelligenceTitle) }),
    ).toBeInTheDocument();
    // Collapsed by default: the body is not rendered.
    expect(screen.queryByTestId("vessel-intelligence")).toBeNull();
  });

  it("passes optional satellite evidence through to Vessel Intelligence", () => {
    render(
      <I18nProvider>
        <VesselPanel
          vessel={feature()}
          track={track()}
          trackLoading={false}
          demo={false}
          satellite_evidence={[{ scene_id: "PANEL_SCENE_001" }]}
          onClose={() => {}}
        />
      </I18nProvider>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: new RegExp(zh.intelligenceTitle) }),
    );
    expect(screen.getByText("PANEL_SCENE_001")).toBeInTheDocument();
  });

  it("still shows the empty hint when no vessel is selected", () => {
    renderPanel(null);
    expect(
      screen.queryByRole("button", { name: new RegExp(zh.intelligenceTitle) }),
    ).toBeNull();
  });

  it("does not expose MMSI/IMO in the default panel view", () => {
    renderPanel(feature());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b\d{9}\b/); // no MMSI
  });
});

describe("VesselPanel demo-only presentation", () => {
  function renderDemoPanel() {
    const { vessel, track, geographicContext } = getDemoScenario();
    return render(
      <I18nProvider>
        <VesselPanel
          vessel={vessel}
          track={track}
          trackLoading={false}
          demo
          demoContext={geographicContext}
          onClose={() => {}}
        />
      </I18nProvider>,
    );
  }

  it("shows DEMO / Illustrative position status and Demo fixture source", () => {
    renderDemoPanel();
    expect(screen.getByText(zh.demoPositionStatus)).toBeInTheDocument();
    expect(screen.getByText(zh.demoSourceLabel)).toBeInTheDocument();
  });

  it("the demo vessel NEVER displays Live AIS as its source", () => {
    renderDemoPanel();
    const source = document.querySelector('[data-field="source"]');
    expect(source?.textContent ?? "").not.toContain(zh.liveSourceLabel);
    expect(source?.textContent ?? "").not.toContain(DICTIONARIES["en"].liveSourceLabel);
    // And it does not read "Offline Demo" for position status either.
    const status = document.querySelector('[data-field="position-status"]');
    expect(status?.textContent).toBe(zh.demoPositionStatus);
  });

  it("keeps DEMO banner, Human review required, Route Deviation, Geographic Context", () => {
    renderDemoPanel();
    expect(screen.getByTestId("demo-banner")).toBeInTheDocument();
    expect(screen.getByText(zh.intelligenceHumanReview)).toBeInTheDocument();
    expect(screen.getByTestId("route-deviation")).toBeInTheDocument();
    expect(screen.getByTestId("geographic-context")).toBeInTheDocument();
  });

  it("never renders prohibited wording", () => {
    renderDemoPanel();
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const term of ["dangerous", "suspicious", "threat", "illegal"]) {
      expect(text).not.toContain(term);
    }
  });
});

describe("VesselPanel live source non-regression", () => {
  it("live vessels still show the Live AIS source label", () => {
    renderPanel(feature()); // demoContext defaults to null → live path
    const source = document.querySelector('[data-field="source"]');
    expect(source?.textContent).toBe(zh.liveSourceLabel);
    // Live position status is NOT the demo label.
    const status = document.querySelector('[data-field="position-status"]');
    expect(status?.textContent).not.toBe(zh.demoPositionStatus);
  });

  it.each([
    [61, "fresh", "live"],
    [300, "fresh", "live"],
    [899, "fresh", "live"],
    [900, "stale", "stale"],
  ] as const)(
    "renders backend Area Scan freshness at age %is as %s",
    (dataAgeSeconds, freshnessState, expectedKind) => {
      renderPanel(feature({
        source: "datalastic",
        data_age_seconds: dataAgeSeconds,
        freshness_state: freshnessState,
      }));

      expect(document.querySelector(".integrity-badge")).toHaveAttribute(
        "data-kind",
        expectedKind,
      );
    },
  );

  it("renders an unknown Area Scan timestamp and age as unknown", () => {
    renderPanel(feature({
      source: "datalastic",
      observed_at: null,
      data_age_seconds: null,
      freshness_state: "unknown",
    }));

    expect(document.querySelector(".integrity-badge")).toHaveAttribute(
      "data-kind",
      "unknown",
    );
    expect(document.querySelector('[data-field="position-status"]')).toHaveTextContent(
      zh.valueUnknown,
    );
    expect(screen.getByText(`${zh.dataFreshness}: —`)).toBeInTheDocument();
  });
});

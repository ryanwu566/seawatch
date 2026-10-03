import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { DICTIONARIES } from "../../i18n/dictionaries";
import { VesselIntelligenceCard } from "./VesselIntelligenceCard";
import {
  DEMO_VESSEL_ID,
  getDemoScenario,
} from "./demoScenario";

const zh = DICTIONARIES["zh-Hant"];
// Task-mandated forbidden words plus the broader card guard list.
const PROHIBITED = ["dangerous", "suspicious", "threat", "illegal", "abnormal", "hostile"];

function renderDemoCard() {
  const { vessel, track, geographicContext } = getDemoScenario();
  return render(
    <I18nProvider>
      <VesselIntelligenceCard vessel={vessel} track={track} demoContext={geographicContext} />
    </I18nProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("demo scenario fixture", () => {
  it("is deterministic: identical output across calls", () => {
    expect(getDemoScenario()).toEqual(getDemoScenario());
  });

  it("carries a complete route-deviation-1 evidence object on the track", () => {
    const { track } = getDemoScenario();
    const ev = (track.properties as unknown as { route_deviation: Record<string, unknown> })
      .route_deviation as Record<string, unknown>;
    expect(ev.schemaVersion).toBe("route-deviation-1");
    expect((ev.deviation_distance_m as { value: number }).value).toBe(4100);
    expect((ev.baseline_source as { value: { method: string } }).value.method).toContain(
      "Historical median corridor",
    );
    expect(ev.confidence).toBe("HIGH");
  });

  it("carries a complete gis-context-1 example (coast + port + area)", () => {
    const { geographicContext } = getDemoScenario();
    expect(geographicContext.schema_version).toBe("gis-context-1");
    expect(geographicContext.distance_to_coast_km.value).not.toBeNull();
    expect(geographicContext.nearest_port.value).not.toBeNull();
    expect(geographicContext.within_named_areas.length).toBeGreaterThan(0);
  });

  it("uses an id that cannot collide with a live provider id", () => {
    expect(DEMO_VESSEL_ID.startsWith("demo-")).toBe(true);
  });

  it("fixtures are frozen (cannot be mutated at runtime)", () => {
    const { geographicContext } = getDemoScenario();
    expect(Object.isFrozen(geographicContext)).toBe(true);
  });
});

describe("Vessel Intelligence Card in DEMO mode", () => {
  it("renders a DEMO / illustrative banner and auto-opens", () => {
    renderDemoCard();
    const body = screen.getByTestId("vessel-intelligence");
    expect(within(body).getByTestId("demo-banner")).toHaveTextContent(zh.demoIllustrativeLabel);
  });

  it("NEVER calls the live /context/geographic endpoint in demo mode", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy as unknown as typeof fetch);
    renderDemoCard();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows a complete Route Deviation section from the fixture", () => {
    renderDemoCard();
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
    // Provenance stays explicit (derived), not relabeled by the demo banner.
    expect(section.querySelector('[data-provenance="derived"]')).not.toBeNull();
  });

  it("shows a complete Geographic Context section from the fixture", () => {
    renderDemoCard();
    const section = screen.getByTestId("geographic-context");
    expect(section.querySelector('[data-field="coast"]')?.textContent).toMatch(/8\.6 km/);
    expect(section.querySelector('[data-field="port"]')?.textContent).toContain("臺中港");
    expect(section.querySelector('[data-field="port-distance"]')?.textContent).toMatch(/12\.3 km/);
    expect(section.querySelector('[data-field="area"]')?.textContent).toContain("臺中港進場區");
    // Port name official, distances derived — provenance preserved.
    expect(section.querySelector('[data-provenance="official"]')).not.toBeNull();
    expect(section.querySelector('[data-provenance="derived"]')).not.toBeNull();
  });

  it("preserves Human review required in demo mode", () => {
    renderDemoCard();
    expect(screen.getByText(zh.intelligenceHumanReview)).toBeInTheDocument();
  });

  it("does not fabricate historical-baseline or satellite evidence", () => {
    renderDemoCard();
    const historical = screen.getByTestId("historical-baseline");
    expect(historical).toHaveTextContent(zh.historicalUnavailable);
    expect(screen.queryByTestId("satellite-evidence")).toBeNull();
  });

  it("never renders dangerous/suspicious/threat/illegal wording", () => {
    renderDemoCard();
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const term of PROHIBITED) {
      expect(text).not.toContain(term);
    }
  });
});

describe("live path non-regression", () => {
  it("without demoContext the card is collapsed and shows no demo banner", () => {
    const { vessel, track } = getDemoScenario();
    // Reuse the fixture shapes but render WITHOUT demoContext (live path).
    render(
      <I18nProvider>
        <VesselIntelligenceCard vessel={vessel} track={track} />
      </I18nProvider>,
    );
    // Collapsed by default in live mode (no auto-open), so no body/banner.
    expect(screen.queryByTestId("vessel-intelligence")).toBeNull();
    expect(screen.queryByTestId("demo-banner")).toBeNull();
  });
});

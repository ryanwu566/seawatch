import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n/I18nContext";
import { DICTIONARIES } from "../../i18n/dictionaries";
import { VesselIntelligenceCard } from "./VesselIntelligenceCard";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";

const zh = DICTIONARIES["zh-Hant"];
const PROHIBITED = ["dangerous", "suspicious", "threat", "abnormal", "hostile"];

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

function renderCard(vessel: LiveVesselFeature, track: LiveTrack | null) {
  return render(
    <I18nProvider>
      <VesselIntelligenceCard vessel={vessel} track={track} />
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

  it("always shows the route-baseline-unavailable note as unknown (no fabricated distance)", () => {
    renderCard(feature(), loiterTrack());
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    const baseline = document.querySelector('[data-reason="route_baseline_unavailable"]');
    expect(baseline).not.toBeNull();
    expect(baseline?.querySelector('[data-provenance="unknown"]')).not.toBeNull();
    // No fabricated "N km" deviation.
    expect(baseline?.textContent ?? "").not.toMatch(/\d+\s*km/);
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

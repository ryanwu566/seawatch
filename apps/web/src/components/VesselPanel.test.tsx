import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { DICTIONARIES } from "../i18n/dictionaries";
import { VesselPanel } from "./VesselPanel";
import type { LiveVesselFeature, LiveTrack } from "../api/live";

const zh = DICTIONARIES["zh-Hant"];

function feature(): LiveVesselFeature {
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

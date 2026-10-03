import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { DICTIONARIES } from "../i18n/dictionaries";
import { VesselPanel } from "./VesselPanel";
import { LayerControl } from "./LayerControl";
import { StatusCards } from "./StatusCards";
import { DEFAULT_LAYER_STATE } from "../lib/layerState";
import type { LiveVesselFeature, LiveTrack } from "../api/live";

const t = DICTIONARIES.en;

function wrap(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

const measured: LiveVesselFeature = {
  type: "Feature",
  id: "v1",
  geometry: { type: "Point", coordinates: [120, 22] },
  properties: {
    provider_id: "v1",
    sog_knots: 16.3,
    cog_deg: 322,
    heading_deg: 319,
    nav_status: 0,
    vessel_type: 83,
    name: "CLIPPER ERIS",
    destination: "TW MLI",
    observed_at: "2026-10-01T00:00:00Z",
    source: "aishub",
    synthesized: false,
    data_age_seconds: 12,
  },
};

const interpolated: LiveVesselFeature = {
  ...measured,
  id: "v2",
  properties: { ...measured.properties, synthesized: true, name: "SYNTH" },
};

describe("VesselPanel", () => {
  it("shows friendly fields in English by default", () => {
    wrap(
      <VesselPanel vessel={measured} track={null} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    expect(screen.getByText("CLIPPER ERIS")).toBeInTheDocument();
    expect(screen.getByText(t.speed)).toBeInTheDocument();
    expect(screen.getByText(t.positionStatus)).toBeInTheDocument();
    expect(screen.getAllByText(t.badgeLiveAis).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(t.positionMeasured)).toBeInTheDocument();
    // Friendly source, never raw provider id, in the main panel.
    expect(screen.queryByText("aishub")).not.toBeInTheDocument();
  });

  it("shows the English fallback when the vessel has no name", () => {
    const anon = { ...measured, properties: { ...measured.properties, name: null } };
    wrap(
      <VesselPanel vessel={anon} track={null} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    expect(screen.getByText(t.noVesselName)).toBeInTheDocument();
  });

  it("distinguishes a provider-interpolated vessel", () => {
    wrap(
      <VesselPanel
        vessel={interpolated}
        track={null}
        trackLoading={false}
        demo={false}
        onClose={() => {}}
      />,
    );
    expect(screen.getAllByText(t.badgeProviderInterpolated).length).toBeGreaterThanOrEqual(1);
  });

  it("shows a no-recent-update notice for a missing (dropped-out) vessel", () => {
    wrap(
      <VesselPanel
        vessel={measured}
        track={null}
        trackLoading={false}
        demo={false}
        missing
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(t.noRecentUpdate)).toBeInTheDocument();
  });

  it("shows Building Track History when fewer than 2 points", () => {
    const track: LiveTrack = {
      type: "Feature",
      id: "v1",
      geometry: { type: "LineString", coordinates: [[120, 22]] },
      properties: { provider_id: "v1", point_count: 1, observed_from: null, observed_to: null },
    };
    wrap(
      <VesselPanel vessel={measured} track={track} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    expect(screen.getByText(t.buildingTrackHistory)).toBeInTheDocument();
  });

  it("reveals Advanced Analysis only on expand, with benchmark disclaimer", () => {
    wrap(
      <VesselPanel vessel={measured} track={null} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    // Collapsed: benchmark source not shown yet.
    expect(screen.queryByText(/MarineCadastre/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(new RegExp(t.advancedAnalysis)));
    expect(screen.getByText(/MarineCadastre/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.benchmarkDisclaimer))).toBeInTheDocument();
  });

  it("fires onClose", () => {
    const onClose = vi.fn();
    wrap(
      <VesselPanel vessel={measured} track={null} trackLoading={false} demo={false} onClose={onClose} />,
    );
    fireEvent.click(screen.getByLabelText(t.closePanel));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("LayerControl", () => {
  it("toggles a maritime layer", () => {
    const onChange = vi.fn();
    wrap(<LayerControl layers={DEFAULT_LAYER_STATE} onChange={onChange} />);
    fireEvent.click(screen.getByText(t.layers));
    const portsLabel = screen.getByText(t.layerPorts);
    const checkbox = portsLabel.querySelector("input") as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ ports: !DEFAULT_LAYER_STATE.ports }),
    );
  });

  it("switches base map to orthophoto", () => {
    const onChange = vi.fn();
    wrap(<LayerControl layers={DEFAULT_LAYER_STATE} onChange={onChange} />);
    fireEvent.click(screen.getByText(t.layers));
    const ortho = screen.getByText(t.layerOrthophoto).querySelector("input") as HTMLInputElement;
    fireEvent.click(ortho);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ baseMap: "nlsc-photo" }));
  });
});

describe("StatusCards", () => {
  it("shows the live vessel count", () => {
    wrap(
      <StatusCards vesselCount={1606} needsReview={0} freshestAgeSeconds={7} source="open_waters" />,
    );
    expect(screen.getByText("1,606")).toBeInTheDocument();
    expect(screen.getByText(t.vesselsNow)).toBeInTheDocument();
    expect(screen.getByText("open_waters")).toBeInTheDocument();
  });
});

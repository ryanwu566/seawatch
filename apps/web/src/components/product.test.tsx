import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { VesselPanel } from "./VesselPanel";
import { LayerControl } from "./LayerControl";
import { StatusCards } from "./StatusCards";
import { DEFAULT_LAYER_STATE } from "../lib/layerState";
import type { LiveVesselFeature, LiveTrack } from "../api/live";

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
  it("shows friendly fields in Traditional Chinese by default", () => {
    wrap(
      <VesselPanel vessel={measured} track={null} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    expect(screen.getByText("CLIPPER ERIS")).toBeInTheDocument();
    expect(screen.getByText("目前航速")).toBeInTheDocument(); // Speed
    expect(screen.getByText("位置狀態")).toBeInTheDocument(); // Position status
    // "即時 AIS" appears both as the integrity badge and the position status.
    expect(screen.getAllByText("即時 AIS").length).toBeGreaterThanOrEqual(1);
    // "實際 AIS" is the measured position-status value.
    expect(screen.getByText("實際 AIS")).toBeInTheDocument();
    // Friendly source, never raw provider id, in the main panel.
    expect(screen.queryByText("aishub")).not.toBeInTheDocument();
  });

  it("shows '未公開船名' when the vessel has no name", () => {
    const anon = { ...measured, properties: { ...measured.properties, name: null } };
    wrap(
      <VesselPanel vessel={anon} track={null} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    expect(screen.getByText("未公開船名")).toBeInTheDocument();
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
    expect(screen.getAllByText("供應商插值").length).toBeGreaterThanOrEqual(1); // Provider Interpolated
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
    expect(screen.getByText("此船舶暫時沒有新資料")).toBeInTheDocument();
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
    expect(screen.getByText("航跡累積中")).toBeInTheDocument(); // Building Track History
  });

  it("reveals Advanced Analysis only on expand, with benchmark disclaimer", () => {
    wrap(
      <VesselPanel vessel={measured} track={null} trackLoading={false} demo={false} onClose={() => {}} />,
    );
    // Collapsed: benchmark source not shown yet.
    expect(screen.queryByText(/MarineCadastre/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/進階分析/)); // Advanced Analysis
    expect(screen.getByText(/MarineCadastre/)).toBeInTheDocument();
    expect(screen.getByText(/舊金山灣/)).toBeInTheDocument(); // benchmark disclaimer
  });

  it("fires onClose", () => {
    const onClose = vi.fn();
    wrap(
      <VesselPanel vessel={measured} track={null} trackLoading={false} demo={false} onClose={onClose} />,
    );
    fireEvent.click(screen.getByLabelText("關閉"));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("LayerControl", () => {
  it("toggles a maritime layer", () => {
    const onChange = vi.fn();
    wrap(<LayerControl layers={DEFAULT_LAYER_STATE} onChange={onChange} />);
    fireEvent.click(screen.getByText("圖層")); // open Layers
    const portsLabel = screen.getByText("商港"); // Commercial Ports
    const checkbox = portsLabel.querySelector("input") as HTMLInputElement;
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ ports: !DEFAULT_LAYER_STATE.ports }),
    );
  });

  it("switches base map to orthophoto", () => {
    const onChange = vi.fn();
    wrap(<LayerControl layers={DEFAULT_LAYER_STATE} onChange={onChange} />);
    fireEvent.click(screen.getByText("圖層"));
    const ortho = screen.getByText("正射影像").querySelector("input") as HTMLInputElement;
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
    expect(screen.getByText("目前船舶")).toBeInTheDocument(); // Vessels Now
    expect(screen.getByText("open_waters")).toBeInTheDocument();
  });
});

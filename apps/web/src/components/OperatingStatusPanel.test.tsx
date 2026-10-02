import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { OperatingMode, ResilienceStatus } from "../api/live";
import { I18nProvider } from "../i18n/I18nContext";
import { OperatingStatusPanel } from "./OperatingStatusPanel";

function status(mode: OperatingMode): ResilienceStatus {
  const edge = mode === "EDGE_LIVE" || mode === "EDGE_REPLAY";
  return {
    mode,
    coverage: mode === "CLOUD_LIVE" ? "taiwan_wide_network_feed" : edge ? "local_rf" : "none",
    simulated: mode === "EDGE_REPLAY",
    internet_available: mode === "CLOUD_LIVE",
    power_mode: "external",
    cloud: {
      source: "open_waters",
      fresh: mode === "CLOUD_LIVE",
      message_age_seconds: mode === "CLOUD_LIVE" ? 8 : 90,
      vessel_count: 10,
      connected: mode === "CLOUD_LIVE",
      input_kind: null,
    },
    edge: {
      source: mode === "EDGE_REPLAY" ? "edge_replay" : "edge_ais",
      fresh: edge,
      message_age_seconds: edge ? 4 : null,
      vessel_count: edge ? 3 : 0,
      connected: edge,
      input_kind: mode === "EDGE_REPLAY" ? "replay" : edge ? "udp" : "disabled",
    },
  };
}

function renderPanel(mode: OperatingMode) {
  return render(
    <I18nProvider>
      <OperatingStatusPanel status={status(mode)} />
    </I18nProvider>,
  );
}

describe("OperatingStatusPanel", () => {
  it.each([
    ["CLOUD_LIVE", "open_waters", "雲端網路 AIS 來源"],
    ["EDGE_LIVE", "edge_ais", "本地無線電 AIS 接收器"],
    ["EDGE_REPLAY", "edge_replay", "錄製 AIS 重播（模擬）"],
    ["NO_LIVE_SOURCE", "—", "無最新來源；快取或較舊資料仍保留標示"],
  ] as const)("renders the authoritative %s operating context", (mode, source, provenance) => {
    renderPanel(mode);
    const panel = screen.getByTestId("operating-status-panel");
    expect(panel).toHaveAttribute("data-mode", mode);
    expect(within(panel).getByText(source)).toBeInTheDocument();
    expect(within(panel).getByText(provenance)).toBeInTheDocument();
  });

  it("labels replay as recorded and never presents it as live RF", () => {
    renderPanel("EDGE_REPLAY");
    const text = screen.getByTestId("operating-status-panel").textContent ?? "";
    expect(text).toContain("錄製");
    expect(text).toContain("模擬");
    expect(text).toContain("非即時無線電 AIS");
  });
});

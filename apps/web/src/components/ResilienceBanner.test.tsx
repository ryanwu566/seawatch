import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ResilienceStatus } from "../api/live";
import { I18nProvider } from "../i18n/I18nContext";
import { ResilienceBanner } from "./ResilienceBanner";

const edge: ResilienceStatus = {
  mode: "EDGE_LIVE",
  coverage: "local_rf",
  simulated: false,
  internet_available: false,
  power_mode: "battery_ups",
  cloud: { source: "open_waters", fresh: false, message_age_seconds: 40, vessel_count: 1, connected: false, input_kind: null },
  edge: { source: "edge_ais", fresh: true, message_age_seconds: 1, vessel_count: 1, connected: true, input_kind: "udp" },
};

function wrapped(status: ResilienceStatus, previousMode: ResilienceStatus["mode"] | null) {
  return <I18nProvider><ResilienceBanner status={status} previousMode={previousMode} /></I18nProvider>;
}

describe("ResilienceBanner", () => {
  it("shows one non-blocking Cloud-to-Edge transition", () => {
    const { rerender } = render(wrapped(edge, "CLOUD_LIVE"));
    expect(screen.getByRole("status")).toHaveTextContent("雲端 AIS 無法使用，已切換至本地 AIS 接收器");
    rerender(wrapped(edge, "CLOUD_LIVE"));
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("shows restoration and prefixes simulated transitions", () => {
    const cloud = { ...edge, mode: "CLOUD_LIVE", coverage: "taiwan_wide_network_feed", internet_available: true } as ResilienceStatus;
    const { rerender } = render(wrapped(cloud, "EDGE_LIVE"));
    expect(screen.getByRole("status")).toHaveTextContent("雲端 AIS 已恢復");
    rerender(wrapped({ ...edge, mode: "EDGE_REPLAY", simulated: true }, "CLOUD_LIVE"));
    expect(screen.getByRole("status")).toHaveTextContent("模擬");
  });
});

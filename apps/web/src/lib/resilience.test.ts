import { describe, expect, it } from "vitest";
import type { ResilienceStatus, LiveVesselFeature, OperatingMode } from "../api/live";
import { DICTIONARIES } from "../i18n/dictionaries";
import { modePresentation, transitionEvent, vesselIntegrity } from "./resilience";

function status(mode: OperatingMode): ResilienceStatus {
  const edge = mode === "EDGE_LIVE" || mode === "EDGE_REPLAY";
  return {
    mode,
    coverage:
      mode === "CLOUD_LIVE"
        ? "taiwan_wide_network_feed"
        : edge
          ? "local_rf"
          : mode === "OFFLINE_DEMO"
            ? "demo"
            : "none",
    simulated: mode === "EDGE_REPLAY" || mode === "OFFLINE_DEMO",
    internet_available: mode === "CLOUD_LIVE",
    power_mode: "external",
    cloud: {
      source: "open_waters",
      fresh: mode === "CLOUD_LIVE",
      message_age_seconds: 0,
      vessel_count: 1,
      connected: mode === "CLOUD_LIVE",
      input_kind: null,
    },
    edge: {
      source: "edge_ais",
      fresh: edge,
      message_age_seconds: 0,
      vessel_count: edge ? 1 : 0,
      connected: edge,
      input_kind: mode === "EDGE_REPLAY" ? "replay" : edge ? "udp" : "disabled",
    },
  };
}

describe("modePresentation", () => {
  it.each([
    ["CLOUD_LIVE", "雲端即時 AIS", "CLOUD LIVE", "臺灣廣域網路 AIS", "Taiwan-wide network AIS"],
    ["EDGE_LIVE", "本地 AIS 接收", "EDGE LIVE", "本地無線電 AIS", "Local RF AIS"],
    ["EDGE_REPLAY", "本地接收重播", "EDGE REPLAY", "本地無線電 AIS", "Local RF AIS"],
    ["NO_LIVE_SOURCE", "即時資料無法使用", "LIVE DATA UNAVAILABLE", "無即時涵蓋", "No live coverage"],
    ["OFFLINE_DEMO", "離線示範資料", "OFFLINE DEMO", "示範資料", "Demo data"],
  ] as const)("presents %s honestly", (mode, zhLabel, enLabel, zhCoverage, enCoverage) => {
    expect(modePresentation(status(mode), DICTIONARIES["zh-Hant"]).label).toBe(zhLabel);
    expect(modePresentation(status(mode), DICTIONARIES.en).label).toBe(enLabel);
    expect(modePresentation(status(mode), DICTIONARIES["zh-Hant"]).coverageLabel).toBe(zhCoverage);
    expect(modePresentation(status(mode), DICTIONARIES.en).coverageLabel).toBe(enCoverage);
  });

  it("always explains local antenna limits and replay is not live RF", () => {
    expect(modePresentation(status("EDGE_LIVE"), DICTIONARIES.en).detail).toContain(
      "Shows only vessels receivable by the local antenna.",
    );
    expect(modePresentation(status("EDGE_REPLAY"), DICTIONARIES.en).detail.toLowerCase()).toContain(
      "recorded",
    );
    expect(modePresentation(status("EDGE_REPLAY"), DICTIONARIES["zh-Hant"]).detail).toContain(
      "非即時無線電",
    );
  });

  it("presents configured power without claiming runtime", () => {
    const battery = { ...status("EDGE_LIVE"), power_mode: "battery_ups" as const };
    expect(modePresentation(status("CLOUD_LIVE"), DICTIONARIES.en).powerLabel).toBe(
      "External Power",
    );
    expect(modePresentation(battery, DICTIONARIES.en).powerLabel).toBe("Battery / UPS");
    expect(modePresentation(battery, DICTIONARIES["zh-Hant"]).powerNote).toBe(
      "韌性運作需要筆電電池或 UPS。",
    );
  });

  it("contains no mojibake replacement characters", () => {
    for (const mode of ["CLOUD_LIVE", "EDGE_LIVE", "EDGE_REPLAY", "NO_LIVE_SOURCE", "OFFLINE_DEMO"] as const) {
      expect(JSON.stringify(modePresentation(status(mode), DICTIONARIES["zh-Hant"]))).not.toContain("�");
    }
  });
});

describe("transitionEvent", () => {
  it("reports failover and restoration once per real state change", () => {
    expect(transitionEvent("CLOUD_LIVE", status("EDGE_LIVE"))).toEqual({
      kind: "cloud_to_edge",
      simulated: false,
    });
    expect(transitionEvent("EDGE_LIVE", status("CLOUD_LIVE"))).toEqual({
      kind: "cloud_restored",
      simulated: false,
    });
    expect(transitionEvent("CLOUD_LIVE", status("CLOUD_LIVE"))).toBeNull();
  });
});

describe("vesselIntegrity", () => {
  it("uses backend cached/stale state instead of age heuristics", () => {
    const feature = {
      properties: { display_state: "stale", synthesized: false },
    } as LiveVesselFeature;
    expect(vesselIntegrity(feature)).toBe("stale");
  });
});

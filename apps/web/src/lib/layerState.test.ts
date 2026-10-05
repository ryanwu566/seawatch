import { describe, expect, it } from "vitest";
import { DEFAULT_LAYER_STATE } from "./layerState";

describe("DEFAULT_LAYER_STATE (live mode defaults)", () => {
  it("has live vessels ON by default so the map is never empty", () => {
    // Regression: thousands of real AIS vessels were hidden because this was off.
    expect(DEFAULT_LAYER_STATE.liveVessels).toBe(true);
  });

  it("keeps vessel trails OFF by default (shown only for the selected vessel)", () => {
    expect(DEFAULT_LAYER_STATE.vesselTracks).toBe(false);
  });

  it("keeps commercial ports ON by default for context", () => {
    expect(DEFAULT_LAYER_STATE.ports).toBe(true);
  });

  it("shows all three maritime reference boundaries by default", () => {
    expect(DEFAULT_LAYER_STATE.eezReference).toBe(true);
    expect(DEFAULT_LAYER_STATE.territorialSea12NmReference).toBe(true);
    expect(DEFAULT_LAYER_STATE.contiguousZone24NmReference).toBe(true);
  });

  it("keeps airspace and analysis overlays OFF by default", () => {
    expect(DEFAULT_LAYER_STATE.restrictedAirspace).toBe(false);
    expect(DEFAULT_LAYER_STATE.publicAirspace).toBe(false);
    expect(DEFAULT_LAYER_STATE.reviewCandidates).toBe(false);
    expect(DEFAULT_LAYER_STATE.navReference).toBe(false);
    expect(DEFAULT_LAYER_STATE.historicalTraffic).toBe(false);
  });
});

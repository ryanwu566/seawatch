import { describe, expect, it } from "vitest";
import { activeRegion, SF_BAY_REGION, TAIWAN_DEMO_REGION } from "./regions";
import demoAlerts from "../demo/demo_alerts.json";

describe("region configuration", () => {
  it("uses the SF Bay real-data benchmark when demo mode is off", () => {
    const region = activeRegion(false);
    expect(region).toEqual(SF_BAY_REGION);
    expect(region.region).toBe("SF Bay Benchmark");
    expect(region.source).toBe("NOAA MarineCadastre AIS");
    expect(region.dataKind).toBe("real");
  });

  it("uses the Taiwan synthetic demo when demo mode is on", () => {
    const region = activeRegion(true);
    expect(region).toEqual(TAIWAN_DEMO_REGION);
    expect(region.region).toBe("Taiwan Demo");
    expect(region.source).toBe("Synthetic Demo Scenario");
    expect(region.dataKind).toBe("synthetic");
  });

  it("centers Taiwan and SF Bay on different coordinates", () => {
    // Taiwan is east; SF Bay is far west (negative longitude).
    expect(TAIWAN_DEMO_REGION.center[0]).toBeGreaterThan(100);
    expect(SF_BAY_REGION.center[0]).toBeLessThan(-100);
  });
});

describe("Taiwan demo fixtures are clearly synthetic", () => {
  it("uses demo-taiwan track identifiers and the primary method", () => {
    const first = (demoAlerts as { alerts: { alert_id: string; ranking_method: string }[] }).alerts[0];
    expect(first.alert_id).toContain("demo-taiwan");
    expect(first.ranking_method).toBe("empirical_percentile");
  });
});

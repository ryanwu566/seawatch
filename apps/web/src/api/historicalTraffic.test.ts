import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetJson = vi.hoisted(() => vi.fn());

vi.mock("./client", () => ({ getJson: mockGetJson }));

describe("getHistoricalTraffic", () => {
  beforeEach(() => {
    vi.resetModules();
    mockGetJson.mockReset();
  });

  it("shares one traffic request for the browser session", async () => {
    const payload = {
      available: true,
      cells: [{
        cell_lat: 25,
        cell_lon: 121.5,
        observation_count: 1200,
        unique_vessel_count: 80,
        observed_days: 40,
        active_hour_buckets: 300,
        cell_active_hour_fraction: 0.25,
        avg_vessels_per_active_hour: 4,
      }],
    };
    mockGetJson.mockResolvedValue(payload);
    const { getHistoricalTraffic } = await import("./historicalTraffic");

    const [first, second, third] = await Promise.all([
      getHistoricalTraffic(),
      getHistoricalTraffic(),
      getHistoricalTraffic(),
    ]);

    expect(first).toBe(payload);
    expect(second).toBe(payload);
    expect(third).toBe(payload);
    expect(mockGetJson).toHaveBeenCalledTimes(1);
    expect(mockGetJson).toHaveBeenCalledWith("/detection/historical/traffic");
  });
});

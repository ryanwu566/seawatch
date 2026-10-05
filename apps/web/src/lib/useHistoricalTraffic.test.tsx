import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getHistoricalTraffic } from "../api/historicalTraffic";
import { useHistoricalTraffic } from "./useHistoricalTraffic";

vi.mock("../api/historicalTraffic", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/historicalTraffic")>();
  return { ...actual, getHistoricalTraffic: vi.fn() };
});

const cell = {
  cell_lat: 25,
  cell_lon: 121.5,
  observation_count: 1200,
  unique_vessel_count: 80,
  observed_days: 40,
  active_hour_buckets: 300,
  cell_active_hour_fraction: 0.25,
  avg_vessels_per_active_hour: 4,
};

describe("useHistoricalTraffic", () => {
  beforeEach(() => vi.mocked(getHistoricalTraffic).mockReset());

  it("publishes the complete converted payload when available", async () => {
    vi.mocked(getHistoricalTraffic).mockResolvedValue({ available: true, cells: [cell] });

    const { result } = renderHook(() => useHistoricalTraffic());

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("available"));
    expect(result.current.data?.features).toHaveLength(1);
  });

  it("contains unavailable payloads and request failures", async () => {
    vi.mocked(getHistoricalTraffic)
      .mockResolvedValueOnce({ available: false, cells: [] })
      .mockRejectedValueOnce(new Error("D:/private/runtime super-secret-token"));

    const unavailable = renderHook(() => useHistoricalTraffic());
    await waitFor(() => expect(unavailable.result.current.status).toBe("unavailable"));
    expect(unavailable.result.current.data).toBeNull();
    unavailable.unmount();

    const failed = renderHook(() => useHistoricalTraffic());
    await waitFor(() => expect(failed.result.current.status).toBe("unavailable"));
    expect(failed.result.current.data).toBeNull();
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { getJson } from "./client";
import {
  getHistoricalRuntimeSummary,
  type HistoricalRuntimeSummary,
} from "./historicalRuntime";


vi.mock("./client", () => ({
  getJson: vi.fn(),
}));


describe("getHistoricalRuntimeSummary", () => {
  beforeEach(() => {
    vi.mocked(getJson).mockReset();
  });

  it("requests the aggregate endpoint once and forwards the abort signal", async () => {
    const summary: HistoricalRuntimeSummary = {
      available: true,
      runtime: "SeaWatch_Runtime_Taiwan_2026_v2",
      data_model: "standardized_hourly_vessel_presence",
      date_range: { start: "2026-01-01", end: "2026-09-29" },
      row_count: 33_200_000,
      unique_vessel_count: 400_800,
      traffic_cell_count: 2457,
      dataset_hour_buckets: 6528,
      mmsi_join_status_counts: { unique_9digit_candidate: 66_043 },
    };
    const controller = new AbortController();
    vi.mocked(getJson).mockResolvedValue(summary);

    await expect(
      getHistoricalRuntimeSummary(controller.signal),
    ).resolves.toBe(summary);
    expect(getJson).toHaveBeenCalledTimes(1);
    expect(getJson).toHaveBeenCalledWith(
      "/detection/historical",
      controller.signal,
    );
  });
});

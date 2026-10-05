import { describe, expect, it } from "vitest";
import type { HistoricalTrafficCell } from "../api/historicalTraffic";
import {
  HISTORICAL_TRAFFIC_FILL_LAYER_ID,
  HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID,
  HISTORICAL_TRAFFIC_SOURCE_ID,
  buildHistoricalTrafficGeoJson,
  formatHistoricalTrafficPopup,
  historicalTrafficLayerSpecs,
} from "./historicalTraffic";

function cell(
  cellLat: number,
  cellLon: number,
  observationCount: number,
): HistoricalTrafficCell {
  return {
    cell_lat: cellLat,
    cell_lon: cellLon,
    observation_count: observationCount,
    unique_vessel_count: 80,
    observed_days: 40,
    active_hour_buckets: 300,
    cell_active_hour_fraction: 0.25,
    avg_vessels_per_active_hour: 4,
  };
}

describe("historical traffic visualization", () => {
  it("builds deterministic visualization footprints around coarse cell centers", () => {
    const result = buildHistoricalTrafficGeoJson([
      cell(25, 121.5, 1),
      cell(24.9, 121.4, 99),
    ]);

    expect(result.type).toBe("FeatureCollection");
    expect(result.features).toHaveLength(2);
    expect(result.features[0].geometry).toEqual({
      type: "Polygon",
      coordinates: [[
        [121.45, 24.95],
        [121.55, 24.95],
        [121.55, 25.05],
        [121.45, 25.05],
        [121.45, 24.95],
      ]],
    });
    expect(result.features[0].properties).toEqual(expect.objectContaining({
      cell_lat: 25,
      cell_lon: 121.5,
      observation_count: 1,
    }));
  });

  it("normalizes log1p observation counts once across the complete dataset", () => {
    const result = buildHistoricalTrafficGeoJson([
      cell(25, 121.5, 0),
      cell(24.9, 121.4, 99),
      cell(24.8, 121.3, 9_999),
    ]);

    expect(result.features.map((feature) => feature.properties?.density)).toEqual([
      0,
      0.5,
      1,
    ]);
    expect(result.features.map((feature) => feature.properties?.log_observation_count)).toEqual([
      0,
      Math.log1p(99),
      Math.log1p(9_999),
    ]);
  });

  it("accepts the complete 2,457-cell payload without sampling", () => {
    const cells = Array.from({ length: 2457 }, (_, index) =>
      cell(21.5 + (index % 51) / 10, 118 + Math.floor(index / 51) / 10, index + 1),
    );

    expect(buildHistoricalTrafficGeoJson(cells).features).toHaveLength(2457);
  });

  it("formats aggregate-only inspection content with the required caveat", () => {
    const html = formatHistoricalTrafficPopup(cell(25, 121.5, 1200));

    expect(html).toContain("Historical traffic");
    expect(html).toContain("Presence observations");
    expect(html).toContain("1,200");
    expect(html).toContain("Unique vessels");
    expect(html).toContain("Observed days");
    expect(html).toContain("Active hour buckets");
    expect(html).toContain("Avg vessels / active hour");
    expect(html).toContain("standardized hourly vessel presence");
    expect(html).toContain("~0.1° cell");
    expect(html).toContain("not raw/message-level AIS");
    expect(html).not.toMatch(/MMSI|IMO|vesselId|shipName|credential|local.path/i);
  });

  it("defines subtle shared layers over the shared source", () => {
    const layers = historicalTrafficLayerSpecs();

    expect(layers.map((layer) => layer.id)).toEqual([
      HISTORICAL_TRAFFIC_FILL_LAYER_ID,
      HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID,
    ]);
    expect(layers.every((layer) => layer.source === HISTORICAL_TRAFFIC_SOURCE_ID)).toBe(true);
    expect(layers[0].layout).toEqual({ visibility: "none" });
    expect(layers[1].minzoom).toBeLessThanOrEqual(6);
  });
});

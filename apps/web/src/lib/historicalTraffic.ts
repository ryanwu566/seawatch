import type {
  FillLayerSpecification,
  GeoJSONSource,
  LineLayerSpecification,
  Map as MapLibreMap,
} from "maplibre-gl";
import type { HistoricalTrafficCell } from "../api/historicalTraffic";

export const HISTORICAL_TRAFFIC_SOURCE_ID = "historical-traffic-cells";
export const HISTORICAL_TRAFFIC_FILL_LAYER_ID = "historical-traffic-density-fill";
export const HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID = "historical-traffic-cell-outline";
export const HISTORICAL_TRAFFIC_LAYER_IDS = [
  HISTORICAL_TRAFFIC_FILL_LAYER_ID,
  HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID,
] as const;

export type HistoricalTrafficProperties = HistoricalTrafficCell & {
  log_observation_count: number;
  density: number;
};

export type HistoricalTrafficFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.Polygon,
  HistoricalTrafficProperties
>;

const HALF_CELL_DEGREES = 0.05;

function coordinate(value: number): number {
  return Number(value.toFixed(6));
}

/**
 * Convert coarse centers to deterministic visualization footprints. These
 * squares show the approximate 0.1-degree presence grid and are not exact
 * positions or navigational boundaries.
 */
export function buildHistoricalTrafficGeoJson(
  cells: HistoricalTrafficCell[],
): HistoricalTrafficFeatureCollection {
  const logCounts = cells.map((cell) => Math.log1p(cell.observation_count));
  const maxLogCount = Math.max(0, ...logCounts);

  return {
    type: "FeatureCollection",
    features: cells.map((cell, index) => {
      const west = coordinate(cell.cell_lon - HALF_CELL_DEGREES);
      const east = coordinate(cell.cell_lon + HALF_CELL_DEGREES);
      const south = coordinate(cell.cell_lat - HALF_CELL_DEGREES);
      const north = coordinate(cell.cell_lat + HALF_CELL_DEGREES);
      const logObservationCount = logCounts[index];
      return {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
          ]],
        },
        properties: {
          ...cell,
          log_observation_count: logObservationCount,
          density: maxLogCount > 0 ? logObservationCount / maxLogCount : 0,
        },
      };
    }),
  };
}

export function historicalTrafficLayerSpecs(): [
  FillLayerSpecification,
  LineLayerSpecification,
] {
  return [
    {
      id: HISTORICAL_TRAFFIC_FILL_LAYER_ID,
      type: "fill",
      source: HISTORICAL_TRAFFIC_SOURCE_ID,
      layout: { visibility: "none" },
      paint: {
        "fill-color": [
          "interpolate",
          ["linear"],
          ["get", "density"],
          0,
          "#164e63",
          0.55,
          "#0e7490",
          1,
          "#67e8f9",
        ],
        "fill-opacity": [
          "interpolate",
          ["linear"],
          ["get", "density"],
          0,
          0.04,
          0.5,
          0.16,
          1,
          0.34,
        ],
      },
    },
    {
      id: HISTORICAL_TRAFFIC_OUTLINE_LAYER_ID,
      type: "line",
      source: HISTORICAL_TRAFFIC_SOURCE_ID,
      layout: { visibility: "none" },
      minzoom: 5.5,
      paint: {
        "line-color": "#67e8f9",
        "line-opacity": 0.1,
        "line-width": 0.45,
      },
    },
  ];
}

export function installHistoricalTrafficLayers(
  map: MapLibreMap,
  data: HistoricalTrafficFeatureCollection | null | undefined,
  beforeLayerId?: string,
): void {
  if (!data) return;
  const source = map.getSource(HISTORICAL_TRAFFIC_SOURCE_ID) as
    | GeoJSONSource
    | undefined;
  if (source) {
    source.setData(data);
  } else {
    map.addSource(HISTORICAL_TRAFFIC_SOURCE_ID, { type: "geojson", data });
  }
  const anchor = beforeLayerId && map.getLayer(beforeLayerId)
    ? beforeLayerId
    : undefined;
  for (const layer of historicalTrafficLayerSpecs()) {
    if (!map.getLayer(layer.id)) {
      map.addLayer(layer, anchor);
    } else if (anchor) {
      // Data can arrive after the rest of the map. Reassert the context stack
      // so async installation never promotes history above operational layers.
      map.moveLayer(layer.id, anchor);
    }
  }
}

export function setHistoricalTrafficVisibility(
  map: MapLibreMap,
  visible: boolean,
): void {
  for (const layerId of HISTORICAL_TRAFFIC_LAYER_IDS) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
    }
  }
}

const integerFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});
const decimalFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

function formatted(value: unknown, decimal = false): string {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? (decimal ? decimalFormat : integerFormat).format(value)
    : "—";
}

/** Format only the public aggregate allowlist; raw identifiers are never read. */
export function formatHistoricalTrafficPopup(
  cell: Partial<HistoricalTrafficCell>,
): string {
  return `<div class="historical-traffic-popup"><strong>Historical traffic</strong>`
    + `<dl><dt>Presence observations</dt><dd>${formatted(cell.observation_count)}</dd>`
    + `<dt>Unique vessels</dt><dd>${formatted(cell.unique_vessel_count)}</dd>`
    + `<dt>Observed days</dt><dd>${formatted(cell.observed_days)}</dd>`
    + `<dt>Active hour buckets</dt><dd>${formatted(cell.active_hour_buckets)}</dd>`
    + `<dt>Avg vessels / active hour</dt><dd>${formatted(cell.avg_vessels_per_active_hour, true)}</dd></dl>`
    + `<span>standardized hourly vessel presence<br/>~0.1° cell · not raw/message-level AIS</span></div>`;
}

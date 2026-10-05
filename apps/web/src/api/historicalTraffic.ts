import { getJson } from "./client";

export interface HistoricalTrafficCell {
  cell_lat: number;
  cell_lon: number;
  observation_count: number;
  unique_vessel_count: number;
  observed_days: number;
  active_hour_buckets: number;
  cell_active_hour_fraction: number;
  avg_vessels_per_active_hour: number;
}

export interface HistoricalTrafficResponse {
  available: boolean;
  cells: HistoricalTrafficCell[];
}

let sessionRequest: Promise<HistoricalTrafficResponse> | null = null;

/** Share one immutable traffic payload request across all map surfaces. */
export function getHistoricalTraffic(): Promise<HistoricalTrafficResponse> {
  sessionRequest ??= getJson<HistoricalTrafficResponse>(
    "/detection/historical/traffic",
  );
  return sessionRequest;
}

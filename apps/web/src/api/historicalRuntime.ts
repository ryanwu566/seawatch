import { getJson } from "./client";


export interface HistoricalDateRange {
  start?: string | null;
  end?: string | null;
  startUtc?: string | null;
  endUtc?: string | null;
}

export interface HistoricalRuntimeSummary {
  available: boolean;
  reason?: string | null;
  runtime?: string | null;
  data_model?: string | null;
  date_range?: HistoricalDateRange | [string, string] | string | null;
  row_count?: number | null;
  unique_vessel_count?: number | null;
  traffic_cell_count?: number | null;
  dataset_hour_buckets?: number | null;
  mmsi_join_status_counts?: Record<string, number | null> | null;
}

export function getHistoricalRuntimeSummary(
  signal?: AbortSignal,
): Promise<HistoricalRuntimeSummary> {
  return getJson<HistoricalRuntimeSummary>("/detection/historical", signal);
}

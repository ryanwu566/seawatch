// Typed client for the privacy-safe historical GFW baseline endpoint.

import { getJson } from "./client";

export type HistoricalProvenance = "official" | "observed" | "derived" | "unknown";
export type HistoricalConfidence = "HIGH" | "MEDIUM" | "LOW";

export interface HistoricalValue<T> {
  value: T | null;
  provenance: HistoricalProvenance;
  note?: string;
}

export interface HistoricalVesselBaseline {
  schema_version: "vessel-baseline-1";
  /** Opaque public vessel identifier; never MMSI, IMO, callsign, or GFW vesselId. */
  vessel_key: string;
  history_summary: {
    observed_day_count: HistoricalValue<number>;
    first_observed_utc: HistoricalValue<string>;
    last_observed_utc: HistoricalValue<string>;
    total_observations: HistoricalValue<number>;
    data_source: string;
  };
  typical_routes: Array<{
    route_key: string;
    occurrence_count: number;
    corridor_centerline: Array<[number, number]>;
    corridor_width_p90_m: HistoricalValue<number>;
    provenance: HistoricalProvenance;
  }>;
  usual_operating_areas: Array<{
    area_id: string;
    label_en: string;
    label_zh: string;
    dwell_fraction: HistoricalValue<number>;
  }>;
  historical_track_count: number;
  confidence: HistoricalValue<HistoricalConfidence>;
  sufficient: boolean;
  thresholds_used: {
    min_history_days: number;
    min_history_tracks: number;
    min_track_points: number;
  };
  data_source: string;
  disclaimer: string;
}

export type HistoricalBaselineState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "sufficient"; baseline: HistoricalVesselBaseline }
  | { status: "insufficient"; baseline: HistoricalVesselBaseline }
  | { status: "not-found" }
  | { status: "unavailable" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isHistoricalValue(value: unknown): value is HistoricalValue<unknown> {
  if (!isRecord(value)) return false;
  return ["official", "observed", "derived", "unknown"].includes(
    String(value.provenance),
  );
}

function isHistoricalVesselBaseline(value: unknown): value is HistoricalVesselBaseline {
  if (!isRecord(value) || !isRecord(value.history_summary)) return false;
  const summary = value.history_summary;
  return (
    value.schema_version === "vessel-baseline-1" &&
    typeof value.vessel_key === "string" &&
    isHistoricalValue(summary.observed_day_count) &&
    isHistoricalValue(summary.total_observations) &&
    Array.isArray(value.typical_routes) &&
    Array.isArray(value.usual_operating_areas) &&
    typeof value.historical_track_count === "number" &&
    isHistoricalValue(value.confidence) &&
    typeof value.sufficient === "boolean" &&
    typeof value.data_source === "string"
  );
}

export async function fetchHistoricalBaseline(
  publicId: string,
  signal?: AbortSignal,
): Promise<HistoricalVesselBaseline> {
  const payload = await getJson<unknown>(
    `/historical/vessels/${encodeURIComponent(publicId)}/baseline`,
    signal,
  );
  if (!isHistoricalVesselBaseline(payload)) {
    throw new Error("Invalid historical baseline response");
  }
  return payload;
}

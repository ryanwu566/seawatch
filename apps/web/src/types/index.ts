// Response types mirroring the SeaWatch FastAPI (Phase 4) schemas.
// These are behavioral-observation types only: no vessel identity is ever present.

export interface HealthResponse {
  status: string;
  service: string;
}

export interface TrackMetadata {
  track_id: string;
  date: string;
  /** Observed trajectory-window duration in seconds. */
  duration: number;
  observation_count: number;
}

export interface TrackListResponse {
  count: number;
  tracks: TrackMetadata[];
}

export interface ExplanationReason {
  reason_code: string;
  feature_group: string;
  feature_name: string;
  observed_value: number;
  unit: string;
  reference_percentile: number;
  /** "higher" | "lower" than the background. */
  direction: string;
  severity: number;
  message: string;
  /** "exact_component" | "supporting_evidence" (not model attribution). */
  attribution_kind: string;
}

export interface SupportingFeature {
  feature_name: string;
  feature_group: string;
  observed_value: number;
  unit: string;
  reference_percentile: number;
}

export interface DataQuality {
  observation_count: number;
  observed_duration_seconds: number;
  max_gap_seconds: number | null;
  sog_valid_fraction: number | null;
  cog_valid_fraction: number | null;
}

export interface AlertSummary {
  alert_id: string;
  track_id: string;
  date: string;
  /** Review priority score (ranking value, not a probability). */
  ranking_score: number;
  ranking_method: string;
  rank: number;
  shortlisted: boolean;
  explanation_reasons: ExplanationReason[];
}

export interface AlertListResponse {
  count: number;
  alerts: AlertSummary[];
}

export interface AlertDetail {
  alert_id: string;
  track_id: string;
  date: string;
  ranking_score: number;
  ranking_method: string;
  rank: number;
  shortlisted: boolean;
  review_status: string;
  explanation_reasons: ExplanationReason[];
  supporting_features: SupportingFeature[];
  data_quality: DataQuality;
}

export interface LineStringGeometry {
  type: "LineString";
  /** Ordered [longitude, latitude] pairs (EPSG:4326). */
  coordinates: [number, number][];
}

export interface TrackGeometryResponse {
  track_id: string;
  geometry: LineStringGeometry;
}

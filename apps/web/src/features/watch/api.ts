// Typed client for the SeaWatch detection API (/detection/*).

import { getBaseUrl } from "../../api/client";

export type Level = "HIGH" | "MEDIUM" | "LOW";
export type ReviewStatus = "new" | "under_review" | "confirmed" | "escalated" | "false_alarm";
export type DetectionSource = "scenario" | "live";

export interface VesselRef {
  mmsi: string;
  public_id?: string;
  name: string;
  type: string;
  flag: string;
}

export interface AlertSummary {
  id: string;
  title: string;
  risk: number;
  level: Level;
  confidence: number;
  mmsis: string[];
  public_ids?: string[];
  vessels: VesselRef[];
  t_start: number;
  t_end: number;
  raised_at: number;
  lat: number;
  lon: number;
  kinds: string[];
  status: ReviewStatus;
  n_events: number;
  n_notes: number;
  suppressed_by_feedback: string | null;
  top_reason: string;
  source?: DetectionSource;
  analysis_at?: string | null;
}

export interface DetectionEvent {
  id: string;
  kind: string;
  mmsis: string[];
  t_start: number;
  t_end: number;
  lat: number;
  lon: number;
  severity: number;
  confidence: number;
  summary: string;
  evidence: string[];
  benign_explanations: string[];
  uncertainty: string[];
  metrics: Record<string, number | string | boolean>;
  zone_id: string | null;
  path: [number, number][];
}

export interface Note {
  t: number;
  operator: string;
  text: string;
  system: boolean;
}

export interface BreakdownItem {
  kind: string;
  label: string;
  severity: number;
  confidence: number;
  points: number;
}

export interface MlOpinion {
  available: boolean;
  gb_score?: number;
  if_score?: number;
  agreement?: "agree" | "rules_only";
  note?: string;
  deviations?: { label: string; value: number; unit: string; typical: number; z: number }[];
}

export interface AlertDetail extends AlertSummary {
  path_reviews?: PathReviewDto[];
  ml: MlOpinion | null;
  reasons: string[];
  breakdown: BreakdownItem[];
  benign_explanations: string[];
  uncertainty: string[];
  recommended_action: string;
  notes: Note[];
  timeline: DetectionEvent[];
}

export interface Zone {
  id: string;
  name: string;
  kind: string;
  description: string;
  polygon: [number, number][];
}

export interface RegionInfo {
  id: string;
  label: string;
  data_kind: "simulated" | "real_plus_injected" | "real";
  available: boolean;
}

export interface Scenario {
  region: string;
  region_label: string;
  timezone: string;
  data_kind: "simulated" | "real_plus_injected" | "real";
  note: string;
  bounds: [[number, number], [number, number]];
  name: string;
  t0: number;
  t1: number;
  vessels: number;
  fixes: number;
  simulated: boolean;
  zones: Zone[];
  receivers: { id: string; lat: number; lon: number; range_nm: number }[];
  source?: DetectionSource;
  detection_status?: string;
  analysis_at?: string | null;
  scanned_at?: string | null;
  context_quality?: string;
  context_source?: string;
  ml_available?: boolean;
}

export interface TrackDto {
  mmsi: string;
  public_id?: string;
  name: string;
  type: string;
  flag: string;
  t: number[];
  lat: number[];
  lon: number[];
  sog: (number | null)[];
}

export interface ParamSpec {
  name: string;
  group: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  help: string;
}

export interface ConfigPayload {
  values: Record<string, number>;
  defaults: Record<string, number>;
  specs: ParamSpec[];
}

export interface Evaluation {
  alerts: number;
  true_alerts: number;
  false_alarms: number;
  false_alarms_on_benign_lookalikes: number;
  precision: number;
  recall: number;
  f1: number;
  alerts_per_100_vessel_days: number;
  false_alarms_per_100_vessel_days: number;
  real_background?: boolean;
  per_kind: Record<string, { truth: number; detected: number }>;
  missed: string[];
  false_alarm_ids: string[];
}

export interface TruthEvent {
  id: string;
  kind: string;
  mmsis: string[];
  t_start: number;
  t_end: number;
  note: string;
  benign: boolean;
}

export interface PathReviewDto {
  id: string;
  mmsi: string;
  name: string;
  t0: number;
  t1: number;
  lat: number;
  lon: number;
  category: string;
  category_description: string;
  flag: boolean;
  confidence: number;
  summary: string;
  reasons: string[];
  caveats: string[];
  features: Record<string, number>;
  context: Record<string, unknown>;
  reviewer: string;
  decision: "pending" | "accepted" | "rejected";
  second_reader?: { category: string; flag: boolean; agrees: boolean } | null;
}

export interface Assessment {
  region: string;
  data_kind: string;
  funnel: { stage: string; count: number }[];
  events_by_kind: Record<string, number>;
  discards: { detector: string; reason: string; count: number }[];
  factors: {
    single: Record<string, number>;
    combinations: { territory: boolean; velocity: boolean; declared: boolean; pattern: boolean; vessels: number; factors_met: number }[];
    classified: Record<string, number>;
  } | null;
  threat_classes: Record<string, number>;
  threat_top: { mmsi: string; name: string; rule: string; classification: string; severity: number; evidence: string[] }[];
  evaluation: Evaluation;
  ml_agreement: { agree: number; rules_only: number; pending: boolean };
}

export interface Rulebook {
  principle: string;
  resolution: string;
  detectors: { id: string; name: string; sees: string; why: string; thresholds: Record<string, number>; discards: string[]; benign: string[]; data: string }[];
  threat_model: {
    title: string;
    premise: string;
    legal: string;
    noise: string;
    factors: { code: string; name: string; rule: string; note: string }[];
    rules: { id: string; name: string; severity: string; needs: string; meaning: string }[];
  };
  fusion: Record<string, string | Record<string, number>>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getBaseUrl()}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

const post = <T,>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

function withSource(path: string, source: DetectionSource): string {
  if (source === "scenario") return path;
  return `${path}${path.includes("?") ? "&" : "?"}source=${source}`;
}

export const watchApi = {
  regions: () => request<{ active: string; regions: RegionInfo[] }>("/detection/regions"),
  selectRegion: (id: string) => post<{ active: string }>("/detection/region", { id }),
  scenario: (source: DetectionSource = "scenario") => request<Scenario>(withSource("/detection/scenario", source)),
  tracks: (source: DetectionSource = "scenario") =>
    request<{ tracks: TrackDto[] }>(withSource("/detection/tracks", source)).then((r) => r.tracks),
  alerts: (asOf?: number, source: DetectionSource = "scenario") => {
    const path = source === "live" || asOf === undefined ? "/detection/alerts" : `/detection/alerts?as_of=${asOf}`;
    return request<{ alerts: AlertSummary[] }>(withSource(path, source)).then((r) => r.alerts);
  },
  dismissed: (source: DetectionSource = "scenario") =>
    request<{ alerts: AlertSummary[] }>(withSource("/detection/alerts?include_dismissed=true", source)).then((r) =>
      r.alerts.filter((a) => a.status === "false_alarm"),
    ),
  alert: (id: string, source: DetectionSource = "scenario") =>
    request<AlertDetail>(withSource(`/detection/alerts/${encodeURIComponent(id)}`, source)),
  setStatus: (id: string, status: ReviewStatus, note?: string, source: DetectionSource = "scenario") =>
    post<AlertDetail>(withSource(`/detection/alerts/${encodeURIComponent(id)}/status`, source), { status, note }),
  addNote: (id: string, text: string, source: DetectionSource = "scenario") =>
    post<AlertDetail>(withSource(`/detection/alerts/${encodeURIComponent(id)}/notes`, source), { text }),
  config: () => request<ConfigPayload>("/detection/config"),
  setConfig: (values: Record<string, number>) => request<ConfigPayload>("/detection/config", { method: "PUT", body: JSON.stringify(values) }),
  resetConfig: () => post<ConfigPayload>("/detection/config/reset", {}),
  evaluation: () => request<Evaluation>("/detection/evaluation"),
  assessment: () => request<Assessment>("/detection/assessment"),
  rulebook: () => request<Rulebook>("/detection/rulebook"),
  pathReviews: () => request<{ reviewer: string; funnel: Record<string, number>; reviews: PathReviewDto[] }>("/detection/path-reviews"),
  decidePathReview: (id: string, decision: "accepted" | "rejected") =>
    request<{ id: string; decision: string }>(`/detection/path-reviews/${encodeURIComponent(id)}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
  layers: () => request<{ cables: GeoJSON.FeatureCollection; landing: GeoJSON.FeatureCollection; limits: GeoJSON.FeatureCollection; attribution: string }>("/detection/layers"),
  truth: () => request<{ truth: TruthEvent[] }>("/detection/truth").then((r) => r.truth),
  resetFeedback: () => post<{ status: string }>("/detection/feedback/reset", {}),
};

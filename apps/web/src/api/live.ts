// Live real-time AIS client for the SeaWatch backend.
//
// The frontend NEVER calls an upstream AIS provider directly. It only reads the
// SeaWatch backend's /live endpoints, which serve the shared in-memory store.

import { getBaseUrl } from "./client";

export type OperatingMode =
  | "CLOUD_LIVE"
  | "EDGE_LIVE"
  | "EDGE_REPLAY"
  | "NO_LIVE_SOURCE"
  | "OFFLINE_DEMO";
export type CoverageKind = "taiwan_wide_network_feed" | "local_rf" | "none" | "demo";
export type ObservationOrigin = "cloud" | "edge_rf" | "edge_replay" | "offline_demo";
export type DisplayState = "live" | "cached" | "stale";
export type EdgeInputKind = "disabled" | "udp" | "replay";
export type PowerMode = "external" | "battery_ups";

export interface SourceStatus {
  source: string;
  fresh: boolean;
  message_age_seconds: number | null;
  vessel_count: number;
  connected: boolean;
  input_kind: EdgeInputKind | null;
}

export interface ResilienceStatus {
  mode: OperatingMode;
  coverage: CoverageKind;
  simulated: boolean;
  internet_available: boolean;
  power_mode: PowerMode;
  cloud: SourceStatus;
  edge: SourceStatus;
}

/** A GeoJSON Feature for one live vessel with SeaWatch data-integrity props. */
export interface LiveVesselFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    provider_id: string;
    sog_knots: number | null;
    cog_deg: number | null;
    heading_deg: number | null;
    nav_status: number | null;
    vessel_type: number | null;
    /** Original Datalastic coarse type, when the provider supplied one. */
    provider_vessel_type?: string | null;
    /** Original Datalastic specific type, when the provider supplied one. */
    provider_vessel_type_specific?: string | null;
    name: string | null;
    destination: string | null;
    /** Upstream AIS report time (ISO-8601 UTC). */
    observed_at: string | null;
    source: string;
    /** True when the provider interpolated the position (not a measured fix). */
    synthesized: boolean;
    /** Server-computed age of the AIS fix at response time, in seconds. */
    data_age_seconds: number | null;
    freshness_state?: "fresh" | "stale" | "unknown";
    observation_origin?: ObservationOrigin;
    display_state?: DisplayState;
    active_source?: boolean;
    coverage?: CoverageKind;
    operating_mode?: OperatingMode;
  };
}

export interface LiveVesselCollection {
  type: "FeatureCollection";
  attribution: string;
  server_timestamp: string;
  data_timestamp: string | null;
  vessel_count: number;
  mode?: OperatingMode;
  coverage?: CoverageKind;
  simulated?: boolean;
  features: LiveVesselFeature[];
}

export interface LiveHealth {
  status: "online" | "degraded" | "offline";
  provider: string;
  connected: boolean;
  subscribed: boolean;
  last_message_at: string | null;
  message_age_seconds: number | null;
  vessel_count: number;
  reconnect_attempts: number;
  last_error: string | null;
  mode?: OperatingMode;
  coverage?: CoverageKind;
  simulated?: boolean;
  cloud?: SourceStatus;
  edge?: SourceStatus;
  provider_status?: DatalasticProviderStatus;
  /** Safe server state; never contains provider credentials. */
  live_ingest_enabled?: boolean;
  area_scan_autoauth_loopback_enabled?: boolean;
}

export interface DatalasticProviderStatus {
  provider: "datalastic";
  configured: boolean;
  reachable: boolean | null;
  key_status: "valid" | "invalid" | "unknown";
  addons: boolean | null;
  requests_remaining: number | null;
  rate_limit_remaining: number | null;
  last_success_at: string | null;
  last_error_category: string | null;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${getBaseUrl()}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function fetchLiveHealth(signal?: AbortSignal): Promise<LiveHealth> {
  return getJson<LiveHealth>("/live/health", signal);
}

export function fetchResilienceStatus(signal?: AbortSignal): Promise<ResilienceStatus> {
  return getJson<ResilienceStatus>("/resilience/status", signal);
}

export interface Bbox {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

export function fetchLiveVessels(bbox?: Bbox, signal?: AbortSignal): Promise<LiveVesselCollection> {
  let path = "/live/vessels";
  if (bbox) {
    const params = new URLSearchParams({
      min_lat: String(bbox.minLat),
      min_lon: String(bbox.minLon),
      max_lat: String(bbox.maxLat),
      max_lon: String(bbox.maxLon),
    });
    path += `?${params.toString()}`;
  }
  return getJson<LiveVesselCollection>(path, signal);
}

export interface LiveTrack {
  type: "Feature";
  id: string;
  geometry: { type: "LineString"; coordinates: [number, number][] };
  properties: {
    provider_id: string;
    point_count: number;
    observed_from: string | null;
    observed_to: string | null;
    source?: string;
  };
}

export function fetchLiveTrack(
  vesselId: string,
  signal?: AbortSignal,
  source?: "datalastic",
): Promise<LiveTrack> {
  const qualifier = source === "datalastic" ? "?source=datalastic" : "";
  return getJson<LiveTrack>(
    `/live/vessels/${encodeURIComponent(vesselId)}/track${qualifier}`,
    signal,
  );
}

export interface AreaScanResponse {
  source: "datalastic";
  scanned_at: string;
  cached: boolean;
  scan: {
    geometry_type: "Polygon";
    provider_queries: number;
  };
  total: number;
  vessels: LiveVesselFeature[];
}

export interface AreaScanPlan {
  area_square_km: number;
  provider_queries: number | null;
  max_provider_queries: number;
  can_scan: boolean;
  reason: "too_large" | null;
}

export class AreaScanApiError extends Error {
  readonly status: number;
  readonly retryAfterSeconds: number | null;

  constructor(status: number, message: string, retryAfterSeconds: number | null) {
    super(message);
    this.name = "AreaScanApiError";
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export interface AreaScanSessionResponse {
  authenticated: true;
  expires_in_seconds: number;
}

export async function authenticateAreaScan(
  operatorCredential: string,
  signal?: AbortSignal,
): Promise<AreaScanSessionResponse> {
  return postAreaScanSession({ operator_credential: operatorCredential }, signal);
}

export async function establishAreaScanSession(
  signal?: AbortSignal,
): Promise<AreaScanSessionResponse> {
  return postAreaScanSession({}, signal);
}

async function postAreaScanSession(
  body: Record<string, string>,
  signal?: AbortSignal,
): Promise<AreaScanSessionResponse> {
  const response = await fetch(`${getBaseUrl()}/live/area-scan/session`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await areaScanError(response);
  return (await response.json()) as AreaScanSessionResponse;
}

export async function scanLiveArea(
  geometry: GeoJSON.Polygon,
  signal?: AbortSignal,
): Promise<AreaScanResponse> {
  const response = await fetch(`${getBaseUrl()}/live/area-scan`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-SeaWatch-Area-Scan": "1",
    },
    body: JSON.stringify({ geometry }),
    signal,
  });
  if (!response.ok) throw await areaScanError(response);
  return (await response.json()) as AreaScanResponse;
}

export async function planLiveArea(
  geometry: GeoJSON.Polygon,
  signal?: AbortSignal,
): Promise<AreaScanPlan> {
  const response = await fetch(`${getBaseUrl()}/live/area-scan/plan`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-SeaWatch-Area-Scan": "1",
    },
    body: JSON.stringify({ geometry }),
    signal,
  });
  if (!response.ok) throw await areaScanError(response);
  return (await response.json()) as AreaScanPlan;
}

async function areaScanError(response: Response): Promise<AreaScanApiError> {
  let detail = "Area Scan unavailable";
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) detail = payload.detail;
  } catch {
    // Use the fixed local fallback; never surface raw provider response text.
  }
  const retryHeader = response.headers.get("Retry-After");
  const parsedRetry = retryHeader === null ? Number.NaN : Number.parseInt(retryHeader, 10);
  return new AreaScanApiError(
    response.status,
    detail,
    Number.isFinite(parsedRetry) && parsedRetry >= 0 && parsedRetry <= 5
      ? parsedRetry
      : null,
  );
}

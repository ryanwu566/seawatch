// Thin, dependency-free API client for the SeaWatch FastAPI backend.
// It consumes existing endpoints only and duplicates no backend logic.

import type {
  AlertDetail,
  AlertListResponse,
  HealthResponse,
  TrackGeometryResponse,
  TrackListResponse,
} from "../types";

const DEFAULT_BASE_URL = "http://localhost:8000";

/** Resolve the API base URL from Vite env, trimming any trailing slash. */
export function getBaseUrl(): string {
  const raw = import.meta.env?.VITE_API_BASE_URL ?? DEFAULT_BASE_URL;
  return raw.replace(/\/+$/, "");
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${getBaseUrl()}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        detail = body.detail;
      }
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health", signal);
}

export function getTracks(signal?: AbortSignal): Promise<TrackListResponse> {
  return getJson<TrackListResponse>("/tracks", signal);
}

export interface AlertQuery {
  method?: string;
  shortlistedOnly?: boolean;
  dedupeByTrack?: boolean;
  limit?: number;
  offset?: number;
}

export function getAlerts(
  options: AlertQuery = {},
  signal?: AbortSignal,
): Promise<AlertListResponse> {
  const params = new URLSearchParams();
  if (options.method) params.set("method", options.method);
  if (options.shortlistedOnly) params.set("shortlisted_only", "true");
  if (options.dedupeByTrack) params.set("dedupe_by_track", "true");
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  const query = params.toString();
  return getJson<AlertListResponse>(`/alerts${query ? `?${query}` : ""}`, signal);
}

export function getAlert(alertId: string, signal?: AbortSignal): Promise<AlertDetail> {
  return getJson<AlertDetail>(`/alerts/${encodeURIComponent(alertId)}`, signal);
}

export function getTrackGeometry(
  trackId: string,
  signal?: AbortSignal,
): Promise<TrackGeometryResponse> {
  return getJson<TrackGeometryResponse>(
    `/tracks/${encodeURIComponent(trackId)}/geometry`,
    signal,
  );
}

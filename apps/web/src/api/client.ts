// Thin, dependency-free API client for the SeaWatch FastAPI backend.
// It consumes existing endpoints only and duplicates no backend logic.

import type {
  AlertDetail,
  AlertListResponse,
  HealthResponse,
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

export function getAlerts(
  options: { shortlistedOnly?: boolean } = {},
  signal?: AbortSignal,
): Promise<AlertListResponse> {
  const query = options.shortlistedOnly ? "?shortlisted_only=true" : "";
  return getJson<AlertListResponse>(`/alerts${query}`, signal);
}

export function getAlert(alertId: string, signal?: AbortSignal): Promise<AlertDetail> {
  return getJson<AlertDetail>(`/alerts/${encodeURIComponent(alertId)}`, signal);
}

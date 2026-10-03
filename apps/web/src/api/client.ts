// Thin, dependency-free API client for the SeaWatch FastAPI backend.
// It consumes existing endpoints only and duplicates no backend logic.

import type {
  AlertDetail,
  AlertListResponse,
  HealthResponse,
  TrackGeometryResponse,
  TrackListResponse,
} from "../types";

/** Select Cloud override, dev convenience, or production same-origin API. */
export function resolveApiBaseUrl(
  explicitBaseUrl: string | undefined,
  isDevelopment: boolean,
  pageHostname?: string,
): string {
  const explicit = explicitBaseUrl?.trim();
  if (explicit) {
    const normalized = explicit.replace(/\/+$/, "");
    const loopbackHosts = new Set(["localhost", "127.0.0.1"]);
    if (pageHostname && loopbackHosts.has(pageHostname)) {
      try {
        const parsed = new URL(normalized);
        if (loopbackHosts.has(parsed.hostname)) {
          parsed.hostname = pageHostname;
          return parsed.toString().replace(/\/+$/, "");
        }
      } catch {
        // Preserve the existing behavior for non-URL build-time overrides.
      }
    }
    return normalized;
  }
  if (!isDevelopment) return "";
  const loopbackHostname = pageHostname === "127.0.0.1" ? "127.0.0.1" : "localhost";
  return `http://${loopbackHostname}:8000`;
}

/** Resolve the API base URL from the actual Vite build environment. */
export function getBaseUrl(): string {
  return resolveApiBaseUrl(
    import.meta.env?.VITE_API_BASE_URL,
    import.meta.env?.DEV ?? false,
    globalThis.location?.hostname,
  );
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

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
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

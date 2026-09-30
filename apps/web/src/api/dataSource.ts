// Data source abstraction: live FastAPI backend or local offline demo fixtures.
//
// When VITE_DEMO_MODE=true the dashboard reads bundled JSON fixtures so the demo
// never fails if the backend or data is unavailable. Demo data is clearly
// labeled in the UI and is never presented as live.

import {
  ApiError,
  getAlert,
  getAlerts,
  getHealth,
  getTrackGeometry,
} from "./client";
import type {
  AlertDetail,
  AlertListResponse,
  HealthResponse,
  TrackGeometryResponse,
} from "../types";
import demoAlerts from "../demo/demo_alerts.json";
import demoDetails from "../demo/demo_details.json";
import demoGeometry from "../demo/demo_geometry.json";

export function isDemoMode(): boolean {
  return String(import.meta.env?.VITE_DEMO_MODE ?? "false").toLowerCase() === "true";
}

// The Phase 3B primary ranking method (from config/phase3b_review_ranking_v1.json
// and the frozen calibration/evaluation outputs). Not a guess.
export const PRIMARY_RANKING_METHOD = "empirical_percentile";

// Default page size for the review-candidate list. The dashboard shows the
// Top-20 track-level priorities and never requests the full frame.
export const DEFAULT_ALERT_LIMIT = 20;

const demoAlertList = demoAlerts as unknown as AlertListResponse;
const demoDetailMap = demoDetails as unknown as Record<string, AlertDetail>;
const demoGeometryMap = demoGeometry as unknown as Record<string, TrackGeometryResponse>;

function delay<T>(value: T): Promise<T> {
  // Small delay so loading states are observable during the demo.
  return new Promise((resolve) => setTimeout(() => resolve(value), 120));
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  if (isDemoMode()) {
    return delay({ status: "ok", service: "seawatch-demo" });
  }
  return getHealth(signal);
}

/**
 * Fetch the default review-candidate list: the primary ranking method,
 * shortlisted candidates only, deduplicated to the highest-priority window per
 * track, capped to the Top-N. Supports pagination via ``offset``.
 */
export function fetchAlerts(
  options: { offset?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<AlertListResponse> {
  if (isDemoMode()) {
    return delay(demoAlertList);
  }
  return getAlerts(
    {
      method: PRIMARY_RANKING_METHOD,
      shortlistedOnly: true,
      dedupeByTrack: true,
      limit: options.limit ?? DEFAULT_ALERT_LIMIT,
      offset: options.offset ?? 0,
    },
    signal,
  );
}

export function fetchAlert(alertId: string, signal?: AbortSignal): Promise<AlertDetail> {
  if (isDemoMode()) {
    const detail = demoDetailMap[alertId];
    if (!detail) {
      return Promise.reject(new ApiError(404, `alert not found: ${alertId}`));
    }
    return delay(detail);
  }
  return getAlert(alertId, signal);
}

export function fetchTrackGeometry(
  trackId: string,
  signal?: AbortSignal,
): Promise<TrackGeometryResponse> {
  if (isDemoMode()) {
    const geometry = demoGeometryMap[trackId];
    if (!geometry) {
      return Promise.reject(new ApiError(404, `track geometry unavailable: ${trackId}`));
    }
    return delay(geometry);
  }
  return getTrackGeometry(trackId, signal);
}

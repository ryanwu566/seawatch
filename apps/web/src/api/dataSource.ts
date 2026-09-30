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

export function fetchAlerts(signal?: AbortSignal): Promise<AlertListResponse> {
  if (isDemoMode()) {
    return delay(demoAlertList);
  }
  return getAlerts({}, signal);
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

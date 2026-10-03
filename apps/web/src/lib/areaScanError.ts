import { AreaScanApiError } from "../api/live";

export type AreaScanErrorKind =
  | "session_expired"
  | "too_large"
  | "invalid_geometry"
  | "limit_reached"
  | "quota_unavailable"
  | "provider_unavailable";

export function classifyAreaScanError(error: unknown): AreaScanErrorKind {
  if (!(error instanceof AreaScanApiError)) return "provider_unavailable";
  if (error.status === 401 || error.status === 403) return "session_expired";
  if (error.status === 429) return "limit_reached";
  if (error.status === 422) {
    return /too large/i.test(error.message) ? "too_large" : "invalid_geometry";
  }
  if (/quota/i.test(error.message)) return "quota_unavailable";
  return "provider_unavailable";
}

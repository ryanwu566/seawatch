import type { DatalasticProviderStatus } from "../api/live";

export type AreaScanReadiness =
  | "available"
  | "status_unavailable"
  | "unconfigured"
  | "invalid_key"
  | "unreachable"
  | "quota_exhausted";

export function deriveAreaScanReadiness(
  provider: DatalasticProviderStatus | undefined,
): AreaScanReadiness {
  if (!provider) return "status_unavailable";
  if (!provider.configured) return "unconfigured";
  if (provider.key_status !== "valid") return "invalid_key";
  if (
    provider.requests_remaining === 0 ||
    provider.rate_limit_remaining === 0 ||
    provider.last_error_category === "quota_exhausted"
  ) {
    return "quota_exhausted";
  }
  if (provider.reachable !== true) return "unreachable";
  return "available";
}

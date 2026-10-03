import { describe, expect, it } from "vitest";
import type { DatalasticProviderStatus, LiveHealth } from "../api/live";
import { deriveAreaScanReadiness } from "./areaScanReadiness";

const healthyProvider: DatalasticProviderStatus = {
  provider: "datalastic",
  configured: true,
  reachable: true,
  key_status: "valid",
  addons: true,
  requests_remaining: 999_999_999,
  rate_limit_remaining: 599,
  last_success_at: "2026-10-03T10:00:00Z",
  last_error_category: null,
};

describe("Datalastic Area Scan readiness", () => {
  it("is available from provider health even when continuous ingest has no live source", () => {
    const health = {
      live_ingest_enabled: false,
      mode: "NO_LIVE_SOURCE",
      provider_status: healthyProvider,
    } satisfies Pick<LiveHealth, "live_ingest_enabled" | "mode" | "provider_status">;

    expect(deriveAreaScanReadiness(health.provider_status)).toBe("available");
  });

  it.each([
    ["unconfigured", { configured: false }, "unconfigured"],
    ["invalid key", { key_status: "invalid" }, "invalid_key"],
    ["unreachable provider", { reachable: false }, "unreachable"],
    ["unknown reachability", { reachable: null }, "unreachable"],
    ["exhausted request quota", { requests_remaining: 0 }, "quota_exhausted"],
    ["exhausted rate limit", { rate_limit_remaining: 0 }, "quota_exhausted"],
    ["reported quota exhaustion", { last_error_category: "quota_exhausted" }, "quota_exhausted"],
  ] as const)("reports %s without consulting live-ingest mode", (_label, patch, expected) => {
    expect(deriveAreaScanReadiness({ ...healthyProvider, ...patch })).toBe(expected);
  });

  it("treats missing provider health as not ready", () => {
    expect(deriveAreaScanReadiness(undefined)).toBe("status_unavailable");
  });
});

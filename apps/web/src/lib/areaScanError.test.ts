import { describe, expect, it } from "vitest";
import { AreaScanApiError } from "../api/live";
import { classifyAreaScanError } from "./areaScanError";

describe("Area Scan error classification", () => {
  it.each([
    [new AreaScanApiError(429, "Area Scan request budget exhausted", 2), "limit_reached"],
    [new AreaScanApiError(422, "Selected area is too large. Draw a smaller region.", null), "too_large"],
    [new AreaScanApiError(422, "Polygon geometry is invalid", null), "invalid_geometry"],
    [new AreaScanApiError(503, "Datalastic quota exhausted", null), "quota_unavailable"],
    [new AreaScanApiError(503, "upstream socket timeout internal-name", null), "provider_unavailable"],
    [new AreaScanApiError(403, "Area Scan authorization invalid or expired", null), "session_expired"],
  ] as const)("maps a sanitized API failure to %s", (error, expected) => {
    expect(classifyAreaScanError(error)).toBe(expected);
  });

  it("never returns a raw backend message", () => {
    const raw = "stack trace: internal limiter x-api-key secret";
    expect(classifyAreaScanError(new AreaScanApiError(500, raw, null))).not.toBe(raw);
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AreaScanApiError,
  authenticateAreaScan,
  establishAreaScanSession,
  fetchLiveTrack,
  planLiveArea,
  scanLiveArea,
  type AreaScanResponse,
} from "./live";

const geometry: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [
    [
      [120, 22],
      [121, 22],
      [121, 23],
      [120, 22],
    ],
  ],
};

const success: AreaScanResponse = {
  source: "datalastic",
  scanned_at: "2026-10-03T02:00:00Z",
  cached: false,
  scan: { geometry_type: "Polygon", provider_queries: 1 },
  total: 0,
  vessels: [],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("scanLiveArea", () => {
  it("plans geometry through a non-provider backend endpoint", async () => {
    const plan = {
      area_square_km: 113.42,
      provider_queries: 1,
      max_provider_queries: 16,
      can_scan: true,
      reason: null,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => plan,
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await expect(planLiveArea(geometry)).resolves.toEqual(plan);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/live/area-scan/plan",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ geometry }),
      }),
    );
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("api.datalastic.com");
  });

  it("requests a cookie-backed session without sending an operator credential", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({ authenticated: true, expires_in_seconds: 900 }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await establishAreaScanSession();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/live/area-scan/session",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({}),
      }),
    );
  });

  it("authenticates once through the backend without receiving a capability", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({ authenticated: true, expires_in_seconds: 900 }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    const result = await authenticateAreaScan("temporary-operator-credential");

    expect(result).toEqual({ authenticated: true, expires_in_seconds: 900 });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/live/area-scan/session",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ operator_credential: "temporary-operator-credential" }),
      }),
    );
    expect(JSON.stringify(result)).not.toContain("capability");
  });

  it("posts GeoJSON only to the shared SeaWatch backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => success,
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    const result = await scanLiveArea(geometry);

    expect(result).toEqual(success);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/live/area-scan",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-SeaWatch-Area-Scan": "1",
        },
        body: JSON.stringify({ geometry }),
      }),
    );
    const serializedCall = JSON.stringify(fetchMock.mock.calls[0]);
    expect(serializedCall).not.toContain("api.datalastic.com");
    expect(serializedCall).not.toContain("x-api-key");
  });

  it("returns only the backend's sanitized error and retry delay", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        headers: new Headers({ "Retry-After": "30" }),
        json: async () => ({ detail: "Datalastic Live AIS currently unavailable" }),
      } as Response),
    );

    await expect(scanLiveArea(geometry)).rejects.toEqual(
      expect.objectContaining({
        name: "AreaScanApiError",
        status: 503,
        retryAfterSeconds: null,
        message: "Datalastic Live AIS currently unavailable",
      }),
    );
    await expect(scanLiveArea(geometry)).rejects.toBeInstanceOf(
      AreaScanApiError,
    );
  });

  it("qualifies only Area Scan tracks with the Datalastic source", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        type: "Feature",
        id: "v_abcdefghijklmnopqrstuvwx",
        geometry: { type: "LineString", coordinates: [] },
        properties: { provider_id: "v_abcdefghijklmnopqrstuvwx", point_count: 0 },
      }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await fetchLiveTrack("v_abcdefghijklmnopqrstuvwx", undefined, "datalastic");
    await fetchLiveTrack("v_abcdefghijklmnopqrstuvwx");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8000/live/vessels/v_abcdefghijklmnopqrstuvwx/track?source=datalastic",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "http://localhost:8000/live/vessels/v_abcdefghijklmnopqrstuvwx/track",
    );
  });
});

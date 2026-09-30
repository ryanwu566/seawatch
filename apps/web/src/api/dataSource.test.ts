import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// These tests stub import.meta.env.VITE_DEMO_MODE and verify the data source
// serves bundled fixtures without touching the network.

describe("dataSource demo mode", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_DEMO_MODE", "true");
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("reports demo mode is enabled", async () => {
    const mod = await import("./dataSource");
    expect(mod.isDemoMode()).toBe(true);
  });

  it("fetchAlerts returns bundled demo candidates without network", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const mod = await import("./dataSource");

    const res = await mod.fetchAlerts();
    expect(res.count).toBeGreaterThan(0);
    expect(res.alerts[0].alert_id).toContain("demo__");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fetchTrackGeometry returns a demo LineString for a known track", async () => {
    const mod = await import("./dataSource");
    const res = await mod.fetchTrackGeometry("demo-track-1");
    expect(res.geometry.type).toBe("LineString");
    expect(res.geometry.coordinates.length).toBeGreaterThanOrEqual(2);
  });

  it("fetchTrackGeometry rejects unknown demo tracks with a 404", async () => {
    const mod = await import("./dataSource");
    await expect(mod.fetchTrackGeometry("missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
    });
  });

  it("fetchHealth reports the demo service", async () => {
    const mod = await import("./dataSource");
    const res = await mod.fetchHealth();
    expect(res.status).toBe("ok");
    expect(res.service).toBe("seawatch-demo");
  });
});

describe("dataSource live mode", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_DEMO_MODE", "false");
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("delegates to the network when demo mode is off", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ count: 0, alerts: [] }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    const mod = await import("./dataSource");
    expect(mod.isDemoMode()).toBe(false);
    await mod.fetchAlerts();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

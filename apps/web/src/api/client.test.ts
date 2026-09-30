import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getAlert, getAlerts, getHealth, getBaseUrl } from "./client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: `HTTP ${status}`,
    json: async () => body,
  } as Response);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getBaseUrl", () => {
  it("falls back to localhost and trims trailing slashes", () => {
    // VITE_API_BASE_URL is unset in the test env, so the default applies.
    expect(getBaseUrl()).toBe("http://localhost:8000");
  });
});

describe("api client", () => {
  it("getHealth returns the parsed payload", async () => {
    const fetchMock = mockFetch(200, { status: "ok", service: "seawatch-api" });
    vi.stubGlobal("fetch", fetchMock);

    const health = await getHealth();
    expect(health).toEqual({ status: "ok", service: "seawatch-api" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("getAlerts requests the alerts collection", async () => {
    const fetchMock = mockFetch(200, { count: 0, alerts: [] });
    vi.stubGlobal("fetch", fetchMock);

    const res = await getAlerts();
    expect(res.count).toBe(0);
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/alerts");
  });

  it("getAlerts adds the shortlisted filter", async () => {
    const fetchMock = mockFetch(200, { count: 0, alerts: [] });
    vi.stubGlobal("fetch", fetchMock);

    await getAlerts({ shortlistedOnly: true });
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8000/alerts?shortlisted_only=true",
    );
  });

  it("getAlert encodes the id in the path", async () => {
    const fetchMock = mockFetch(200, { alert_id: "a b", data_quality: {} });
    vi.stubGlobal("fetch", fetchMock);

    await getAlert("a b");
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/alerts/a%20b");
  });

  it("throws ApiError with the detail message on error responses", async () => {
    const fetchMock = mockFetch(404, { detail: "alert not found: x" });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAlert("x")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "alert not found: x",
    });
    await expect(getAlert("x")).rejects.toBeInstanceOf(ApiError);
  });
});

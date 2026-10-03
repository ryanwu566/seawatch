import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  getAlert,
  getAlerts,
  getHealth,
  getBaseUrl,
  resolveApiBaseUrl,
} from "./client";

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

  it("always honors and trims an explicit Cloud deployment URL", () => {
    expect(resolveApiBaseUrl("https://seawatch-bgsi.onrender.com///", false)).toBe(
      "https://seawatch-bgsi.onrender.com",
    );
    expect(resolveApiBaseUrl("https://seawatch-bgsi.onrender.com/", true)).toBe(
      "https://seawatch-bgsi.onrender.com",
    );
  });

  it("uses relative same-origin requests in production without an override", () => {
    const base = resolveApiBaseUrl(undefined, false);
    expect(base).toBe("");
    expect(`${base}/health`).toBe("/health");
    expect(`${base}/live/vessels`).toBe("/live/vessels");
    expect(`${base}/resilience/status`).toBe("/resilience/status");
    const pageOrigin = "http://127.0.0.1:8000";
    expect(new URL(`${base}/live/vessels`, pageOrigin).origin).toBe(pageOrigin);
    expect(new URL(`${base}/edge/health`, pageOrigin).hostname).toBe("127.0.0.1");
  });

  it("keeps localhost convenience development-only", () => {
    expect(resolveApiBaseUrl(undefined, true)).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("   ", true)).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("   ", false)).toBe("");
  });

  it("keeps the development API on the page's exact loopback hostname", () => {
    expect(
      resolveApiBaseUrl(undefined, true, "127.0.0.1"),
    ).toBe("http://127.0.0.1:8000");
    expect(
      resolveApiBaseUrl(undefined, true, "localhost"),
    ).toBe("http://localhost:8000");
  });

  it("normalizes a loopback override to the page hostname for strict cookies", () => {
    expect(
      resolveApiBaseUrl("http://localhost:8000", false, "127.0.0.1"),
    ).toBe("http://127.0.0.1:8000");
    expect(
      resolveApiBaseUrl("http://127.0.0.1:8000", false, "localhost"),
    ).toBe("http://localhost:8000");
    expect(
      resolveApiBaseUrl("https://seawatch-bgsi.onrender.com", false, "127.0.0.1"),
    ).toBe("https://seawatch-bgsi.onrender.com");
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

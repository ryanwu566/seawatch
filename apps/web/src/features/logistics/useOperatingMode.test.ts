import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

// Drive the SHARED getBaseUrl per environment without touching import.meta.env.
// This proves the operating-mode read uses the one shared API-base policy
// (public Cloud -> Render; Edge -> exact same-origin "") and hardcodes no host.
let baseUrl = "";
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    getBaseUrl: () => baseUrl,
  };
});

import { useOperatingMode } from "./useOperatingMode";

function okFetch(body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
  } as Response);
}

function status(mode: string) {
  return {
    mode,
    coverage: "taiwan_wide_network_feed",
    simulated: false,
    internet_available: true,
    power_mode: "external",
    cloud: {
      source: "cloud",
      fresh: true,
      message_age_seconds: 1,
      vessel_count: 10,
      connected: true,
      input_kind: null,
    },
    edge: {
      source: "edge",
      fresh: false,
      message_age_seconds: null,
      vessel_count: 0,
      connected: false,
      input_kind: "disabled",
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  baseUrl = "";
});

describe("useOperatingMode", () => {
  it("exposes the existing Phase 8 status without creating another state model", async () => {
    const response = status("EDGE_REPLAY");
    const fetchMock = okFetch(response);
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useOperatingMode());

    await waitFor(() => expect(result.current.status).toEqual(response));
    expect(result.current.mode).toBe("EDGE_REPLAY");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("gracefully falls back to null when the status endpoint fails (logistics still works)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({}),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useOperatingMode());

    // Give the effect a chance to run and reject internally.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    // Mode remains null; the hook never throws.
    expect(result.current.mode).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it("gracefully falls back to null when the fetch itself rejects (network/absent)", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useOperatingMode());

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(result.current.mode).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it("PUBLIC CLOUD: reads /resilience/status from the explicit Render origin (shared getBaseUrl)", async () => {
    baseUrl = "https://seawatch-bgsi.onrender.com";
    const fetchMock = okFetch(status("CLOUD_LIVE"));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useOperatingMode());

    await waitFor(() => expect(result.current.status?.mode).toBe("CLOUD_LIVE"));
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://seawatch-bgsi.onrender.com/resilience/status",
    );
  });

  it("EDGE: production base '' resolves to exact same-origin, never a hardcoded host", async () => {
    baseUrl = "";
    const fetchMock = okFetch(status("NO_LIVE_SOURCE"));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useOperatingMode());

    await waitFor(() => expect(result.current.status?.mode).toBe("NO_LIVE_SOURCE"));
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toBe("/resilience/status");
    const pageOrigin = "http://127.0.0.1:8000";
    expect(new URL(url, pageOrigin).origin).toBe(pageOrigin);
    expect(new URL(url, pageOrigin).hostname).toBe("127.0.0.1");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

// Mock the SHARED client so we can drive getBaseUrl per environment without
// touching import.meta.env. This proves logisticsApi uses the shared policy
// (public Cloud -> Render; Edge -> same-origin "") rather than inventing one.
let baseUrl = "";
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    getBaseUrl: () => baseUrl,
  };
});

import { fetchScenarios, fetchScenarioContext, runSimulation } from "./logisticsApi";

function okFetch(body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
  } as Response);
}

afterEach(() => {
  vi.restoreAllMocks();
  baseUrl = "";
});

describe("logisticsApi shared API-base policy", () => {
  it("PUBLIC CLOUD: targets the explicit Render origin for /logistics", async () => {
    baseUrl = "https://seawatch-bgsi.onrender.com";
    const fetchMock = okFetch({ count: 0, scenarios: [] });
    vi.stubGlobal("fetch", fetchMock);

    await fetchScenarios();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://seawatch-bgsi.onrender.com/logistics/scenarios",
    );
  });

  it("EDGE: production base '' resolves to exact same-origin, never Vercel", async () => {
    baseUrl = "";
    const fetchMock = okFetch({ count: 0, scenarios: [] });
    vi.stubGlobal("fetch", fetchMock);

    await fetchScenarios();
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toBe("/logistics/scenarios");
    const pageOrigin = "http://127.0.0.1:8000";
    expect(new URL(url, pageOrigin).origin).toBe(pageOrigin);
    expect(new URL(url, pageOrigin).hostname).toBe("127.0.0.1");
  });

  it("does not hardcode any deployment host (uses the shared base)", async () => {
    baseUrl = "https://example-base.test";
    const fetchMock = okFetch({ scenario: {}, affected_demands: [], candidate_ports: [], candidate_routes: [], provenance_summary: {} });
    vi.stubGlobal("fetch", fetchMock);

    await fetchScenarioContext("kaohsiung-disruption");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://example-base.test/logistics/scenarios/kaohsiung-disruption",
    );
  });

  it("runSimulation POSTs the scenario id and weights to the shared base", async () => {
    baseUrl = "https://seawatch-bgsi.onrender.com";
    const fetchMock = okFetch({ scenario_id: "kaohsiung-disruption" });
    vi.stubGlobal("fetch", fetchMock);

    await runSimulation("kaohsiung-disruption");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://seawatch-bgsi.onrender.com/logistics/simulate");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      scenario_id: "kaohsiung-disruption",
      weights: null,
    });
  });
});

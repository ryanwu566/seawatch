import { afterEach, describe, expect, it, vi } from "vitest";

import { watchApi } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Watch API live source routing", () => {
  it("adds source=live to reads and feedback without replay parameters", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return {
        ok: true,
        json: async () => ({ tracks: [], alerts: [], status: "new", notes: [] }),
      } as Response;
    }));

    await watchApi.scenario("live");
    await watchApi.tracks("live");
    await watchApi.alerts(undefined, "live");
    await watchApi.dismissed("live");
    await watchApi.alert("A-live", "live");
    await watchApi.setStatus("A-live", "under_review", undefined, "live");
    await watchApi.addNote("A-live", "checking", "live");

    expect(urls.map((url) => url.slice(url.indexOf("/detection")))).toEqual([
      "/detection/scenario?source=live",
      "/detection/tracks?source=live",
      "/detection/alerts?source=live",
      "/detection/alerts?include_dismissed=true&source=live",
      "/detection/alerts/A-live?source=live",
      "/detection/alerts/A-live/status?source=live",
      "/detection/alerts/A-live/notes?source=live",
    ]);
  });
});

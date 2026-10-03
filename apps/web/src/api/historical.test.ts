import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchHistoricalBaseline } from "./historical";


afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});


describe("fetchHistoricalBaseline", () => {
  it("rejects a malformed HTTP 200 payload so the card can degrade safely", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({ schema_version: "gis-context-1" }),
      })) as unknown as typeof fetch,
    );

    await expect(fetchHistoricalBaseline("v_opaque123")).rejects.toThrow(
      "Invalid historical baseline response",
    );
  });
});

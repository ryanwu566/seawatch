import { describe, expect, it } from "vitest";
import { deriveLiveStatus } from "./liveStatus";
import { normalizeOrientation } from "./orientation";
import type { LiveHealth } from "../api/live";

function health(overrides: Partial<LiveHealth> = {}): LiveHealth {
  return {
    status: "online",
    provider: "open_waters",
    connected: true,
    subscribed: true,
    last_message_at: "2026-10-01T00:00:00Z",
    message_age_seconds: 5,
    vessel_count: 100,
    reconnect_attempts: 0,
    last_error: null,
    ...overrides,
  };
}

describe("deriveLiveStatus", () => {
  it("shows LIVE when connected and messages are fresh", () => {
    expect(deriveLiveStatus({ demo: false, health: health(), vesselCount: 100 })).toBe("live");
  });

  it("NEVER shows offline-demo while real live vessels are displayed", () => {
    // Even if the env demo flag is on, real vessels on screen must not be
    // labeled as offline demo.
    expect(
      deriveLiveStatus({ demo: true, health: health(), vesselCount: 1606 }),
    ).not.toBe("offline_demo");
    expect(deriveLiveStatus({ demo: true, health: health(), vesselCount: 1606 })).toBe("live");
  });

  it("shows offline-demo only when demo flag is set AND no real data", () => {
    expect(
      deriveLiveStatus({ demo: true, health: null, vesselCount: 0 }),
    ).toBe("offline_demo");
  });

  it("shows reconnecting when not connected and retrying", () => {
    expect(
      deriveLiveStatus({
        demo: false,
        health: health({ connected: false, reconnect_attempts: 3, message_age_seconds: null }),
        vesselCount: 0,
      }),
    ).toBe("reconnecting");
  });

  it("shows stale when connected but last message is old", () => {
    expect(
      deriveLiveStatus({
        demo: false,
        health: health({ message_age_seconds: 600 }),
        vesselCount: 50,
      }),
    ).toBe("stale");
  });

  it("assumes live when vessels are visible but health has not loaded yet", () => {
    expect(deriveLiveStatus({ demo: false, health: null, vesselCount: 42 })).toBe("live");
  });

  it("treats backend mode as authoritative over legacy connection heuristics", () => {
    expect(
      deriveLiveStatus({
        demo: false,
        health: health({ mode: "NO_LIVE_SOURCE", connected: true, message_age_seconds: 1 }),
        vesselCount: 2,
      }),
    ).toBe("stale");
    expect(
      deriveLiveStatus({
        demo: false,
        health: health({ mode: "EDGE_REPLAY", connected: false }),
        vesselCount: 1,
      }),
    ).toBe("live");
  });
});

describe("normalizeOrientation", () => {
  it("prefers a valid heading", () => {
    expect(normalizeOrientation(319, 200)).toBe(319);
  });
  it("falls back to COG when heading is the 511 sentinel", () => {
    expect(normalizeOrientation(511, 90)).toBe(90);
  });
  it("falls back to COG when heading is null", () => {
    expect(normalizeOrientation(null, 123)).toBe(123);
  });
  it("returns null when COG is the 360 sentinel and heading is unavailable", () => {
    expect(normalizeOrientation(511, 360)).toBeNull();
  });
  it("returns null when both are unavailable", () => {
    expect(normalizeOrientation(null, null)).toBeNull();
  });
  it("rejects out-of-range angles", () => {
    expect(normalizeOrientation(999, 400)).toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import { projectPosition, reconcile, type MeasuredFix } from "./interpolation";
import { classifyVessel, formatAge } from "./integrity";
import type { LiveVesselFeature } from "../api/live";

describe("visual interpolation (dead reckoning)", () => {
  const base: MeasuredFix = {
    lon: 120.0,
    lat: 22.0,
    sogKnots: 10,
    courseDeg: 90, // due east
    observedAtMs: 1_000_000,
  };

  it("returns the measured position when no time has elapsed", () => {
    const r = projectPosition(base, base.observedAtMs);
    expect(r.lon).toBeCloseTo(120.0, 6);
    expect(r.lat).toBeCloseTo(22.0, 6);
    expect(r.interpolated).toBe(false);
  });

  it("advances eastward along course over time", () => {
    const r = projectPosition(base, base.observedAtMs + 60_000); // 60s later
    expect(r.interpolated).toBe(true);
    expect(r.lon).toBeGreaterThan(120.0); // moved east
    expect(r.lat).toBeCloseTo(22.0, 2); // latitude ~unchanged heading east
  });

  it("does not advance when speed is zero or unknown", () => {
    const stopped = { ...base, sogKnots: 0 };
    const r = projectPosition(stopped, base.observedAtMs + 60_000);
    expect(r.interpolated).toBe(false);
    expect(r.lon).toBeCloseTo(120.0, 6);

    const noSpeed = { ...base, sogKnots: null };
    const r2 = projectPosition(noSpeed, base.observedAtMs + 60_000);
    expect(r2.interpolated).toBe(false);
  });

  it("does not advance when course is unknown", () => {
    const noCourse = { ...base, courseDeg: null };
    const r = projectPosition(noCourse, base.observedAtMs + 60_000);
    expect(r.interpolated).toBe(false);
  });

  it("reconciles toward a target without teleporting", () => {
    const mid = reconcile({ lon: 120, lat: 22 }, { lon: 121, lat: 23 }, 0.5);
    expect(mid.lon).toBeCloseTo(120.5, 6);
    expect(mid.lat).toBeCloseTo(22.5, 6);
  });
});

function feature(overrides: Partial<LiveVesselFeature["properties"]>): LiveVesselFeature {
  return {
    type: "Feature",
    id: "x",
    geometry: { type: "Point", coordinates: [120, 22] },
    properties: {
      provider_id: "x",
      sog_knots: 10,
      cog_deg: 90,
      heading_deg: 90,
      nav_status: 0,
      vessel_type: 70,
      name: "TEST",
      destination: "KHH",
      observed_at: "2026-10-01T00:00:00Z",
      source: "aishub",
      synthesized: false,
      data_age_seconds: 10,
      ...overrides,
    },
  };
}

describe("data-integrity classification", () => {
  it("classifies a fresh measured fix as live", () => {
    expect(classifyVessel(feature({ data_age_seconds: 10 }))).toBe("live");
  });
  it("classifies an aging fix as cached", () => {
    expect(classifyVessel(feature({ data_age_seconds: 120 }))).toBe("cached");
  });
  it("classifies an old fix as stale", () => {
    expect(classifyVessel(feature({ data_age_seconds: 600 }))).toBe("stale");
  });
  it("classifies provider-synthesized positions distinctly", () => {
    expect(classifyVessel(feature({ synthesized: true }))).toBe("provider_interpolated");
  });
  it("classifies demo mode distinctly and never blurs it", () => {
    expect(classifyVessel(feature({}), { demo: true })).toBe("offline_demo");
  });
});

describe("formatAge", () => {
  const t = {
    secondsAgo: (n: number) => `${n} sec ago`,
    minutesAgo: (n: number) => `${n} min ago`,
    justNow: "just now",
  };
  it("formats recent as just now", () => {
    expect(formatAge(2, t)).toBe("just now");
  });
  it("formats seconds", () => {
    expect(formatAge(18, t)).toBe("18 sec ago");
  });
  it("formats minutes", () => {
    expect(formatAge(180, t)).toBe("3 min ago");
  });
});

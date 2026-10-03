import { describe, expect, it } from "vitest";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import {
  buildVesselIntelligence,
  hasEvidenceBackedReason,
  COURSE_CHANGE_MIN_DELTA_DEG,
} from "./buildIntelligence";

function feature(overrides: Partial<LiveVesselFeature["properties"]> = {}): LiveVesselFeature {
  return {
    type: "Feature",
    id: "v_opaque123",
    geometry: { type: "Point", coordinates: [120.3, 22.6] },
    properties: {
      provider_id: "v_opaque123",
      sog_knots: 12,
      cog_deg: 90,
      heading_deg: 90,
      nav_status: 0,
      vessel_type: 70,
      name: "EVER GIVEN",
      destination: "KHH",
      observed_at: "2026-10-02T06:00:00Z",
      source: "open_waters",
      synthesized: false,
      data_age_seconds: 12,
      ...overrides,
    },
  };
}

function track(
  coords: [number, number][],
  from: string | null,
  to: string | null,
): LiveTrack {
  return {
    type: "Feature",
    id: "v_opaque123",
    geometry: { type: "LineString", coordinates: coords },
    properties: {
      provider_id: "v_opaque123",
      point_count: coords.length,
      observed_from: from,
      observed_to: to,
    },
  };
}

describe("buildVesselIntelligence — provenance correctness", () => {
  it("marks present name/type as observed", () => {
    const intel = buildVesselIntelligence(feature(), null);
    expect(intel.profile.name).toEqual({ value: "EVER GIVEN", provenance: "observed" });
    expect(intel.profile.type.provenance).toBe("observed");
    expect(intel.profile.type.value).toBe("70");
  });

  it("marks missing name/type as unknown (null value), never invented", () => {
    const intel = buildVesselIntelligence(feature({ name: null, vessel_type: null }), null);
    expect(intel.profile.name).toEqual({ value: null, provenance: "unknown" });
    expect(intel.profile.type).toEqual({ value: null, provenance: "unknown" });
  });

  it("always marks flag and IMO unknown in MVP (not in the live schema)", () => {
    const intel = buildVesselIntelligence(feature(), null);
    expect(intel.profile.flag).toEqual({ value: null, provenance: "unknown" });
    expect(intel.profile.imo).toEqual({ value: null, provenance: "unknown" });
  });

  it("marks current observation fields as observed", () => {
    const intel = buildVesselIntelligence(feature(), null);
    expect(intel.observation.speedKnots).toEqual({ value: 12, provenance: "observed" });
    expect(intel.observation.headingDeg.provenance).toBe("observed");
    expect(intel.observation.lastUpdateSeconds).toEqual({ value: 12, provenance: "observed" });
  });

  it("marks missing speed as unknown", () => {
    const intel = buildVesselIntelligence(feature({ sog_knots: null }), null);
    expect(intel.observation.speedKnots).toEqual({ value: null, provenance: "unknown" });
  });

  it("derives in-session observation count and span from the track", () => {
    const tk = track(
      [
        [120.3, 22.6],
        [120.4, 22.7],
      ],
      "2026-10-02T05:30:00Z",
      "2026-10-02T06:00:00Z",
    );
    const intel = buildVesselIntelligence(feature(), tk);
    expect(intel.behavior.sessionObservationCount).toEqual({ value: 2, provenance: "derived" });
    expect(intel.behavior.sessionSpan.provenance).toBe("derived");
    expect(intel.behavior.sessionSpan.evidence).toBe("30 min");
  });

  it("marks behavior summary unknown when no track is available", () => {
    const intel = buildVesselIntelligence(feature(), null);
    expect(intel.behavior.sessionObservationCount).toEqual({ value: null, provenance: "unknown" });
    expect(intel.behavior.sessionSpan).toEqual({ value: null, provenance: "unknown" });
  });

  it("always marks typical route and usual area unknown in MVP (no historical baseline)", () => {
    const tk = track(
      [
        [120.3, 22.6],
        [120.4, 22.7],
      ],
      "2026-10-02T05:30:00Z",
      "2026-10-02T06:00:00Z",
    );
    const intel = buildVesselIntelligence(feature(), tk);
    expect(intel.behavior.typicalRoute).toEqual({ value: null, provenance: "unknown" });
    expect(intel.behavior.usualOperatingArea).toEqual({ value: null, provenance: "unknown" });
  });
});

describe("buildVesselIntelligence — evidence-backed review reasons", () => {
  it("emits a derived loitering reason only when low speed persists over a long session", () => {
    const tk = track(
      [
        [120.3, 22.6],
        [120.3001, 22.6001],
      ],
      "2026-10-02T05:30:00Z",
      "2026-10-02T06:00:00Z", // 30 min >= 15
    );
    const intel = buildVesselIntelligence(feature({ sog_knots: 0.5 }), tk);
    const loiter = intel.reasons.find((r) => r.kind === "session_loitering");
    expect(loiter?.provenance).toBe("derived");
    expect(loiter?.evidence).toContain("0.5 kn");
    expect(loiter?.evidence).toContain("30 min");
  });

  it("does not emit loitering for a short session even at low speed", () => {
    const tk = track(
      [
        [120.3, 22.6],
        [120.3001, 22.6001],
      ],
      "2026-10-02T05:58:00Z",
      "2026-10-02T06:00:00Z", // 2 min < 15
    );
    const intel = buildVesselIntelligence(feature({ sog_knots: 0.5 }), tk);
    expect(intel.reasons.find((r) => r.kind === "session_loitering")).toBeUndefined();
  });

  it("emits a derived course-change reason for a sharp turn along the trail", () => {
    // East then north ⇒ ~90° turn, above the 45° threshold.
    const tk = track(
      [
        [120.0, 22.0],
        [120.1, 22.0],
        [120.1, 22.1],
      ],
      "2026-10-02T05:00:00Z",
      "2026-10-02T06:00:00Z",
    );
    const intel = buildVesselIntelligence(feature(), tk);
    const course = intel.reasons.find((r) => r.kind === "session_course_change");
    expect(course?.provenance).toBe("derived");
    expect(course?.evidence).toMatch(/°/);
  });

  it("does not emit a course-change reason for a straight trail", () => {
    const tk = track(
      [
        [120.0, 22.0],
        [120.1, 22.0],
        [120.2, 22.0],
      ],
      "2026-10-02T05:00:00Z",
      "2026-10-02T06:00:00Z",
    );
    const intel = buildVesselIntelligence(feature(), tk);
    expect(intel.reasons.find((r) => r.kind === "session_course_change")).toBeUndefined();
  });

  it("always includes the route-baseline-unavailable note as unknown (never a fabricated distance)", () => {
    const intel = buildVesselIntelligence(feature(), null);
    const baseline = intel.reasons.find((r) => r.kind === "route_baseline_unavailable");
    expect(baseline).toBeDefined();
    expect(baseline?.provenance).toBe("unknown");
    expect(baseline?.evidence).toBeUndefined();
  });

  it("reports no evidence-backed reason when nothing crosses a threshold", () => {
    // Near-stationary tiny movement over a short session: average speed ≈ current,
    // straight line, span below the loitering minimum ⇒ no derived reason.
    const tk = track(
      [
        [120.0, 22.0],
        [120.00001, 22.0],
        [120.00002, 22.0],
      ],
      "2026-10-02T05:55:00Z",
      "2026-10-02T06:00:00Z",
    );
    const intel = buildVesselIntelligence(feature({ sog_knots: 0.3 }), tk);
    expect(hasEvidenceBackedReason(intel)).toBe(false);
  });

  it("exposes the course-change threshold as a documented constant", () => {
    expect(COURSE_CHANGE_MIN_DELTA_DEG).toBe(45);
  });
});

describe("buildVesselIntelligence — determinism & privacy", () => {
  it("is deterministic: identical inputs produce identical output", () => {
    const tk = track(
      [
        [120.0, 22.0],
        [120.1, 22.0],
        [120.1, 22.1],
      ],
      "2026-10-02T05:00:00Z",
      "2026-10-02T06:00:00Z",
    );
    const a = buildVesselIntelligence(feature({ sog_knots: 0.5 }), tk);
    const b = buildVesselIntelligence(feature({ sog_knots: 0.5 }), tk);
    expect(a).toEqual(b);
  });

  it("carries only the opaque public id and never an MMSI/IMO", () => {
    const intel = buildVesselIntelligence(feature(), null);
    expect(intel.profile.publicId).toBe("v_opaque123");
    const serialized = JSON.stringify(intel);
    expect(serialized).not.toMatch(/mmsi/i);
    expect(serialized).not.toMatch(/imo"\s*:\s*"\d/); // no numeric IMO value
  });
});

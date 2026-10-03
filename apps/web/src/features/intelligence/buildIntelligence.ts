// Pure, deterministic builder for the Vessel Intelligence Card.
//
// Assembles a VesselIntelligence from the existing public payloads only
// (LiveVesselFeature + optional LiveTrack). It invents nothing: fields the live
// data does not provide are `unknown`. Review reasons are emitted ONLY when
// in-session evidence crosses a documented threshold, and each carries the
// numbers it was computed from. No MMSI/IMO is ever read or produced.

import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import { normalizeOrientation } from "../../lib/orientation";
import type {
  BehaviorSummary,
  Provenanced,
  ReviewReason,
  VesselIntelligence,
  VesselObservation,
  VesselProfile,
} from "./intelligenceTypes";

// --- Documented review-reason thresholds (deterministic constants) --------- //
/** Loitering: current speed at or below this (knots) counts as low-speed dwell. */
export const LOITER_MAX_SOG_KNOTS = 1.0;
/** Loitering: only noted when the session trail spans at least this many minutes. */
export const LOITER_MIN_SESSION_MINUTES = 15;
/** Speed change: |current SOG − session-average speed| at or above this (knots). */
export const SPEED_CHANGE_MIN_DELTA_KNOTS = 5.0;
/** Course change: max turn along the session trail at or above this (degrees). */
export const COURSE_CHANGE_MIN_DELTA_DEG = 45;
/** Minimum trail points required before any geometry-derived reason is emitted. */
export const MIN_TRACK_POINTS = 3;

const EARTH_RADIUS_KM = 6371.0088;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function toDeg(rad: number): number {
  return (rad * 180) / Math.PI;
}

/** Great-circle distance in km between two [lon, lat] points. */
function haversineKm(a: [number, number], b: [number, number]): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(s)));
}

/** Initial bearing in degrees [0,360) from [lon,lat] a to b. */
function bearingDeg(a: [number, number], b: [number, number]): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

/** Smallest absolute angular difference in degrees [0,180]. */
function angleDeltaDeg(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

function unknown<T>(): Provenanced<T> {
  return { value: null, provenance: "unknown" };
}

function observed<T>(value: T | null): Provenanced<T> {
  return value === null ? unknown<T>() : { value, provenance: "observed" };
}

function sessionSpanMinutes(track: LiveTrack | null): number | null {
  if (!track) return null;
  const { observed_from, observed_to } = track.properties;
  if (!observed_from || !observed_to) return null;
  const from = Date.parse(observed_from);
  const to = Date.parse(observed_to);
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return null;
  return (to - from) / 60000;
}

function buildProfile(feature: LiveVesselFeature): VesselProfile {
  const p = feature.properties;
  return {
    publicId: p.provider_id,
    name: p.name ? { value: p.name, provenance: "observed" } : unknown<string>(),
    // Coarse AIS type bucket is self-reported ⇒ observed. The caller renders the
    // localized label; here we carry the raw numeric presence as observed/unknown.
    type:
      p.vessel_type === null || !Number.isFinite(p.vessel_type)
        ? unknown<string>()
        : { value: String(p.vessel_type), provenance: "observed" },
    // Not present in the live schema ⇒ unknown (never derived from MMSI MID).
    flag: unknown<string>(),
    imo: unknown<string>(),
  };
}

function buildObservation(feature: LiveVesselFeature): VesselObservation {
  const p = feature.properties;
  const course = normalizeOrientation(p.heading_deg, p.cog_deg);
  return {
    speedKnots: observed(p.sog_knots),
    headingDeg: observed(course),
    lastUpdateSeconds: observed(
      Number.isFinite(p.data_age_seconds) ? p.data_age_seconds : null,
    ),
  };
}

function buildBehavior(track: LiveTrack | null): BehaviorSummary {
  const count = track?.properties.point_count ?? null;
  const spanMin = sessionSpanMinutes(track);
  return {
    sessionObservationCount:
      count === null ? unknown<number>() : { value: count, provenance: "derived" },
    sessionSpan:
      track?.properties.observed_from && track?.properties.observed_to
        ? {
            value: `${track.properties.observed_from}–${track.properties.observed_to}`,
            provenance: "derived",
            evidence:
              spanMin !== null ? `${Math.round(spanMin)} min` : undefined,
          }
        : unknown<string>(),
    // No persistent multi-session history exists in the live path ⇒ unknown.
    typicalRoute: unknown<string>(),
    usualOperatingArea: unknown<string>(),
  };
}

/** Max turn (deg) along the session trail, or null when too few points. */
function maxTurnDeg(track: LiveTrack | null): number | null {
  const coords = track?.geometry.coordinates ?? [];
  if (coords.length < MIN_TRACK_POINTS) return null;
  let maxTurn = 0;
  for (let i = 2; i < coords.length; i++) {
    const b1 = bearingDeg(coords[i - 2] as [number, number], coords[i - 1] as [number, number]);
    const b2 = bearingDeg(coords[i - 1] as [number, number], coords[i] as [number, number]);
    maxTurn = Math.max(maxTurn, angleDeltaDeg(b1, b2));
  }
  return maxTurn;
}

/** Average session speed (knots) from trail distance/time, or null. */
function sessionAverageKnots(track: LiveTrack | null): number | null {
  const coords = track?.geometry.coordinates ?? [];
  const spanMin = sessionSpanMinutes(track);
  if (coords.length < MIN_TRACK_POINTS || spanMin === null || spanMin <= 0) return null;
  let km = 0;
  for (let i = 1; i < coords.length; i++) {
    km += haversineKm(coords[i - 1] as [number, number], coords[i] as [number, number]);
  }
  const hours = spanMin / 60;
  const knots = km / 1.852 / hours; // km → nautical miles → knots
  return Number.isFinite(knots) ? knots : null;
}

function buildReasons(feature: LiveVesselFeature, track: LiveTrack | null): ReviewReason[] {
  const reasons: ReviewReason[] = [];
  const p = feature.properties;
  const spanMin = sessionSpanMinutes(track);

  // Loitering: low current speed sustained over a long-enough session trail.
  if (
    p.sog_knots !== null &&
    p.sog_knots <= LOITER_MAX_SOG_KNOTS &&
    spanMin !== null &&
    spanMin >= LOITER_MIN_SESSION_MINUTES
  ) {
    reasons.push({
      kind: "session_loitering",
      provenance: "derived",
      labelKey: "intelligenceReasonLoitering",
      evidence: `SOG ${p.sog_knots.toFixed(1)} kn, ${Math.round(spanMin)} min`,
    });
  }

  // Speed change vs. the session-average speed derived from trail geometry.
  const avg = sessionAverageKnots(track);
  if (p.sog_knots !== null && avg !== null && Math.abs(p.sog_knots - avg) >= SPEED_CHANGE_MIN_DELTA_KNOTS) {
    reasons.push({
      kind: "session_speed_change",
      provenance: "derived",
      labelKey: "intelligenceReasonSpeedChange",
      evidence: `~${avg.toFixed(1)} → ${p.sog_knots.toFixed(1)} kn`,
    });
  }

  // Course change: largest turn along the session trail.
  const turn = maxTurnDeg(track);
  if (turn !== null && turn >= COURSE_CHANGE_MIN_DELTA_DEG) {
    reasons.push({
      kind: "session_course_change",
      provenance: "derived",
      labelKey: "intelligenceReasonCourseChange",
      evidence: `~${Math.round(turn)}°`,
    });
  }

  // Always present: route-deviation review needs a historical baseline that the
  // live path does not have. Stated explicitly, never a fabricated distance.
  reasons.push({
    kind: "route_baseline_unavailable",
    provenance: "unknown",
    labelKey: "intelligenceNoBaseline",
  });

  return reasons;
}

/**
 * Build the deterministic VesselIntelligence from existing public data.
 * Same inputs ⇒ identical output. Unavailable fields are `unknown`.
 */
export function buildVesselIntelligence(
  feature: LiveVesselFeature,
  track: LiveTrack | null,
): VesselIntelligence {
  return {
    profile: buildProfile(feature),
    observation: buildObservation(feature),
    behavior: buildBehavior(track),
    reasons: buildReasons(feature, track),
  };
}

/** True when at least one evidence-backed (derived) reason exists. */
export function hasEvidenceBackedReason(intel: VesselIntelligence): boolean {
  return intel.reasons.some((r) => r.provenance === "derived");
}

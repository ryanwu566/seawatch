// Read optional route-deviation evidence from the existing track payload.
//
// Route Deviation Evidence (`route-deviation-1`) is produced by the backend
// (apps/api/seawatch/trajectories/route_deviation.py). It requires a HISTORICAL
// multi-track baseline for an origin→destination route. The live rolling-track
// path does not always carry such a baseline, so this reader treats the evidence
// as OPTIONAL: when the backend attaches a `route-deviation-1` object to the
// track properties, it is surfaced verbatim; otherwise every field defaults to
// Unknown. Nothing is fabricated and no distance is ever guessed — matching the
// backend's own `unknown` discipline. No backend route is added or modified.

import type { LiveTrack } from "../../api/live";
import type { Confidence, RouteDeviationEvidence } from "./geographicTypes";

/**
 * A display-ready route-deviation model that ALWAYS exposes the five fields the
 * card renders, each with a provenance class. Unknown fields render "Unknown".
 */
export interface RouteDeviationView {
  /** Present only when the backend produced evidence; else a synthetic unknown. */
  statusKey: "route_deviation_detected" | "route_within_corridor" | "route_unknown";
  statusProvenance: "derived" | "unknown";
  /** Deviation distance in km (derived) or null (unknown). */
  deviationKm: number | null;
  deviationProvenance: "derived" | "unknown";
  /** Baseline description for the human (official/derived) or null. */
  baseline: string | null;
  baselineProvenance: "official" | "derived" | "unknown";
  /** HIGH / MEDIUM / LOW when known. */
  confidence: Confidence | null;
  /** Evidence source string ("Trajectory derived") or null. */
  source: string | null;
  /** The primary human-readable evidence statement, when present. */
  explanation: string | null;
  explanationProvenance: "derived" | "unknown";
}

/** The all-Unknown view used when no route-deviation evidence is available. */
export const UNKNOWN_ROUTE_DEVIATION: RouteDeviationView = {
  statusKey: "route_unknown",
  statusProvenance: "unknown",
  deviationKm: null,
  deviationProvenance: "unknown",
  baseline: null,
  baselineProvenance: "unknown",
  confidence: null,
  source: null,
  explanation: null,
  explanationProvenance: "unknown",
};

/**
 * The live track type does not declare route-deviation evidence, but the backend
 * `route-deviation-1` schema is stable. We read it defensively from an optional
 * property without widening the shared LiveTrack contract.
 */
type TrackWithOptionalDeviation = LiveTrack & {
  properties: LiveTrack["properties"] & {
    route_deviation?: RouteDeviationEvidence | null;
  };
};

function metresToKm(m: number): number {
  return Math.round((m / 1000) * 10) / 10; // one decimal, e.g. 4.1
}

/**
 * Build a display-ready RouteDeviationView from a track. Returns the all-Unknown
 * view when the track is null or carries no `route-deviation-1` evidence.
 */
export function readRouteDeviation(track: LiveTrack | null): RouteDeviationView {
  const evidence = (track as TrackWithOptionalDeviation | null)?.properties?.route_deviation;
  if (!evidence || evidence.schemaVersion !== "route-deviation-1") {
    return UNKNOWN_ROUTE_DEVIATION;
  }

  const dist = evidence.deviation_distance_m;
  const deviationKm =
    dist.value !== null && dist.provenance === "derived" ? metresToKm(dist.value) : null;
  const deviationProvenance = deviationKm !== null ? "derived" : "unknown";

  // Status derives from the primary (cross-track) evidence statement, with no
  // threat/suspicion wording — the backend statements are place/geometry facts.
  const primary = evidence.evidence?.[0] ?? null;
  let statusKey: RouteDeviationView["statusKey"] = "route_unknown";
  let statusProvenance: "derived" | "unknown" = "unknown";
  if (deviationKm !== null && primary) {
    const departs = /depart/i.test(primary.statement);
    statusKey = departs ? "route_deviation_detected" : "route_within_corridor";
    statusProvenance = "derived";
  }

  const baselineVal = evidence.baseline_source;
  const baseline =
    baselineVal.value && typeof baselineVal.value === "object"
      ? baselineVal.value.method ?? null
      : null;
  const baselineProvenance =
    baselineVal.provenance === "official"
      ? "official"
      : baselineVal.provenance === "derived" && baseline
        ? "derived"
        : "unknown";

  const source = primary ? normalizeSource(primary.source) : null;
  const confidence = deviationKm !== null ? evidence.confidence : null;

  return {
    statusKey,
    statusProvenance,
    deviationKm,
    deviationProvenance,
    baseline,
    baselineProvenance,
    confidence,
    source,
    explanation: primary ? primary.statement : null,
    explanationProvenance: primary && primary.provenance === "derived" ? "derived" : "unknown",
  };
}

/** Turn the backend source token into a human label ("Trajectory derived"). */
function normalizeSource(source: string): string {
  if (source === "trajectory_derived") return "Trajectory derived";
  return source;
}

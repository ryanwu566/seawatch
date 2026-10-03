// Deterministic, frontend-only DEMO fixture for the Vessel Intelligence Card.
//
// WHY THIS EXISTS
// Live AIS vessels frequently have no multi-track historical baseline, so the
// honest live card renders "Unknown" for route-deviation (by design — see
// routeDeviation.ts). That is correct behavior and MUST NOT change. For a
// hackathon walkthrough, judges still need to see ONE complete card. This module
// supplies a single, fixed, clearly-labeled ILLUSTRATIVE scenario.
//
// HARD GUARANTEES
// • Deterministic: no Date.now(), no Math.random(), no I/O — same output always.
// • Never mixed with live AIS: the demo vessel is produced here and is only ever
//   passed through a dedicated `demoContext` prop; it is never inserted into the
//   live `vessels` array, and the live `/context/geographic` fetch is skipped
//   when demo context is active.
// • Explicitly labeled DEMO / illustrative data at render time (banner).
// • Per-field provenance is preserved exactly as the live schemas define it
//   (derived / official / unknown). The DEMO banner labels the WHOLE scenario as
//   illustrative; it does not relabel individual provenance classes.
// • No threat / suspicious / dangerous / illegal wording. The route-deviation
//   statement is a neutral geometry fact, identical in tone to the backend's.
// • Evidence rules are untouched: this is static fixture data consumed by the
//   SAME render path, not a new scoring/classification rule.

import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import type { GeographicContext, RouteDeviationEvidence } from "./geographicTypes";

/** Stable id for the single demo vessel. Prefixed so it can never collide with a
 *  live `provider_id` and is trivially greppable in logs/tests. */
export const DEMO_VESSEL_ID = "demo-illustrative-keelung-taichung";

/** The demo vessel position (within Taiwan reference coverage, mid-strait). A
 *  plain GeoJSON point feature using the live schema shape — but it is only used
 *  via the demo path, never emitted by `/live/vessels`. */
export const DEMO_VESSEL: LiveVesselFeature = Object.freeze({
  type: "Feature",
  id: DEMO_VESSEL_ID,
  geometry: { type: "Point", coordinates: [120.05, 24.25] },
  properties: Object.freeze({
    provider_id: DEMO_VESSEL_ID,
    sog_knots: 11.4,
    cog_deg: 205,
    heading_deg: 205,
    nav_status: 0,
    vessel_type: 70, // cargo bucket (self-reported ⇒ observed in the card)
    name: "ILLUSTRATIVE DEMO VESSEL",
    destination: "TXG",
    observed_at: "2026-10-02T06:00:00Z",
    source: "illustrative_demo",
    synthesized: false,
    data_age_seconds: 20,
  }),
}) as LiveVesselFeature;

/** A complete route-deviation-1 evidence object: deviation + historical baseline
 *  + confidence, mirroring the backend schema exactly. Deterministic constants. */
const DEMO_ROUTE_DEVIATION: RouteDeviationEvidence = Object.freeze({
  schemaVersion: "route-deviation-1",
  track_ref: DEMO_VESSEL_ID,
  route_key: "keelung->taichung",
  deviation_distance_m: {
    value: 4100,
    provenance: "derived",
    note: "max cross-track to historical median corridor",
  },
  deviation_p95_m: { value: 3850, provenance: "derived" },
  deviation_ratio: { value: 2.4, provenance: "derived", note: "deviation / historical p90 corridor width" },
  baseline_source: {
    value: {
      method: "Historical median corridor",
      contributing_track_count: 12,
      observed_time_range: "2024-05-01–2024-05-31",
      corridor_width_p90_m: 1700,
    },
    provenance: "derived",
  },
  confidence: "HIGH",
  evidence: [
    {
      id: "cross_track",
      statement:
        "Current track departs from the historical median corridor for this origin–destination pair.",
      confidence: "HIGH",
      source: "trajectory_derived",
      provenance: "derived",
      evidence: "max 4.1 km (p95 3.9 km) vs ~1.7 km corridor",
    },
  ],
  disclaimer:
    "Decision support for human review only; a derived geometric deviation, not a judgement about the vessel.",
}) as RouteDeviationEvidence;

/** The demo rolling track, carrying the route-deviation-1 evidence in the same
 *  optional property the live reader already understands. Coordinates are fixed. */
export const DEMO_TRACK: LiveTrack = Object.freeze({
  type: "Feature",
  id: DEMO_VESSEL_ID,
  geometry: {
    type: "LineString",
    coordinates: [
      [120.18, 24.6],
      [120.12, 24.45],
      [120.05, 24.25],
    ],
  },
  properties: Object.freeze({
    provider_id: DEMO_VESSEL_ID,
    point_count: 184,
    observed_from: "2026-10-02T05:30:00Z",
    observed_to: "2026-10-02T06:00:00Z",
    // Optional field already read by readRouteDeviation(); live tracks omit it.
    route_deviation: DEMO_ROUTE_DEVIATION,
  }),
}) as unknown as LiveTrack;

/** A complete gis-context-1 example: distance to coast, nearest port + distance,
 *  and a named maritime area. Port name/area definition are official; distances
 *  and containment are derived — identical provenance discipline to live. */
export const DEMO_GEOGRAPHIC_CONTEXT: GeographicContext = Object.freeze({
  schema_version: "gis-context-1",
  coverage: { value: "in_coverage", provenance: "derived" },
  distance_to_coast_km: {
    value: 8.6,
    provenance: "derived",
    source: "Natural Earth (public domain)",
    note: "nearest-point WGS84 geodesic distance to coastline",
  },
  nearest_port: {
    value: { id: "taichung", name_zh: "臺中港", name_en: "Taichung", distance_km: 12.3 },
    provenance: "derived",
    source: "COMMERCIAL_PORTS (public civilian)",
    note: "port name/location official; distance derived (WGS84)",
  },
  within_named_areas: [
    {
      id: "taichung_approach",
      name_zh: "臺中港進場區",
      name_en: "Taichung approach",
      kind: "approach",
      definition_provenance: "official",
      containment_provenance: "derived",
    },
  ],
  named_areas_computed: true,
  disclaimer:
    "Geographic context for human review only: geometric facts about the area around the vessel position, not a judgement about the vessel, its behavior, its intent, or its permission to be there.",
}) as GeographicContext;

/** The complete bundle a demo entry point hands to the card. */
export interface DemoScenario {
  vessel: LiveVesselFeature;
  track: LiveTrack;
  geographicContext: GeographicContext;
}

/**
 * Return the single deterministic demo scenario. Pure: same output every call.
 * The returned objects are the frozen fixtures above (never cloned/mutated).
 */
export function getDemoScenario(): DemoScenario {
  return {
    vessel: DEMO_VESSEL,
    track: DEMO_TRACK,
    geographicContext: DEMO_GEOGRAPHIC_CONTEXT,
  };
}

// Frontend mirror of the backend maritime GIS context + route-deviation schemas.
//
// These types are a READ-ONLY projection of what the backend already produces:
//   • `gis-context-1`      → GET /context/geographic?lon=&lat= (apps/api/seawatch/context/gis)
//   • `route-deviation-1`  → apps/api/seawatch/trajectories/route_deviation.py
//
// The frontend performs NO geometry and invents NO data. Every value carries a
// provenance class; anything the backend reports as `null` / absent is rendered
// as Unknown. No backend route is added or modified here — the card simply reads
// the stable contracts and degrades to Unknown when a field is unavailable.

import type { Provenance } from "./intelligenceTypes";

/** A backend `Provenanced` value: `value === null` always implies `unknown`. */
export interface ProvenancedValue<T> {
  value: T | null;
  provenance: Provenance;
  /** Cited reference dataset (official) or how a derived value was computed. */
  source?: string | null;
  note?: string | null;
}

// --------------------------------------------------------------------------- //
// gis-context-1 (maritime GIS context)
// --------------------------------------------------------------------------- //

/** Descriptive label for a named maritime area — NOT a permission classification. */
export type NamedAreaKind = "anchorage" | "approach" | "fairway" | "port_area";

/** A named maritime area whose polygon contains the position (a place fact). */
export interface NamedAreaHit {
  id: string;
  name_zh: string;
  name_en: string;
  kind: NamedAreaKind;
  definition_provenance?: Provenance;
  containment_provenance?: Provenance;
  source?: string;
}

/** Nearest civilian port + distance (name/location official, distance derived). */
export interface NearestPort {
  id: string;
  name_zh: string;
  name_en: string;
  distance_km: number;
}

/** The `gis-context-1` result for one position (mirrors GeographicContext.to_dict). */
export interface GeographicContext {
  schema_version: string; // "gis-context-1"
  /** value "in_coverage" when geometry was computed; otherwise unknown. */
  coverage: ProvenancedValue<string>;
  distance_to_coast_km: ProvenancedValue<number>;
  nearest_port: ProvenancedValue<NearestPort>;
  /** Empty tuple = computed, inside no area (distinct from unknown). */
  within_named_areas: NamedAreaHit[];
  named_areas_computed: boolean;
  disclaimer: string;
}

// --------------------------------------------------------------------------- //
// route-deviation-1 (route deviation evidence)
// --------------------------------------------------------------------------- //

export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export interface RouteDeviationEvidenceItem {
  id: string;
  statement: string;
  confidence: Confidence;
  source: string; // "trajectory_derived"
  provenance: Provenance;
  evidence?: string;
}

/** Baseline-source payload shape carried inside `baseline_source.value`. */
export interface RouteBaselineSource {
  method: string;
  contributing_track_count?: number;
  observed_time_range?: string | null;
  corridor_width_p90_m?: number;
  min_required?: number;
}

/** The `route-deviation-1` result (mirrors RouteDeviationEvidence.to_dict). */
export interface RouteDeviationEvidence {
  schemaVersion: string; // "route-deviation-1"
  track_ref: string;
  route_key: string;
  deviation_distance_m: ProvenancedValue<number>;
  deviation_p95_m: ProvenancedValue<number>;
  deviation_ratio: ProvenancedValue<number>;
  baseline_source: ProvenancedValue<RouteBaselineSource>;
  confidence: Confidence;
  evidence: RouteDeviationEvidenceItem[];
  disclaimer: string;
}

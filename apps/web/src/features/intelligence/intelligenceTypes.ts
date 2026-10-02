// Vessel Intelligence Card — additive, frontend-only data model.
//
// Composed purely from the existing public live payloads (LiveVesselFeature +
// LiveTrack). No backend route, no database, no external API, no MMSI/IMO
// exposure. Every field carries a provenance class; anything the live data does
// not actually provide is `unknown` and never invented.

export type Provenance = "official" | "observed" | "derived" | "unknown";

/** A value plus how we know it. `value === null` always implies `unknown`. */
export interface Provenanced<T> {
  value: T | null;
  provenance: Provenance;
  /** For `derived` values: the numbers the value was computed from. */
  evidence?: string;
}

export interface VesselProfile {
  /** Opaque public id (never an MMSI/IMO). */
  publicId: string;
  name: Provenanced<string>; // observed | unknown
  type: Provenanced<string>; // observed | unknown (coarse AIS bucket)
  flag: Provenanced<string>; // unknown in MVP (not in the live schema)
  imo: Provenanced<string>; // unknown in MVP (not in the live schema)
}

export interface VesselObservation {
  speedKnots: Provenanced<number>; // observed
  headingDeg: Provenanced<number>; // observed
  lastUpdateSeconds: Provenanced<number>; // observed (age in seconds)
}

export interface BehaviorSummary {
  sessionObservationCount: Provenanced<number>; // derived (track point_count)
  sessionSpan: Provenanced<string>; // derived (observed_from–observed_to)
  typicalRoute: Provenanced<string>; // unknown in MVP (no historical baseline)
  usualOperatingArea: Provenanced<string>; // unknown in MVP
}

export type ReviewReasonKind =
  | "session_loitering"
  | "session_speed_change"
  | "session_course_change"
  | "route_baseline_unavailable";

export interface ReviewReason {
  kind: ReviewReasonKind;
  /** `derived` for evidence-backed reasons; `unknown` for baseline-unavailable. */
  provenance: Provenance;
  /** Translation key for the human-readable, non-threat summary. */
  labelKey:
    | "intelligenceReasonLoitering"
    | "intelligenceReasonSpeedChange"
    | "intelligenceReasonCourseChange"
    | "intelligenceNoBaseline";
  /** The numbers the reason was computed from (empty for baseline-unavailable). */
  evidence?: string;
}

export interface VesselIntelligence {
  profile: VesselProfile;
  observation: VesselObservation;
  behavior: BehaviorSummary;
  /** Evidence-backed reasons only; plus the always-present baseline-unavailable note. */
  reasons: ReviewReason[];
}

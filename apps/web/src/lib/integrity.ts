// Data-integrity classification for live vessels. Keeps the categories the
// product promises strictly separate and never blurs them.

import type { LiveVesselFeature } from "../api/live";
import { vesselIntegrity } from "./resilience";

export type IntegrityKind =
  | "live" // fresh measured AIS fix
  | "cached" // measured but aging
  | "stale" // old measured fix
  | "unknown" // Area Scan provider observation time unavailable
  | "provider_interpolated" // provider marked synthesized=true
  | "visual_interpolation" // frontend-animated position (not a measured fix)
  | "offline_demo"; // synthetic offline fixture

// Thresholds in seconds for measured-fix freshness.
export const LIVE_MAX_AGE_S = 60;
export const CACHED_MAX_AGE_S = 300;

/**
 * Classify a vessel's *measured* data integrity from its AIS fix age and the
 * provider's synthesized flag. This describes the source data, independent of
 * any frontend visual interpolation (which is labeled separately on the marker).
 */
export function classifyVessel(
  feature: LiveVesselFeature,
  options: { demo?: boolean } = {},
): IntegrityKind {
  if (options.demo) return "offline_demo";
  const authoritative = vesselIntegrity(feature);
  if (authoritative === "provider_interpolated") return authoritative;
  const areaFreshness = feature.properties.freshness_state;
  if (areaFreshness === "fresh") return "live";
  if (areaFreshness === "stale") return "stale";
  if (areaFreshness === "unknown") return "unknown";
  if (feature.properties.display_state) return authoritative;
  const age = feature.properties.data_age_seconds;
  if (age === null || !Number.isFinite(age)) return "stale";
  if (age <= LIVE_MAX_AGE_S) return "live";
  if (age <= CACHED_MAX_AGE_S) return "cached";
  return "stale";
}

/** Human-ago string using the active dictionary's formatters. */
export function formatAge(
  seconds: number | null,
  t: { secondsAgo: (n: number) => string; minutesAgo: (n: number) => string; justNow: string },
): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 5) return t.justNow;
  if (seconds < 90) return t.secondsAgo(Math.round(seconds));
  return t.minutesAgo(Math.round(seconds / 60));
}

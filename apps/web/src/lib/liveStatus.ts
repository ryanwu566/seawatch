// Derives the user-facing connection status for the live header pill.
//
// The critical rule: NEVER show "Offline Demo" while real live AIS vessels are
// being displayed. The status is computed from the actual /live/health snapshot
// (connection + message freshness), and only falls back to the demo label when
// the app is explicitly running in offline-demo mode (VITE_DEMO_MODE=true).

import type { LiveHealth } from "../api/live";

export type LiveStatusKind =
  | "live" // connected + fresh messages
  | "reconnecting" // not connected but actively retrying (or no fix yet)
  | "stale" // connected but last message is old
  | "offline_demo"; // explicit offline-demo mode (bundled fixtures)

// A live message older than this is considered stale.
export const LIVE_FRESH_MAX_AGE_S = 90;

export interface DeriveStatusInput {
  /** True only when VITE_DEMO_MODE=true (bundled offline fixtures). */
  demo: boolean;
  /** The latest /live/health snapshot, or null if it has not loaded yet. */
  health: LiveHealth | null;
  /** Number of real vessels currently rendered (safety net). */
  vesselCount: number;
}

/**
 * Compute the header status from real live-health state.
 *
 * Priority:
 *  1. Explicit offline-demo mode wins ONLY when no real vessels are shown. If
 *     demo mode is on but real live vessels are actually present, we never claim
 *     "offline demo" (that would be a lie about the data on screen).
 *  2. Otherwise derive from /live/health: connected + fresh -> live;
 *     connected + stale message -> stale; reconnecting/connecting -> reconnecting.
 *  3. With no health yet but vessels present, assume live (data is visible).
 */
export function deriveLiveStatus({ demo, health, vesselCount }: DeriveStatusInput): LiveStatusKind {
  if (health?.mode) {
    if (health.mode === "OFFLINE_DEMO") return "offline_demo";
    if (health.mode === "CLOUD_LIVE" || health.mode === "EDGE_LIVE" || health.mode === "EDGE_REPLAY") {
      return "live";
    }
    return vesselCount > 0 ? "stale" : "reconnecting";
  }
  // Offline demo is only honest when there is no real live data on screen.
  if (demo && vesselCount === 0 && (!health || !health.connected)) {
    return "offline_demo";
  }

  if (health) {
    const age = health.message_age_seconds;
    const fresh = age !== null && age <= LIVE_FRESH_MAX_AGE_S;

    if (health.connected && fresh) return "live";
    if (health.connected && age !== null && !fresh) return "stale";
    // Connected but no message yet, or actively reconnecting.
    if (health.reconnect_attempts > 0 || !health.connected) {
      // If we still have fresh-ish vessels on screen, prefer "stale" over
      // "reconnecting" so the user understands data is present but aging.
      if (vesselCount > 0 && age !== null && !fresh) return "stale";
      return "reconnecting";
    }
    if (health.connected) return "live";
  }

  // No health snapshot yet. If real vessels are visible, we are effectively live.
  if (vesselCount > 0) return "live";

  // Nothing to show and not in demo mode: treat as reconnecting (API warming up).
  return demo ? "offline_demo" : "reconnecting";
}

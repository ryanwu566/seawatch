// Slice J — Phase 8 → Phase 9 read-only integration seam.
//
// A tiny, absence-tolerant hook that reads the STABLE Phase 8 resilience status
// contract (`GET /resilience/status`) through the SHARED frontend API client
// (`fetchResilienceStatus`, which itself uses `getBaseUrl`). It:
//   - consumes ONLY the stable status contract — no import of any Phase 8
//     internal store, runtime, or `live/`/`edge/`/`resilience/` internal;
//   - treats the operating mode as an opaque string for display context;
//   - degrades SILENTLY to `null` if the endpoint is missing, errors, or the
//     network is unavailable, so logistics works fully without Phase 8.
//
// It defines no independent API-base policy and hardcodes no deployment host:
// the single shared `getBaseUrl` contract (public Cloud → Render; Edge → exact
// same-origin) is inherited via `fetchResilienceStatus`.

import { useEffect, useState } from "react";
import {
  fetchResilienceStatus,
  type OperatingMode,
  type ResilienceStatus,
} from "../../api/live";

export interface OperatingModeState {
  /** The unchanged Phase 8 resilience status response, when available. */
  status: ResilienceStatus | null;
  /** The Phase 8 operating mode, or null when the status is unavailable. */
  mode: OperatingMode | null;
}

/**
 * Read-only Phase 8 operating-mode context for the logistics view.
 *
 * The mode is fetched once on mount; any failure is swallowed and leaves the
 * mode as `null` (no banner is shown). No scenario is auto-triggered from this
 * value — it is display context only.
 */
export function useOperatingMode(): OperatingModeState {
  const [status, setStatus] = useState<ResilienceStatus | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    fetchResilienceStatus(controller.signal)
      .then((status) => {
        if (active && status && typeof status.mode === "string") {
          setStatus(status);
        }
      })
      .catch(() => {
        // Tolerant of absence: the endpoint may not exist (older Phase 8),
        // may error, or the network may be down. Logistics still works.
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return { status, mode: status?.mode ?? null };
}

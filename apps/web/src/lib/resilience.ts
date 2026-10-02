import type {
  DisplayState,
  LiveVesselFeature,
  OperatingMode,
  ResilienceStatus,
} from "../api/live";
import type { Dict } from "../i18n/dictionaries";

export interface ModePresentation {
  mode: OperatingMode;
  label: string;
  coverageLabel: string;
  detail: string;
  powerLabel: string;
  powerNote: string;
}

export interface OperatingStatusPresentation extends ModePresentation {
  source: string;
  freshness: string;
  coverageDetail: string;
  provenance: string;
}

export function modePresentation(status: ResilienceStatus, t: Dict): ModePresentation {
  const labels: Record<OperatingMode, string> = {
    CLOUD_LIVE: t.modeCloud,
    EDGE_LIVE: t.modeEdge,
    EDGE_REPLAY: t.modeReplay,
    NO_LIVE_SOURCE: t.modeNoSource,
    OFFLINE_DEMO: t.modeDemo,
  };
  const coverage = {
    taiwan_wide_network_feed: t.coverageCloud,
    local_rf: t.coverageEdge,
    none: t.coverageNone,
    demo: t.coverageDemo,
  };
  const edgeDetail =
    status.mode === "EDGE_LIVE" || status.mode === "EDGE_REPLAY"
      ? t.edgeCoverageNote
      : "";
  const replayDetail = status.mode === "EDGE_REPLAY" ? ` ${t.replayRecordedNote}` : "";
  return {
    mode: status.mode,
    label: labels[status.mode],
    coverageLabel: coverage[status.coverage],
    detail: `${edgeDetail}${replayDetail}`.trim(),
    powerLabel: status.power_mode === "battery_ups" ? t.batteryUps : t.externalPower,
    powerNote: t.powerRequirement,
  };
}

export function operatingStatusPresentation(
  status: ResilienceStatus,
  t: Dict,
): OperatingStatusPresentation {
  const base = modePresentation(status, t);
  const activeSource =
    status.mode === "CLOUD_LIVE"
      ? status.cloud
      : status.mode === "EDGE_LIVE" || status.mode === "EDGE_REPLAY"
        ? status.edge
        : null;
  const coverageDetail: Record<OperatingMode, string> = {
    CLOUD_LIVE: t.cloudCoverageNote,
    EDGE_LIVE: t.edgeCoverageNote,
    EDGE_REPLAY: `${t.edgeCoverageNote} ${t.replayRecordedNote}`,
    NO_LIVE_SOURCE: t.noCoverageNote,
    OFFLINE_DEMO: t.demoCoverageNote,
  };
  const provenance: Record<OperatingMode, string> = {
    CLOUD_LIVE: t.provenanceCloud,
    EDGE_LIVE: t.provenanceEdge,
    EDGE_REPLAY: t.provenanceReplay,
    NO_LIVE_SOURCE: t.provenanceNoSource,
    OFFLINE_DEMO: t.provenanceDemo,
  };

  return {
    ...base,
    source: activeSource?.source ?? "—",
    freshness: activeSource
      ? activeSource.fresh
        ? `${t.freshnessFresh} · ${formatFreshnessAge(activeSource.message_age_seconds, t)}`
        : t.staleData
      : t.noFreshSource,
    coverageDetail: coverageDetail[status.mode],
    provenance: provenance[status.mode],
  };
}

function formatFreshnessAge(ageSeconds: number | null, t: Dict): string {
  if (ageSeconds === null) return t.ageUnavailable;
  if (ageSeconds < 5) return t.justNow;
  if (ageSeconds < 60) return t.secondsAgo(Math.round(ageSeconds));
  return t.minutesAgo(Math.round(ageSeconds / 60));
}

export type TransitionEvent = {
  kind: "cloud_to_edge" | "cloud_restored";
  simulated: boolean;
};

export function transitionEvent(
  previous: OperatingMode | null,
  next: ResilienceStatus,
): TransitionEvent | null {
  if (!previous || previous === next.mode) return null;
  if (
    previous === "CLOUD_LIVE" &&
    (next.mode === "EDGE_LIVE" || next.mode === "EDGE_REPLAY")
  ) {
    return { kind: "cloud_to_edge", simulated: next.simulated };
  }
  if (
    next.mode === "CLOUD_LIVE" &&
    (previous === "EDGE_LIVE" || previous === "EDGE_REPLAY")
  ) {
    return { kind: "cloud_restored", simulated: next.simulated };
  }
  return null;
}

export function vesselIntegrity(feature: LiveVesselFeature): DisplayState | "provider_interpolated" {
  if (feature.properties.synthesized) return "provider_interpolated";
  return feature.properties.display_state ?? "live";
}

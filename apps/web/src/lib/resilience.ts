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

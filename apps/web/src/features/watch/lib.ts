// Pure helpers for the Watch Floor: formatting, colours, track lookup.

import type { Level, TrackDto } from "./api";

export const LEVEL_COLOR: Record<Level, string> = {
  HIGH: "#ff4d4f",
  MEDIUM: "#ffa940",
  LOW: "#4cc9f0",
};

export const STATUS_LABEL: Record<string, string> = {
  new: "New",
  under_review: "Under review",
  confirmed: "Confirmed",
  escalated: "Escalated",
  false_alarm: "False alarm",
};

export interface KindMeta {
  label: string;
  short: string;
  color: string;
  what: string;
}

export const KIND_META: Record<string, KindMeta> = {
  ais_gap: { label: "AIS silence", short: "DARK", color: "#b197fc", what: "Transponder stopped reporting while the vessel should be visible." },
  loitering: { label: "Loitering", short: "LOITER", color: "#ffa94d", what: "Lingering in a small area away from port or anchorage." },
  rendezvous: { label: "Slow rendezvous", short: "MEET", color: "#ff6b9d", what: "Two vessels meeting and drifting together at sea." },
  cluster: { label: "Vessel cluster", short: "CLUSTER", color: "#f783ac", what: "Several vessels assembling outside a port or fishing ground." },
  zone_entry: { label: "Zone entry", short: "ZONE", color: "#ff6b6b", what: "Entering a protected, restricted or cable zone." },
  position_jump: { label: "Position anomaly", short: "SPOOF?", color: "#74c0fc", what: "Reported position jumps in a physically impossible way." },
  identity_conflict: { label: "Identity conflict", short: "CLONE?", color: "#63e6be", what: "One MMSI reported from two places at once." },
  route_deviation: { label: "Off-route", short: "OFF-ROUTE", color: "#ffd43b", what: "Travelling through water normal traffic does not use." },
  dark_rendezvous: { label: "Possible dark transfer", short: "DARK STS", color: "#e599f7", what: "One vessel dark while another stops where it could have gone." },
};

export const kindMeta = (k: string): KindMeta =>
  KIND_META[k] ?? { label: k, short: k.toUpperCase(), color: "#adb5bd", what: "" };

export const ZONE_COLOR: Record<string, string> = {
  protected: "#ff6b6b",
  cable: "#da77f2",
  restricted: "#ffa94d",
  port: "#74c0fc",
  anchorage: "#4dabf7",
  fishing_ground: "#69db7c",
};

const TZ = "Asia/Taipei";

export function fmtClock(t: number): string {
  return new Date(t * 1000).toLocaleString("en-GB", {
    timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

export function fmtHM(t: number): string {
  return new Date(t * 1000).toLocaleTimeString("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });
}

export function fmtDur(seconds: number): string {
  const m = Math.max(0, Math.round(seconds / 60));
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

export function ago(now: number, t: number): string {
  const d = now - t;
  if (d < 90) return "just now";
  return `${fmtDur(d)} ago`;
}

export function confidenceLabel(c: number): string {
  return c >= 0.75 ? "High" : c >= 0.55 ? "Medium" : "Low";
}

export function fmtPos(lat: number, lon: number): string {
  return `${lat.toFixed(2)}°N ${lon.toFixed(2)}°E`;
}

export const FLAG_NAME: Record<string, string> = {
  TW: "Taiwan", CN: "China", HK: "Hong Kong", PA: "Panama", MH: "Marshall Is.", LR: "Liberia", JP: "Japan",
};

export interface VesselPoint {
  lat: number;
  lon: number;
  sog: number | null;
  /** Seconds since the last fix at time t. */
  age: number;
  /** Index of the last fix at or before t. */
  idx: number;
}

/** Last-known position of a track at time t (null when not yet / no longer reporting). */
export function positionAt(tr: TrackDto, t: number, staleAfter = 3 * 3600): VesselPoint | null {
  const n = tr.t.length;
  if (n === 0 || t < tr.t[0]) return null;
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (tr.t[mid] <= t) lo = mid;
    else hi = mid - 1;
  }
  const age = t - tr.t[lo];
  if (lo === n - 1 && age > 1800) return null; // voyage finished
  if (age > staleAfter) return null;
  return { lat: tr.lat[lo], lon: tr.lon[lo], sog: tr.sog[lo], age, idx: lo };
}

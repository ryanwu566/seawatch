// Pure GeoJSON builders for the Watch Floor map.

import type { AlertDetail, AlertSummary, Level, Scenario, TrackDto } from "./api";
import { KIND_META, LEVEL_COLOR, ZONE_COLOR, ago, fmtDur, positionAt } from "./lib";

type FC = GeoJSON.FeatureCollection;
const empty = (): FC => ({ type: "FeatureCollection", features: [] });

const RANK: Record<Level, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 };

export function circlePolygon(lat: number, lon: number, radiusNm: number, n = 72): [number, number][] {
  const ring: [number, number][] = [];
  const dLat = radiusNm / 60;
  const dLon = radiusNm / 60 / Math.cos((lat * Math.PI) / 180);
  for (let i = 0; i <= n; i++) {
    const a = (2 * Math.PI * i) / n;
    ring.push([lon + dLon * Math.sin(a), lat + dLat * Math.cos(a)]);
  }
  return ring;
}

export function zonesFC(sc: Scenario): FC {
  return {
    type: "FeatureCollection",
    features: sc.zones.map((z) => ({
      type: "Feature",
      properties: { id: z.id, name: z.name, kind: z.kind, color: ZONE_COLOR[z.kind] ?? "#adb5bd" },
      geometry: { type: "Polygon", coordinates: [[...z.polygon.map(([la, lo]) => [lo, la]), [z.polygon[0][1], z.polygon[0][0]]]] },
    })),
  };
}

export function coverageFC(sc: Scenario): FC {
  return {
    type: "FeatureCollection",
    features: sc.receivers.map((r) => ({
      type: "Feature",
      properties: { id: r.id },
      geometry: { type: "Polygon", coordinates: [circlePolygon(r.lat, r.lon, r.range_nm)] },
    })),
  };
}

export function allTracksFC(tracks: TrackDto[]): FC {
  return {
    type: "FeatureCollection",
    features: tracks.map((t) => ({
      type: "Feature",
      properties: { mmsi: t.mmsi },
      geometry: { type: "LineString", coordinates: t.lon.map((lo, i) => [lo, t.lat[i]]) },
    })),
  };
}

export function levelByMmsi(alerts: AlertSummary[]): Map<string, { level: Level; id: string }> {
  const m = new Map<string, { level: Level; id: string }>();
  for (const a of alerts) {
    for (const mm of a.mmsis) {
      const cur = m.get(mm);
      if (!cur || RANK[a.level] > RANK[cur.level]) m.set(mm, { level: a.level, id: a.id });
    }
  }
  return m;
}

export function vesselsFC(tracks: TrackDto[], t: number, flagged: Map<string, { level: Level; id: string }>, selectedMmsis: Set<string>): FC {
  const features: GeoJSON.Feature[] = [];
  for (const tr of tracks) {
    const p = positionAt(tr, t);
    if (!p) continue;
    const f = flagged.get(tr.mmsi);
    const stale = p.age > 900;
    features.push({
      type: "Feature",
      properties: {
        mmsi: tr.mmsi,
        name: tr.name,
        type: tr.type,
        flag: tr.flag,
        level: f?.level ?? "NONE",
        alertId: f?.id ?? "",
        color: f ? LEVEL_COLOR[f.level] : "#7a8ba3",
        flagged: f ? 1 : 0,
        selected: selectedMmsis.has(tr.mmsi) ? 1 : 0,
        stale: stale ? 1 : 0,
        label: f ? tr.name : "",
        sog: p.sog ?? -1,
        info: stale ? `Last report ${fmtDur(p.age)} ago` : p.sog != null ? `${p.sog.toFixed(1)} kn` : "",
      },
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    });
  }
  return { type: "FeatureCollection", features };
}

export function alertRingsFC(alerts: AlertSummary[]): FC {
  return {
    type: "FeatureCollection",
    features: alerts.map((a) => ({
      type: "Feature",
      properties: { id: a.id, level: a.level, color: LEVEL_COLOR[a.level], risk: a.risk, title: a.title },
      geometry: { type: "Point", coordinates: [a.lon, a.lat] },
    })),
  };
}

/** Recent path of flagged vessels, drawn in their alert colour. */
export function trailsFC(tracks: TrackDto[], t: number, flagged: Map<string, { level: Level; id: string }>, only: Set<string>, hours = 14): FC {
  const features: GeoJSON.Feature[] = [];
  for (const tr of tracks) {
    const f = flagged.get(tr.mmsi);
    if (!f || !only.has(tr.mmsi)) continue;
    const coords: [number, number][] = [];
    for (let i = 0; i < tr.t.length; i++) {
      if (tr.t[i] > t) break;
      if (tr.t[i] >= t - hours * 3600) coords.push([tr.lon[i], tr.lat[i]]);
    }
    if (coords.length > 1) {
      features.push({
        type: "Feature",
        properties: { mmsi: tr.mmsi, color: LEVEL_COLOR[f.level], selected: 0 },
        geometry: { type: "LineString", coordinates: coords },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

/** Evidence geometry for the selected alert: event paths + numbered badge points. */
export function eventGeometry(detail: AlertDetail | null): { lines: FC; points: FC; bounds: [[number, number], [number, number]] | null } {
  if (!detail) return { lines: empty(), points: empty(), bounds: null };
  const lines: GeoJSON.Feature[] = [];
  const points: GeoJSON.Feature[] = [];
  const pts: [number, number][] = [];
  detail.timeline.forEach((e, i) => {
    const meta = KIND_META[e.kind];
    const color = meta?.color ?? "#adb5bd";
    if (e.path.length > 1) {
      lines.push({
        type: "Feature",
        properties: { kind: e.kind, color, dashed: e.kind === "ais_gap" ? 1 : 0, n: i + 1 },
        geometry: { type: "LineString", coordinates: e.path.map(([la, lo]) => [lo, la]) },
      });
      e.path.forEach(([la, lo]) => pts.push([lo, la]));
    }
    points.push({
      type: "Feature",
      properties: { kind: e.kind, color, n: i + 1, label: meta?.short ?? e.kind, summary: e.summary, id: e.id },
      geometry: { type: "Point", coordinates: [e.lon, e.lat] },
    });
    pts.push([e.lon, e.lat]);
  });
  if (!pts.length) return { lines: { type: "FeatureCollection", features: lines }, points: { type: "FeatureCollection", features: points }, bounds: null };
  const lons = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  return {
    lines: { type: "FeatureCollection", features: lines },
    points: { type: "FeatureCollection", features: points },
    bounds: [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
  };
}

export { ago };

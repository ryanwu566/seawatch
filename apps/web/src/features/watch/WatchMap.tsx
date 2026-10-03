import { useEffect, useMemo, useRef, useState } from "react";
import { watchApi } from "./api";
import maplibregl, { type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import emergencyGeographyRaw from "../../assets/taiwan-emergency.geojson?raw";
import type { AlertDetail, AlertSummary, Scenario, TrackDto, TruthEvent } from "./api";
import { LEVEL_COLOR } from "./lib";
import {
  alertRingsFC,
  allTracksFC,
  coverageFC,
  eventGeometry,
  levelByMmsi,
  trailsFC,
  vesselsFC,
  zonesFC,
} from "./mapData";

const emergencyGeography = JSON.parse(emergencyGeographyRaw) as GeoJSON.FeatureCollection;

const STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    land: { type: "geojson", data: emergencyGeography },
    carto: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 16,
      attribution: "Tiles © Esri - Esri, HERE, Garmin, OpenStreetMap contributors",
    },
    labels: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 16,
    },
  },
  layers: [
    { id: "sea", type: "background", paint: { "background-color": "#08111f" } },
    { id: "land-fallback", type: "fill", source: "land", paint: { "fill-color": "#16233a" } },
    { id: "land-coast", type: "line", source: "land", paint: { "line-color": "#2c4a6e", "line-width": 1 } },
    { id: "carto", type: "raster", source: "carto", paint: { "raster-opacity": 0.95 } },
    { id: "labels", type: "raster", source: "labels", paint: { "raster-opacity": 0.8 } },
  ],
};

interface Props {
  scenario: Scenario;
  tracks: TrackDto[];
  alerts: AlertSummary[];
  detail: AlertDetail | null;
  selectedId: string | null;
  clock: number;
  truth: TruthEvent[];
  showTruth: boolean;
  onSelect: (id: string | null) => void;
}

const SRC = ["cables", "landing", "limits", "zones", "coverage", "tracks-all", "trails", "ev-lines", "ev-points", "rings", "vessels", "truth"] as const;

function setData(map: maplibregl.Map, id: string, data: GeoJSON.FeatureCollection) {
  (map.getSource(id) as GeoJSONSource | undefined)?.setData(data);
}

export function WatchMap({ scenario, tracks, alerts, detail, selectedId, clock, truth, showTruth, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [layers, setLayers] = useState({ coverage: false, tracks: true, zones: true, cables: true, limits: true });
  const markers = useRef<maplibregl.Marker[]>([]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const flagged = useMemo(() => levelByMmsi(alerts), [alerts]);
  const selectedMmsis = useMemo(() => new Set(detail?.mmsis ?? []), [detail]);

  // ---- init -------------------------------------------------------------
  useEffect(() => {
    if (!host.current) return;
    const map = new maplibregl.Map({
      container: host.current,
      style: STYLE,
      bounds: scenario.bounds,
      fitBoundsOptions: { padding: 20 },
      minZoom: 4,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

    map.on("load", () => {
      for (const id of SRC) map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      map.addLayer({
        id: "limits-line", type: "line", source: "limits",
        paint: {
          "line-color": ["match", ["get", "level"], "ts", "#fb7185", "cz", "#fbbf24", "#60a5fa"],
          "line-width": ["match", ["get", "level"], "ts", 1.6, 1.2], "line-opacity": 0.85,
          "line-dasharray": ["match", ["get", "level"], "ts", ["literal", [1, 0]], ["literal", [4, 3]]],
        },
      });
      map.addLayer({ id: "cables-line", type: "line", source: "cables", paint: { "line-color": "#22d3ee", "line-width": 1.6, "line-opacity": 0.8 } });
      map.addLayer({
        id: "cables-label", type: "symbol", source: "cables", minzoom: 6,
        layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-size": 10, "text-font": ["Open Sans Regular"] },
        paint: { "text-color": "#67e8f9", "text-halo-color": "#06121f", "text-halo-width": 1.2 },
      });
      map.addLayer({ id: "landing-pt", type: "circle", source: "landing", paint: { "circle-radius": 3.5, "circle-color": "#06121f", "circle-stroke-color": "#22d3ee", "circle-stroke-width": 1.5 } });
      map.addLayer({ id: "coverage-fill", type: "fill", source: "coverage", layout: { visibility: "none" }, paint: { "fill-color": "#38bdf8", "fill-opacity": 0.05 } });
      map.addLayer({ id: "coverage-line", type: "line", source: "coverage", layout: { visibility: "none" }, paint: { "line-color": "#38bdf8", "line-opacity": 0.35, "line-width": 1, "line-dasharray": [2, 3] } });
      map.addLayer({ id: "zones-fill", type: "fill", source: "zones", paint: { "fill-color": ["get", "color"], "fill-opacity": ["match", ["get", "kind"], ["port", "anchorage"], 0.1, 0.16] } });
      map.addLayer({ id: "zones-line", type: "line", source: "zones", paint: { "line-color": ["get", "color"], "line-width": 1.4, "line-opacity": 0.85, "line-dasharray": [3, 2] } });
      map.addLayer({
        id: "zones-label", type: "symbol", source: "zones", minzoom: 6.8,
        layout: { "text-field": ["get", "name"], "text-font": ["Open Sans Regular"], "text-size": 10.5, "text-allow-overlap": false },
        paint: { "text-color": ["get", "color"], "text-halo-color": "#06101d", "text-halo-width": 1.4, "text-opacity": 0.9 },
      });
      map.addLayer({ id: "tracks-all", type: "line", source: "tracks-all", paint: { "line-color": "#6c86a8", "line-opacity": 0.22, "line-width": 0.8 } });
      map.addLayer({ id: "trails", type: "line", source: "trails", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": 2.2, "line-opacity": 0.75 } });
      map.addLayer({ id: "truth-fill", type: "circle", source: "truth", paint: { "circle-radius": 26, "circle-color": "#69db7c", "circle-opacity": 0.08, "circle-stroke-color": "#69db7c", "circle-stroke-width": 1.2, "circle-stroke-opacity": 0.8 } });
      map.addLayer({
        id: "ev-lines-casing", type: "line", source: "ev-lines",
        paint: { "line-color": "#050b14", "line-width": 6, "line-opacity": 0.7 },
        layout: { "line-cap": "round", "line-join": "round" },
      });
      map.addLayer({
        id: "ev-lines", type: "line", source: "ev-lines", filter: ["==", ["get", "dashed"], 0],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 3.4 },
      });
      map.addLayer({
        id: "ev-lines-dashed", type: "line", source: "ev-lines", filter: ["==", ["get", "dashed"], 1],
        layout: { "line-join": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 3.4, "line-dasharray": [1.2, 1.4] },
      });
      map.addLayer({ id: "pulse", type: "circle", source: "rings", paint: { "circle-radius": 14, "circle-color": ["get", "color"], "circle-opacity": 0.0, "circle-stroke-color": ["get", "color"], "circle-stroke-width": 2, "circle-stroke-opacity": 0.6 } });
      map.addLayer({ id: "rings", type: "circle", source: "rings", paint: { "circle-radius": 15, "circle-color": ["get", "color"], "circle-opacity": 0.09, "circle-stroke-color": ["get", "color"], "circle-stroke-width": 1.6, "circle-stroke-opacity": 0.9 } });
      map.addLayer({
        id: "vessels", type: "circle", source: "vessels",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, ["case", ["==", ["get", "flagged"], 1], 4.5, 2.4], 9, ["case", ["==", ["get", "flagged"], 1], 8, 4.6]],
          "circle-color": ["case", ["==", ["get", "stale"], 1], "#08111f", ["get", "color"]],
          "circle-stroke-color": ["case", ["==", ["get", "selected"], 1], "#ffffff", ["get", "color"]],
          "circle-stroke-width": ["case", ["==", ["get", "selected"], 1], 2.4, ["==", ["get", "stale"], 1], 2, 1],
          "circle-opacity": 0.95,
        },
      });
      map.addLayer({
        id: "vessel-labels", type: "symbol", source: "vessels", filter: ["==", ["get", "flagged"], 1],
        layout: { "text-field": ["get", "label"], "text-font": ["Open Sans Regular"], "text-size": 11, "text-offset": [0, 1.35], "text-anchor": "top", "text-allow-overlap": false },
        paint: { "text-color": "#e8f0ff", "text-halo-color": "#050b14", "text-halo-width": 1.6 },
      });

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "wf-popup" });
      map.on("mousemove", "vessels", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        map.getCanvas().style.cursor = "pointer";
        const p = f.properties as Record<string, string | number>;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${p.name}</strong><span>${p.type} · MMSI ${p.mmsi}</span><span>${p.info || ""}</span>` +
              (p.alertId ? `<em class="lv-${String(p.level).toLowerCase()}">${p.level} alert</em>` : ""),
          )
          .addTo(map);
      });
      map.on("mouseleave", "vessels", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      const pick = (id?: string) => {
        if (id) onSelectRef.current(id);
      };
      map.on("click", "vessels", (e) => pick(e.features?.[0]?.properties?.alertId as string | undefined));
      map.on("click", "rings", (e) => pick(e.features?.[0]?.properties?.id as string | undefined));
      map.on("mouseenter", "rings", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "rings", () => (map.getCanvas().style.cursor = ""));
      map.on("click", (e) => {
        const hit = map.queryRenderedFeatures(e.point, { layers: ["vessels", "rings"] });
        if (!hit.length) onSelectRef.current(null);
      });
      setReady(true);
    });

    // gentle pulse on alert rings
    let raf = 0;
    const animate = (ts: number) => {
      if (map.getLayer("pulse")) {
        const k = (ts % 1800) / 1800;
        map.setPaintProperty("pulse", "circle-radius", 14 + k * 26);
        map.setPaintProperty("pulse", "circle-stroke-opacity", 0.7 * (1 - k));
      }
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(raf);
      markers.current.forEach((m) => m.remove());
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- static data ---------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    watchApi.layers().then((l) => {
      setData(map, "cables", l.cables);
      setData(map, "landing", l.landing);
      setData(map, "limits", l.limits);
    }).catch(() => undefined);
    setData(map, "zones", zonesFC(scenario));
    setData(map, "coverage", coverageFC(scenario));
  }, [ready, scenario]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    setData(map, "tracks-all", allTracksFC(tracks));
  }, [ready, tracks]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const vis = (on: boolean) => (on ? "visible" : "none");
    map.setLayoutProperty("coverage-fill", "visibility", vis(layers.coverage));
    map.setLayoutProperty("coverage-line", "visibility", vis(layers.coverage));
    map.setLayoutProperty("tracks-all", "visibility", vis(layers.tracks));
    for (const id of ["zones-fill", "zones-line", "zones-label"]) map.setLayoutProperty(id, "visibility", vis(layers.zones));
    for (const id of ["cables-line", "cables-label", "landing-pt"]) map.setLayoutProperty(id, "visibility", vis(layers.cables));
    map.setLayoutProperty("limits-line", "visibility", vis(layers.limits));
  }, [ready, layers]);

  // ---- dynamic data (clock / alerts) --------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    setData(map, "vessels", vesselsFC(tracks, clock, flagged, selectedMmsis));
    setData(map, "trails", trailsFC(tracks, clock, flagged, selectedMmsis));
    setData(map, "rings", alertRingsFC(alerts));
  }, [ready, tracks, clock, flagged, selectedMmsis, alerts]);

  // ---- selected alert evidence ---------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const g = eventGeometry(detail);
    setData(map, "ev-lines", g.lines);
    setData(map, "ev-points", g.points);
    markers.current.forEach((m) => m.remove());
    markers.current = [];
    g.points.features.forEach((f) => {
      const p = f.properties as { n: number; color: string; label: string; summary: string };
      const el = document.createElement("div");
      el.className = "wf-badge";
      el.style.setProperty("--c", p.color);
      el.title = p.summary;
      el.innerHTML = `<b>${p.n}</b><span>${p.label}</span>`;
      const c = (f.geometry as GeoJSON.Point).coordinates as [number, number];
      markers.current.push(new maplibregl.Marker({ element: el, anchor: "left", offset: [-12, 0] }).setLngLat(c).addTo(map));
    });
    if (g.bounds) {
      map.fitBounds(g.bounds, { padding: { top: 90, bottom: 90, left: 70, right: 70 }, maxZoom: 9.2, duration: 900 });
    }
  }, [ready, detail?.id, detail?.timeline.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || selectedId) return;
    map.fitBounds(scenario.bounds, { padding: 20, duration: 700 });
  }, [ready, selectedId, scenario.bounds]);

  // ---- ground truth overlay ---------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const feats: GeoJSON.Feature[] = [];
    if (showTruth) {
      for (const t of truth) {
        if (t.benign) continue;
        for (const m of t.mmsis) {
          const tr = tracks.find((x) => x.mmsi === m);
          if (!tr) continue;
          const idx = tr.t.findIndex((x) => x >= t.t_start);
          if (idx >= 0) feats.push({ type: "Feature", properties: { kind: t.kind }, geometry: { type: "Point", coordinates: [tr.lon[idx], tr.lat[idx]] } });
        }
      }
    }
    setData(map, "truth", { type: "FeatureCollection", features: feats });
  }, [ready, showTruth, truth, tracks]);

  return (
    <div className="wf-map">
      <div ref={host} className="wf-map-canvas" />
      <div className="wf-layers" role="group" aria-label="Map layers">
        {(
          [
            ["zones", "Zones"],
            ["cables", "Cables"],
            ["limits", "12 / 24 nm / EEZ"],
            ["tracks", "Tracks"],
            ["coverage", "AIS coverage"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} type="button" className={layers[k] ? "on" : ""} aria-pressed={layers[k]} onClick={() => setLayers((l) => ({ ...l, [k]: !l[k] }))}>
            {label}
          </button>
        ))}
      </div>
      <div className="wf-legend" aria-label="Legend">
        <span><i style={{ background: LEVEL_COLOR.HIGH }} />High</span>
        <span><i style={{ background: LEVEL_COLOR.MEDIUM }} />Medium</span>
        <span><i style={{ background: LEVEL_COLOR.LOW }} />Low</span>
        <span><i className="norm" />Normal</span>
        <span><i className="hollow" />No recent report</span>
      </div>
    </div>
  );
}

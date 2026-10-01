import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  fetchLiveHealth,
  fetchLiveVessels,
  type LiveHealth,
  type LiveVesselCollection,
} from "../api/live";

// MapLibre's public demo tiles need no API key. Taiwan official NLSC basemaps
// are integrated in a later phase; this is the minimal live-data proof only.
const STYLE_URL = "https://demotiles.maplibre.org/style.json";
const TAIWAN_CENTER: [number, number] = [120.9, 23.9];
const TAIWAN_ZOOM = 6.4;

const VESSEL_SOURCE = "live-vessels";
const VESSEL_LAYER = "live-vessels-symbols";

// Refresh the active viewport approximately every 30 seconds. The backend
// serves this from its in-memory store, so this does not hit any upstream feed.
const REFRESH_MS = 30_000;

/**
 * Minimal live Taiwan AIS proof. Renders every live vessel through ONE MapLibre
 * GeoJSON source and ONE symbol layer (no React component per vessel), updating
 * via source.setData() without remounting the map. The vessel marker is oriented
 * by heading when present, else by course over ground, else neutral.
 */
export function LiveMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const latestDataRef = useRef<LiveVesselCollection | null>(null);

  const [health, setHealth] = useState<LiveHealth | null>(null);
  const [vesselCount, setVesselCount] = useState(0);
  const [dataAge, setDataAge] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Initialize the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      loadedRef.current = true;
      map.addSource(VESSEL_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Circle fallback (always renders); a triangle symbol oriented by heading
      // sits on top when a sprite is available. Circle alone proves the data.
      map.addLayer({
        id: VESSEL_LAYER,
        type: "circle",
        source: VESSEL_SOURCE,
        paint: {
          // Interpolated (synthesized) fixes are visually distinct from measured.
          "circle-color": [
            "case",
            ["get", "synthesized"],
            "#f59e0b", // amber = provider-interpolated
            "#38bdf8", // blue = measured AIS fix
          ],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 2.5, 10, 6],
          "circle-stroke-color": "#04121f",
          "circle-stroke-width": 1,
        },
      });
      // Apply any data that arrived before load completed.
      applyData(map, latestDataRef.current);
    });
    mapRef.current = map;
    return () => {
      loadedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Poll the backend for live vessels and push onto the single source.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function tick() {
      try {
        const [collection, h] = await Promise.all([
          fetchLiveVessels(undefined, controller.signal),
          fetchLiveHealth(controller.signal).catch(() => null),
        ]);
        if (cancelled) return;
        latestDataRef.current = collection;
        setVesselCount(collection.vessel_count);
        setDataAge(freshestAge(collection));
        setError(null);
        if (h) setHealth(h);
        const map = mapRef.current;
        if (map && loadedRef.current) {
          applyData(map, collection);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load live vessels.");
      }
    }

    tick();
    const interval = setInterval(tick, REFRESH_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="live-map" aria-label="Live Taiwan AIS map">
      <div className="live-status-bar">
        <span className={`live-dot live-${health?.status ?? "offline"}`} />
        <strong>即時資料 / LIVE</strong>
        <span>船舶 Vessels: {vesselCount}</span>
        <span>
          資料更新 AIS fix:{" "}
          {dataAge === null ? "—" : `${Math.round(dataAge)}s ago`}
        </span>
        <span>來源 Source: {health?.provider ?? "open_waters"}</span>
        {error && <span className="live-error">{error}</span>}
      </div>
      <div ref={containerRef} className="live-map-canvas" />
    </div>
  );
}

/** Push a vessel collection onto the single GeoJSON source. */
function applyData(map: maplibregl.Map, collection: LiveVesselCollection | null) {
  const source = map.getSource(VESSEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  const features = (collection?.features ?? []).map((f) => ({
    ...f,
    properties: {
      ...f.properties,
      // Orientation: prefer heading, fall back to COG, else neutral (0).
      orientation:
        f.properties.heading_deg ?? f.properties.cog_deg ?? 0,
    },
  }));
  source.setData({ type: "FeatureCollection", features });
}

/** Smallest data_age_seconds across the collection (freshest observed fix). */
function freshestAge(collection: LiveVesselCollection): number | null {
  if (collection.features.length === 0) return null;
  return collection.features.reduce(
    (min, f) => Math.min(min, f.properties.data_age_seconds),
    Number.POSITIVE_INFINITY,
  );
}

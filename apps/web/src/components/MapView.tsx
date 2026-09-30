import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { LineStringGeometry } from "../types";

interface MapViewProps {
  /** Geometry of the currently selected track, if loaded. */
  geometry: LineStringGeometry | null;
  selectedTrackId: string | null;
  loading?: boolean;
  error?: string | null;
  /** Initial map center [lng, lat] for the active region. */
  center?: [number, number];
  /** Initial map zoom for the active region. */
  zoom?: number;
}

// MapLibre's public demo tiles need no API key — appropriate for a hackathon MVP.
const STYLE_URL = "https://demotiles.maplibre.org/style.json";
const FALLBACK_CENTER: [number, number] = [-122.4, 37.75]; // San Francisco Bay cohort area
const FALLBACK_ZOOM = 8;

const TRACK_SOURCE = "selected-track";
const TRACK_LINE_LAYER = "selected-track-line";
const TRACK_POINT_LAYER = "selected-track-endpoints";

/**
 * Maritime base map. Draws the selected track as a GeoJSON LineString when its
 * geometry is available. Coordinates are never fabricated: with no geometry the
 * map shows the base map and an informative state.
 */
export function MapView({ geometry, selectedTrackId, loading, error, center, zoom }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);

  // Initialize the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: center ?? FALLBACK_CENTER,
      zoom: zoom ?? FALLBACK_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      loadedRef.current = true;
      map.addSource(TRACK_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: TRACK_LINE_LAYER,
        type: "line",
        source: TRACK_SOURCE,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#38bdf8", "line-width": 3 },
      });
      map.addLayer({
        id: TRACK_POINT_LAYER,
        type: "circle",
        source: TRACK_SOURCE,
        filter: ["==", "$type", "Point"],
        paint: {
          "circle-radius": 5,
          "circle-color": "#fbbf24",
          "circle-stroke-color": "#04121f",
          "circle-stroke-width": 2,
        },
      });
    });
    mapRef.current = map;

    return () => {
      loadedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Sync the selected track geometry onto the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    const apply = () => {
      const source = map.getSource(TRACK_SOURCE) as maplibregl.GeoJSONSource | undefined;
      if (!source) {
        return;
      }
      if (!geometry || geometry.coordinates.length < 2) {
        source.setData({ type: "FeatureCollection", features: [] });
        return;
      }
      const coords = geometry.coordinates;
      const endpoints = [coords[0], coords[coords.length - 1]];
      source.setData({
        type: "FeatureCollection",
        features: [
          { type: "Feature", geometry, properties: {} },
          ...endpoints.map((position) => ({
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: position },
            properties: {},
          })),
        ],
      });
      const bounds = coords.reduce(
        (acc, [lng, lat]) => acc.extend([lng, lat] as [number, number]),
        new maplibregl.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]),
      );
      map.fitBounds(bounds, { padding: 48, maxZoom: 13, duration: 300 });
    };

    if (loadedRef.current) {
      apply();
    } else {
      map.once("load", apply);
    }
  }, [geometry]);

  const hasTrack = Boolean(geometry && geometry.coordinates.length >= 2);

  return (
    <div className="map-view" aria-label="Maritime map">
      <div ref={containerRef} className="map-canvas" />
      {!hasTrack && (
        <div className="map-overlay" role="note">
          {loading ? (
            <>
              <strong>Loading track geometry…</strong>
            </>
          ) : error ? (
            <>
              <strong>Track geometry unavailable</strong>
              <p>{error}</p>
            </>
          ) : selectedTrackId ? (
            <>
              <strong>No geometry for this track</strong>
              <p>The backend did not return coordinates for {selectedTrackId}.</p>
            </>
          ) : (
            <>
              <strong>Select a review candidate</strong>
              <p>Choose an alert to draw its trajectory on the map.</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { AlertSummary } from "../types";

interface MapViewProps {
  alerts: AlertSummary[];
  selectedId: string | null;
}

// Optional geographic fields. The current SeaWatch API exposes privacy-safe
// metadata only and does NOT return coordinates, so these are optional and the
// map degrades gracefully when they are absent.
type MaybeGeo = AlertSummary & { longitude?: number; latitude?: number };

function hasCoordinates(alert: MaybeGeo): alert is MaybeGeo &
  Required<Pick<MaybeGeo, "longitude" | "latitude">> {
  return (
    typeof alert.longitude === "number" && typeof alert.latitude === "number"
  );
}

// MapLibre's public demo tiles need no API key — appropriate for a hackathon MVP.
const STYLE_URL = "https://demotiles.maplibre.org/style.json";
const INITIAL_CENTER: [number, number] = [-122.4, 37.75]; // San Francisco Bay cohort area
const INITIAL_ZOOM = 7;

/**
 * Maritime base map. Plots alert markers when the API provides coordinates and
 * otherwise shows an informative overlay (the current API is position-free).
 */
export function MapView({ alerts, selectedId }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  // Initialize the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Sync markers when alerts or selection change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    const geoAlerts = (alerts as MaybeGeo[]).filter(hasCoordinates);
    geoAlerts.forEach((alert) => {
      const element = document.createElement("div");
      element.className =
        alert.alert_id === selectedId ? "map-marker selected" : "map-marker";
      const marker = new maplibregl.Marker({ element })
        .setLngLat([alert.longitude, alert.latitude])
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setText(
            `Track ${alert.track_id} · rank ${alert.rank}`,
          ),
        )
        .addTo(map);
      markersRef.current.push(marker);
    });
  }, [alerts, selectedId]);

  const geoCount = (alerts as MaybeGeo[]).filter(hasCoordinates).length;

  return (
    <div className="map-view" aria-label="Maritime map">
      <div ref={containerRef} className="map-canvas" />
      {geoCount === 0 && (
        <div className="map-overlay" role="note">
          <strong>Positions not exposed by API</strong>
          <p>
            The current SeaWatch API returns privacy-safe metadata without vessel
            coordinates, so tracks are not plotted.
          </p>
          {selectedId && (
            <p className="map-selected">Selected: {selectedId}</p>
          )}
        </div>
      )}
    </div>
  );
}

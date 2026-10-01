import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { LiveVesselFeature } from "../api/live";
import type { LayerState } from "../lib/layerState";
import {
  MAPLIBRE_DEMO_STYLE,
  TAIWAN_CENTER,
  TAIWAN_ZOOM,
  airspaceGeoJson,
  nlscStyle,
  portsGeoJson,
} from "../config/taiwanMap";
import { projectPosition, type MeasuredFix } from "../lib/interpolation";
import { makeShipIcon } from "../lib/shipIcon";

export interface Viewport {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

interface MapCanvasProps {
  vessels: LiveVesselFeature[];
  layers: LayerState;
  selectedTrack: GeoJSON.Feature | null;
  onSelectVessel: (feature: LiveVesselFeature) => void;
  onViewportChange: (viewport: Viewport) => void;
  onBaseMapError?: (message: string | null) => void;
}

const VESSEL_SOURCE = "live-vessels";
const VESSEL_LAYER = "live-vessels-symbols";
const TRACK_SOURCE = "selected-track";
const TRACK_LAYER = "selected-track-line";
const PORT_SOURCE = "ports";
const PORT_LAYER = "ports-circle";
const PORT_LABEL = "ports-label";
const AIRSPACE_SOURCE = "airspace";
const AIRSPACE_FILL = "airspace-fill";
const AIRSPACE_LINE = "airspace-line";
const SHIP_ICON = "ship-icon";

/**
 * The product map. Renders all live vessels through ONE GeoJSON source + ONE
 * symbol layer (no DOM element per vessel), animates smooth motion via frontend
 * visual interpolation between real fixes, draws the selected vessel's trail,
 * and overlays public ports + airspace context. Base map switches between the
 * official NLSC e-Map / Orthophoto with a demo-tile fallback.
 */
export function MapCanvas({
  vessels,
  layers,
  selectedTrack,
  onSelectVessel,
  onViewportChange,
  onBaseMapError,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const vesselsRef = useRef<LiveVesselFeature[]>([]);
  const rafRef = useRef<number | null>(null);
  const currentBaseRef = useRef<string>(layers.baseMap);

  // Keep the latest vessels in a ref for the animation loop.
  vesselsRef.current = vessels;

  // Initialize the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: nlscStyle(layers.baseMap),
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    // If the official NLSC tiles error (e.g. CORS), fall back to demo tiles and
    // report honestly instead of faking success.
    map.on("error", (e) => {
      const msg = (e?.error && (e.error as Error).message) || "";
      if (msg && /tile|source|network|fetch/i.test(msg)) {
        onBaseMapError?.(msg);
      }
    });

    map.on("load", () => {
      loadedRef.current = true;
      installOverlays(map);
      applyVessels(map, vesselsRef.current);
      applyLayerVisibility(map, layers);
      applyPorts(map, layers);
      applyAirspace(map, layers);
      emitViewport(map, onViewportChange);
    });

    map.on("moveend", () => emitViewport(map, onViewportChange));

    map.on("click", VESSEL_LAYER, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const match = vesselsRef.current.find((v) => v.id === feature.id);
      if (match) onSelectVessel(match);
    });
    map.on("mouseenter", VESSEL_LAYER, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", VESSEL_LAYER, () => {
      map.getCanvas().style.cursor = "";
    });

    mapRef.current = map;
    startAnimation();

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      loadedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Switch base map when it changes (setStyle, then reinstall overlays).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (currentBaseRef.current === layers.baseMap) return;
    currentBaseRef.current = layers.baseMap;
    onBaseMapError?.(null);
    map.setStyle(nlscStyle(layers.baseMap));
    map.once("styledata", () => {
      installOverlays(map);
      applyVessels(map, vesselsRef.current);
      applyLayerVisibility(map, layers);
      applyPorts(map, layers);
      applyAirspace(map, layers);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers.baseMap]);

  // Apply vessel data + layer visibility whenever inputs change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyVessels(map, vessels);
    applyLayerVisibility(map, layers);
    applyPorts(map, layers);
    applyAirspace(map, layers);
  }, [vessels, layers]);

  // Draw the selected track.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const source = map.getSource(TRACK_SOURCE) as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(
      selectedTrack ?? { type: "FeatureCollection", features: [] },
    );
  }, [selectedTrack]);

  // Animation loop: advance visual (interpolated) positions each frame.
  function startAnimation() {
    const step = () => {
      const map = mapRef.current;
      if (map && loadedRef.current) {
        applyVessels(map, vesselsRef.current);
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
  }

  return <div ref={containerRef} className="map-canvas" aria-label="Taiwan maritime map" />;
}

// --- helpers (module scope so the animation loop can reuse them) ------------ //

function installOverlays(map: maplibregl.Map) {
  // Ship icon.
  if (!map.hasImage(SHIP_ICON)) {
    const icon = makeShipIcon();
    if (icon) map.addImage(SHIP_ICON, icon, { pixelRatio: 2 });
  }
  // Vessel source + symbol layer (single source for all vessels).
  if (!map.getSource(VESSEL_SOURCE)) {
    map.addSource(VESSEL_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
  }
  if (!map.getLayer(VESSEL_LAYER)) {
    map.addLayer({
      id: VESSEL_LAYER,
      type: "symbol",
      source: VESSEL_SOURCE,
      layout: {
        "icon-image": SHIP_ICON,
        "icon-size": ["interpolate", ["linear"], ["zoom"], 5, 0.35, 10, 0.7],
        "icon-rotate": ["get", "orientation"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
      },
      paint: {
        // Amber tint when the position is provider-interpolated or visually
        // interpolated; neutral when it's a measured fix at rest.
        "icon-color": [
          "case",
          ["get", "isInterpolated"],
          "#f59e0b",
          "#38bdf8",
        ],
      },
    });
  }
  // Trail.
  if (!map.getSource(TRACK_SOURCE)) {
    map.addSource(TRACK_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
  }
  if (!map.getLayer(TRACK_LAYER)) {
    map.addLayer({
      id: TRACK_LAYER,
      type: "line",
      source: TRACK_SOURCE,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#fbbf24", "line-width": 2.5, "line-opacity": 0.8 },
    });
  }
  // Ports.
  if (!map.getSource(PORT_SOURCE)) {
    map.addSource(PORT_SOURCE, { type: "geojson", data: portsGeoJson() });
  }
  if (!map.getLayer(PORT_LAYER)) {
    map.addLayer({
      id: PORT_LAYER,
      type: "circle",
      source: PORT_SOURCE,
      paint: {
        "circle-radius": 5,
        "circle-color": "#22d3ee",
        "circle-stroke-color": "#04121f",
        "circle-stroke-width": 2,
      },
    });
  }
  if (!map.getLayer(PORT_LABEL)) {
    map.addLayer({
      id: PORT_LABEL,
      type: "symbol",
      source: PORT_SOURCE,
      layout: {
        "text-field": ["get", "nameZh"],
        "text-size": 11,
        "text-offset": [0, 1.2],
        "text-anchor": "top",
      },
      paint: {
        "text-color": "#e2e8f0",
        "text-halo-color": "#04121f",
        "text-halo-width": 1.5,
      },
    });
  }
  // Airspace.
  if (!map.getSource(AIRSPACE_SOURCE)) {
    map.addSource(AIRSPACE_SOURCE, { type: "geojson", data: airspaceGeoJson() });
  }
  if (!map.getLayer(AIRSPACE_FILL)) {
    map.addLayer({
      id: AIRSPACE_FILL,
      type: "fill",
      source: AIRSPACE_SOURCE,
      paint: { "fill-color": "#a855f7", "fill-opacity": 0.08 },
    });
  }
  if (!map.getLayer(AIRSPACE_LINE)) {
    map.addLayer({
      id: AIRSPACE_LINE,
      type: "line",
      source: AIRSPACE_SOURCE,
      paint: { "line-color": "#a855f7", "line-width": 1.5, "line-dasharray": [2, 2] },
    });
  }
}

/** Push vessels onto the single source, computing visual-interpolated positions. */
function applyVessels(map: maplibregl.Map, vessels: LiveVesselFeature[]) {
  const source = map.getSource(VESSEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  const now = Date.now();
  const features = vessels.map((v) => {
    const fix: MeasuredFix = {
      lon: v.geometry.coordinates[0],
      lat: v.geometry.coordinates[1],
      sogKnots: v.properties.sog_knots,
      courseDeg: v.properties.heading_deg ?? v.properties.cog_deg,
      observedAtMs: Date.parse(v.properties.observed_at),
    };
    const projected = projectPosition(fix, now);
    const orientation = v.properties.heading_deg ?? v.properties.cog_deg ?? 0;
    // Interpolated visually (frontend) OR provider-synthesized source position.
    const isInterpolated = projected.interpolated || v.properties.synthesized;
    return {
      type: "Feature" as const,
      id: v.id,
      geometry: { type: "Point" as const, coordinates: [projected.lon, projected.lat] },
      properties: {
        provider_id: v.properties.provider_id,
        orientation,
        isInterpolated,
      },
    };
  });
  source.setData({ type: "FeatureCollection", features });
}

function applyLayerVisibility(map: maplibregl.Map, layers: LayerState) {
  setVisible(map, VESSEL_LAYER, layers.liveVessels);
  setVisible(map, TRACK_LAYER, layers.vesselTracks);
  setVisible(map, PORT_LAYER, layers.ports);
  setVisible(map, PORT_LABEL, layers.ports);
  setVisible(map, AIRSPACE_FILL, layers.restrictedAirspace || layers.publicAirspace);
  setVisible(map, AIRSPACE_LINE, layers.restrictedAirspace || layers.publicAirspace);
}

function applyPorts(map: maplibregl.Map, layers: LayerState) {
  setVisible(map, PORT_LAYER, layers.ports);
  setVisible(map, PORT_LABEL, layers.ports);
}

function applyAirspace(map: maplibregl.Map, layers: LayerState) {
  const on = layers.restrictedAirspace || layers.publicAirspace;
  setVisible(map, AIRSPACE_FILL, on);
  setVisible(map, AIRSPACE_LINE, on);
}

function setVisible(map: maplibregl.Map, layerId: string, visible: boolean) {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
}

function emitViewport(map: maplibregl.Map, cb: (v: Viewport) => void) {
  const b = map.getBounds();
  cb({
    minLat: b.getSouth(),
    minLon: b.getWest(),
    maxLat: b.getNorth(),
    maxLon: b.getEast(),
  });
}

const MAPLIBRE_FALLBACK_STYLE = MAPLIBRE_DEMO_STYLE;
export { MAPLIBRE_FALLBACK_STYLE };

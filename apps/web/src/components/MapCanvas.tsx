import { useEffect, useRef, useState } from "react";
import maplibregl, { type LayerSpecification, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { LiveVesselFeature, OperatingMode } from "../api/live";
import type { LayerState } from "../lib/layerState";
import {
  TAIWAN_CENTER,
  TAIWAN_ZOOM,
  airspaceGeoJson,
  nlscStyle,
  portsGeoJson,
} from "../config/taiwanMap";
import {
  emergencyStyle,
  pmtilesStyle,
  registerPmtilesProtocol,
  selectOfflineBasemap,
  type BasemapStage,
  type OnlineFailureState,
} from "../config/offlineMap";
import { projectPosition, type MeasuredFix } from "../lib/interpolation";
import { normalizeOrientation } from "../lib/orientation";
import { makeShipIcon } from "../lib/shipIcon";
import type { AreaDrawMode } from "./AreaScanPanel";

export interface Viewport {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

interface MapCanvasProps {
  vessels: LiveVesselFeature[];
  layers: LayerState;
  selectedId: string | null;
  selectedSource?: "live" | "datalastic" | null;
  selectedTrack: GeoJSON.Feature | null;
  follow: boolean;
  /** Fit the map to these [west,south,east,north] bounds (preset navigation). */
  fitBounds?: [number, number, number, number] | null;
  /** Nonce bumped by the caller to re-trigger the same fitBounds. */
  fitBoundsNonce?: number;
  onSelectVessel: (
    feature: LiveVesselFeature,
    source?: "live" | "datalastic",
  ) => void;
  onDeselect: () => void;
  onViewportChange: (viewport: Viewport) => void;
  /** Fired when the user manually pans/zooms, so follow mode can pause. */
  onUserInteract?: () => void;
  onBaseMapError?: (message: string | null) => void;
  operatingMode?: OperatingMode;
  areaDrawMode?: AreaDrawMode;
  areaGeometry?: GeoJSON.Polygon | null;
  areaVessels?: LiveVesselFeature[];
  onAreaGeometryChange?: (geometry: GeoJSON.Polygon) => void;
  /**
   * Optional, generic GeoJSON overlay layer groups rendered ABOVE the built-in
   * overlays. This is a logistics-agnostic seam: the caller supplies named
   * GeoJSON sources and MapLibre layer specs; MapCanvas installs them and
   * re-installs them after every style/basemap change (NLSC → PMTiles →
   * emergency). ``undefined``/``null`` preserves exactly the current behavior
   * (no extra sources or layers are touched). MapCanvas holds no knowledge of
   * what the overlay represents.
   */
  overlays?: MapOverlays | null;
}

/** Generic overlay payload: named GeoJSON sources + MapLibre layer specs. */
export interface MapOverlays {
  sources: Record<string, GeoJSON.FeatureCollection>;
  layers: LayerSpecification[];
}

const VESSEL_SOURCE = "live-vessels";
const VESSEL_LAYER = "live-vessels-symbols";
const VESSEL_DOT_LAYER = "live-vessels-dot";
const HALO_LAYER = "live-vessels-halo";
const TRACK_SOURCE = "selected-track";
const TRACK_LAYER = "selected-track-line";
const PORT_SOURCE = "ports";
const PORT_LAYER = "ports-circle";
const PORT_LABEL = "ports-label";
const AIRSPACE_SOURCE = "airspace";
const AIRSPACE_FILL = "airspace-fill";
const AIRSPACE_LINE = "airspace-line";
const SHIP_ICON = "ship-icon";
const AREA_GEOMETRY_SOURCE = "area-scan-geometry";
const AREA_FILL_LAYER = "area-scan-fill";
const AREA_LINE_LAYER = "area-scan-line";
const AREA_VESSEL_SOURCE = "area-scan-vessels";
const AREA_VESSEL_LAYER = "area-scan-vessels-dot";

// Both vessel layers are interactive; the dot always renders, the symbol may
// not until the raster style is loaded.
const VESSEL_INTERACTIVE_LAYERS = [VESSEL_LAYER, VESSEL_DOT_LAYER];
const ALL_VESSEL_INTERACTIVE_LAYERS = [...VESSEL_INTERACTIVE_LAYERS, AREA_VESSEL_LAYER];

const FOLLOW_ZOOM = 11;

/**
 * The product map. All live vessels render through ONE GeoJSON source + a halo
 * circle layer and a symbol layer (no DOM element per vessel). The selected
 * vessel is styled via MapLibre feature-state ("selected") so selection changes
 * never rebuild the source. Motion is smoothed on the client via visual
 * interpolation between real fixes; the selected vessel can be followed.
 */
export function MapCanvas({
  vessels,
  layers,
  selectedId,
  selectedSource = null,
  selectedTrack,
  follow,
  fitBounds,
  fitBoundsNonce,
  onSelectVessel,
  onDeselect,
  onViewportChange,
  onUserInteract,
  onBaseMapError,
  operatingMode = "CLOUD_LIVE",
  areaDrawMode = null,
  areaGeometry = null,
  areaVessels = [],
  onAreaGeometryChange,
  overlays = null,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const vesselsRef = useRef<LiveVesselFeature[]>([]);
  const rafRef = useRef<number | null>(null);
  const currentBaseRef = useRef<string>(layers.baseMap);
  const selectedIdRef = useRef<string | null>(selectedId);
  const selectedSourceRef = useRef<"live" | "datalastic" | null>(selectedSource);
  const followRef = useRef<boolean>(follow);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const programmaticMoveRef = useRef(false);
  const failureRef = useRef<OnlineFailureState>("healthy");
  const operatingModeRef = useRef(operatingMode);
  const overlaysRef = useRef<MapOverlays | null>(overlays);
  const areaDrawModeRef = useRef<AreaDrawMode>(areaDrawMode);
  const areaGeometryRef = useRef<GeoJSON.Polygon | null>(areaGeometry);
  const areaVesselsRef = useRef<LiveVesselFeature[]>(areaVessels);
  const onAreaGeometryChangeRef = useRef(onAreaGeometryChange);
  const polygonDraftRef = useRef<Array<[number, number]>>([]);
  const rectangleStartRef = useRef<[number, number] | null>(null);
  const initialStage = selectOfflineBasemap(operatingMode, "healthy");
  const stageRef = useRef<BasemapStage>(initialStage);
  const [basemapStage, setBasemapStage] = useState<BasemapStage>(initialStage);

  // Keep latest props in refs for the animation loop and event handlers.
  vesselsRef.current = vessels;
  selectedIdRef.current = selectedId;
  selectedSourceRef.current = selectedSource;
  followRef.current = follow;
  operatingModeRef.current = operatingMode;
  overlaysRef.current = overlays;
  areaDrawModeRef.current = areaDrawMode;
  areaGeometryRef.current = areaGeometry;
  areaVesselsRef.current = areaVessels;
  onAreaGeometryChangeRef.current = onAreaGeometryChange;

  // Initialize the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    registerPmtilesProtocol();
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleForStage(stageRef.current, layers.baseMap),
      center: TAIWAN_CENTER,
      zoom: TAIWAN_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("error", (e) => {
      const msg = (e?.error && (e.error as Error).message) || "";
      const basemapFailed =
        stageRef.current === "pmtiles" || /tile|source|network|fetch|response code/i.test(msg);
      if (msg && stageRef.current !== "emergency" && basemapFailed) {
        onBaseMapError?.(msg);
        const nextFailure =
          stageRef.current === "nlsc"
            ? "nlsc_failed"
            : stageRef.current === "pmtiles"
              ? "pmtiles_failed"
              : failureRef.current;
        const nextStage = selectOfflineBasemap(operatingModeRef.current, nextFailure);
        if (nextStage !== stageRef.current) {
          failureRef.current = nextFailure;
          stageRef.current = nextStage;
          setBasemapStage(nextStage);
          map.setStyle(styleForStage(nextStage, layers.baseMap));
          map.once("styledata", () =>
            restoreOverlays(
              map,
              layers,
              vesselsRef.current,
              selectedIdRef.current,
              selectedSourceRef.current,
              areaGeometryRef.current,
              areaVesselsRef.current,
              overlaysRef.current,
            ),
          );
        }
      }
    });

    map.on("load", () => {
      loadedRef.current = true;
      installOverlays(map, overlaysRef.current);
      applyVessels(
        map,
        vesselsRef.current,
        selectedIdRef.current,
        selectedSourceRef.current,
      );
      applyAreaGeometry(map, areaGeometryRef.current);
      applyAreaVessels(
        map,
        areaVesselsRef.current,
        selectedIdRef.current,
        selectedSourceRef.current,
      );
      applyLayerVisibility(map, layers, selectedIdRef.current);
      applyPorts(map, layers);
      applyAirspace(map, layers);
      emitViewport(map, onViewportChange);
    });

    map.on("moveend", () => emitViewport(map, onViewportChange));

    // Manual pan/zoom -> pause follow mode. Programmatic moves (flyTo/follow)
    // set a flag so they don't count as user interaction.
    map.on("dragstart", () => onUserInteract?.());
    map.on("zoomstart", () => {
      if (!programmaticMoveRef.current) onUserInteract?.();
    });

    // Click a vessel (symbol or dot) -> select it. The dot layer always renders;
    // the symbol may not until the raster style is loaded, so both are targeted.
    map.on("click", VESSEL_INTERACTIVE_LAYERS, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const match = vesselsRef.current.find((v) => v.id === feature.id);
      if (match) onSelectVessel(match, "live");
    });
    map.on("click", AREA_VESSEL_LAYER, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const match = areaVesselsRef.current.find((v) => v.id === feature.id);
      if (match) onSelectVessel(match, "datalastic");
    });

    // Polygon drawing is local-only until the user explicitly presses Scan.
    // Coordinates are always GeoJSON longitude-latitude order.
    map.on("click", (e) => {
      if (areaDrawModeRef.current === "polygon") {
        polygonDraftRef.current.push([e.lngLat.lng, e.lngLat.lat]);
        if (polygonDraftRef.current.length >= 3) {
          applyAreaGeometry(map, polygonFromPoints(polygonDraftRef.current));
        }
        return;
      }
      if (areaDrawModeRef.current !== null) return;
      const hits = map.queryRenderedFeatures(e.point, {
        layers: existingLayers(map, ALL_VESSEL_INTERACTIVE_LAYERS),
      });
      if (hits.length === 0) onDeselect();
    });

    map.on("dblclick", (e) => {
      if (areaDrawModeRef.current !== "polygon") return;
      e.preventDefault?.();
      if (polygonDraftRef.current.length < 3) return;
      const geometry = polygonFromPoints(polygonDraftRef.current);
      polygonDraftRef.current = [];
      applyAreaGeometry(map, geometry);
      onAreaGeometryChangeRef.current?.(geometry);
    });

    map.on("mousedown", (e) => {
      if (areaDrawModeRef.current !== "rectangle") return;
      rectangleStartRef.current = [e.lngLat.lng, e.lngLat.lat];
      map.dragPan.disable();
    });
    map.on("mousemove", (e) => {
      const start = rectangleStartRef.current;
      if (areaDrawModeRef.current !== "rectangle" || !start) return;
      applyAreaGeometry(map, rectangleFromCorners(start, [e.lngLat.lng, e.lngLat.lat]));
    });
    map.on("mouseup", (e) => {
      const start = rectangleStartRef.current;
      if (areaDrawModeRef.current !== "rectangle" || !start) return;
      const geometry = rectangleFromCorners(start, [e.lngLat.lng, e.lngLat.lat]);
      rectangleStartRef.current = null;
      map.dragPan.enable();
      applyAreaGeometry(map, geometry);
      onAreaGeometryChangeRef.current?.(geometry);
    });

    const cancelDrawing = () => {
      polygonDraftRef.current = [];
      rectangleStartRef.current = null;
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      applyAreaGeometry(map, areaGeometryRef.current);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelDrawing();
    };
    const onPointerUp = () => {
      if (rectangleStartRef.current !== null) cancelDrawing();
    };
    window.addEventListener("keydown", onEscape);
    window.addEventListener("pointerup", onPointerUp);

    // Hover tooltip (desktop) — lightweight, does not open the panel.
    map.on("mousemove", ALL_VESSEL_INTERACTIVE_LAYERS, (e) => {
      map.getCanvas().style.cursor = "pointer";
      const feature = e.features?.[0];
      if (!feature) return;
      const sourceVessels = feature.source === AREA_VESSEL_SOURCE
        ? areaVesselsRef.current
        : vesselsRef.current;
      const match = sourceVessels.find((v) => v.id === feature.id);
      if (!match) return;
      showHoverPopup(map, popupRef, match, e.lngLat);
    });
    map.on("mouseleave", ALL_VESSEL_INTERACTIVE_LAYERS, () => {
      map.getCanvas().style.cursor = "";
      popupRef.current?.remove();
    });

    mapRef.current = map;
    startAnimation();

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      loadedRef.current = false;
      popupRef.current?.remove();
      window.removeEventListener("keydown", onEscape);
      window.removeEventListener("pointerup", onPointerUp);
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Edge/no-source operation starts locally and never retries a latched remote
  // source. Cloud mode always selects NLSC and handles tile failures in place.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const nextStage = selectOfflineBasemap(operatingMode, failureRef.current);
    if (nextStage === stageRef.current) return;
    stageRef.current = nextStage;
    setBasemapStage(nextStage);
    map.setStyle(styleForStage(nextStage, layers.baseMap));
    map.once("styledata", () =>
      restoreOverlays(
        map,
        layers,
        vesselsRef.current,
        selectedIdRef.current,
        selectedSourceRef.current,
        areaGeometryRef.current,
        areaVesselsRef.current,
        overlaysRef.current,
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operatingMode]);

  // Switch base map when it changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (stageRef.current !== "nlsc") return;
    if (currentBaseRef.current === layers.baseMap) return;
    currentBaseRef.current = layers.baseMap;
    onBaseMapError?.(null);
    map.setStyle(nlscStyle(layers.baseMap));
    map.once("styledata", () => {
      installOverlays(map, overlaysRef.current);
      applyVessels(map, vesselsRef.current, selectedIdRef.current, selectedSourceRef.current);
      applyAreaGeometry(map, areaGeometryRef.current);
      applyAreaVessels(
        map,
        areaVesselsRef.current,
        selectedIdRef.current,
        selectedSourceRef.current,
      );
      applyLayerVisibility(map, layers, selectedIdRef.current);
      applyPorts(map, layers);
      applyAirspace(map, layers);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers.baseMap]);

  // Apply vessel data + layer visibility whenever inputs change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyVessels(map, vessels, selectedId, selectedSource);
    applyLayerVisibility(map, layers, selectedId);
    applyPorts(map, layers);
    applyAirspace(map, layers);
  }, [vessels, layers, selectedId, selectedSource]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyAreaGeometry(map, areaGeometry);
    applyAreaVessels(map, areaVessels, selectedId, selectedSource);
  }, [areaGeometry, areaVessels, selectedId, selectedSource]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    polygonDraftRef.current = [];
    rectangleStartRef.current = null;
    if (areaDrawMode === "polygon") map.doubleClickZoom.disable();
    else map.doubleClickZoom.enable();
    if (areaDrawMode !== "rectangle") map.dragPan.enable();
  }, [areaDrawMode]);

  // Install/refresh generic caller overlays when they change. Null preserves
  // current behavior (nothing extra is touched).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    installGenericOverlays(map, overlays);
  }, [overlays]);

  // Update selected feature-state (never rebuilds the source).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applySelectedState(
      map,
      vesselsRef.current,
      selectedId,
      areaVesselsRef.current,
      selectedSource,
    );
  }, [selectedId, selectedSource]);

  // Fly to the newly selected vessel.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current || !selectedId) return;
    const selectedVessels =
      selectedSource === "datalastic" ? areaVesselsRef.current : vesselsRef.current;
    const match = selectedVessels.find((v) => v.id === selectedId);
    if (!match) return;
    programmaticMoveRef.current = true;
    map.flyTo({
      center: match.geometry.coordinates,
      // Zoom to a useful maritime detail level (10–12) without overzooming.
      zoom: Math.min(12, Math.max(map.getZoom(), FOLLOW_ZOOM)),
      duration: 900,
      essential: true,
    });
    map.once("moveend", () => {
      programmaticMoveRef.current = false;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selectedSource]);

  // Fit to a preset region (quick-location navigation).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current || !fitBounds) return;
    programmaticMoveRef.current = true;
    map.fitBounds(
      [
        [fitBounds[0], fitBounds[1]],
        [fitBounds[2], fitBounds[3]],
      ],
      { padding: 40, duration: 900, maxZoom: 12 },
    );
    map.once("moveend", () => {
      programmaticMoveRef.current = false;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitBoundsNonce]);

  // Draw the selected track.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const source = map.getSource(TRACK_SOURCE) as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(selectedTrack ?? { type: "FeatureCollection", features: [] });
  }, [selectedTrack]);

  // Animation loop: advance visual (interpolated) positions each frame, and
  // keep following the selected vessel when follow mode is on.
  function startAnimation() {
    const step = () => {
      const map = mapRef.current;
      if (map && loadedRef.current) {
        applyVessels(
          map,
          vesselsRef.current,
          selectedIdRef.current,
          selectedSourceRef.current,
        );
        applyAreaVessels(
          map,
          areaVesselsRef.current,
          selectedIdRef.current,
          selectedSourceRef.current,
        );
        maybeFollow(
          map,
          selectedSourceRef.current === "datalastic"
            ? areaVesselsRef.current
            : vesselsRef.current,
          selectedIdRef.current,
          followRef,
          programmaticMoveRef,
        );
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
  }

  return (
    <div
      ref={containerRef}
      className="map-canvas"
      data-basemap-stage={basemapStage}
      aria-label="Taiwan maritime map"
    />
  );
}

// --- helpers (module scope so the animation loop can reuse them) ------------ //

function installOverlays(map: maplibregl.Map, overlays?: MapOverlays | null) {
  if (!map.hasImage(SHIP_ICON)) {
    const icon = makeShipIcon();
    // Register as SDF so the symbol layer's data-driven icon-color is valid.
    if (icon) map.addImage(SHIP_ICON, icon, { pixelRatio: 2, sdf: true });
  }
  if (!map.getSource(VESSEL_SOURCE)) {
    map.addSource(VESSEL_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
      promoteId: "fid",
    });
  }
  // Halo under the selected vessel for immediate visibility.
  if (!map.getLayer(HALO_LAYER)) {
    map.addLayer({
      id: HALO_LAYER,
      type: "circle",
      source: VESSEL_SOURCE,
      paint: {
        "circle-radius": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          16,
          0,
        ],
        "circle-color": "#38bdf8",
        "circle-opacity": 0.25,
        "circle-stroke-color": "#38bdf8",
        "circle-stroke-width": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          2,
          0,
        ],
        "circle-stroke-opacity": 0.9,
      },
    });
  }
  // Primary vessel marker: a CIRCLE layer. Unlike a symbol/icon layer, a circle
  // layer commits to the render pipeline even when the raster basemap style has
  // not reached isStyleLoaded() (NLSC tiles can stall / be CORS-blocked). This
  // guarantees vessels are ALWAYS visible; the directional ship symbol is drawn
  // on top of it when the sprite path is ready. Runtime diagnosis proved the
  // symbol-only layer silently failed to render while circles on the same
  // source rendered thousands of features.
  if (!map.getLayer(VESSEL_DOT_LAYER)) {
    map.addLayer({
      id: VESSEL_DOT_LAYER,
      type: "circle",
      source: VESSEL_SOURCE,
      paint: {
        // Smaller at national overview (declutter), larger when closer. NOTE:
        // MapLibre silently rejects a layer whose "circle-radius" nests an
        // "interpolate" inside a "case" — keep this a PLAIN zoom interpolate.
        // Selected-vessel emphasis is provided by the halo + larger ship symbol.
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 1.8, 8, 2.6, 11, 3.4],
        "circle-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          "#fde68a",
          ["==", ["get", "displayState"], "stale"],
          "#f59e0b",
          ["==", ["get", "displayState"], "cached"],
          "#67e8f9",
          ["get", "isInterpolated"],
          "#f59e0b",
          "#38bdf8",
        ],
        // The directional ship symbol takes over at closer zoom; fade the dot
        // out there. Plain zoom interpolate (no "case" wrapper — see above).
        "circle-opacity": ["interpolate", ["linear"], ["zoom"], 8.5, 0.95, 10.5, 0.35],
        "circle-stroke-color": "#04121f",
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 10, 1],
      },
    });
  }
  if (!map.getLayer(VESSEL_LAYER)) {
    map.addLayer({
      id: VESSEL_LAYER,
      type: "symbol",
      source: VESSEL_SOURCE,
      layout: {
        "icon-image": SHIP_ICON,
        // Directional ship grows with zoom; kept modest so thousands of vessels
        // never become giant icons. PLAIN zoom interpolate (do not nest inside a
        // "case" — MapLibre silently drops such layers). Selected emphasis comes
        // from the halo + the dot colour.
        "icon-size": ["interpolate", ["linear"], ["zoom"], 6, 0.18, 9, 0.32, 12, 0.55],
        "icon-rotate": ["get", "orientation"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
        "symbol-z-order": "source",
      },
      paint: {
        "icon-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          "#fde68a",
          ["get", "isInterpolated"],
          "#f59e0b",
          "#38bdf8",
        ],
        // Fade the directional icon in as we zoom past the overview level so the
        // national view stays as light dots (declutter), ships appear closer in.
        // PLAIN zoom interpolate (no "case" wrapper).
        "icon-opacity": ["interpolate", ["linear"], ["zoom"], 7.5, 0, 9.5, 1],
        "icon-halo-color": "#04121f",
        "icon-halo-width": 1,
      },
    });
  }
  if (!map.getSource(TRACK_SOURCE)) {
    map.addSource(TRACK_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
      lineMetrics: true,
    });
  }
  if (!map.getLayer(TRACK_LAYER)) {
    map.addLayer(
      {
        id: TRACK_LAYER,
        type: "line",
        source: TRACK_SOURCE,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-width": 3,
          // Older (start) more transparent -> recent (end) stronger.
          "line-gradient": [
            "interpolate",
            ["linear"],
            ["line-progress"],
            0,
            "rgba(251,191,36,0.15)",
            1,
            "rgba(251,191,36,0.95)",
          ],
        },
      },
      HALO_LAYER,
    );
  }
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
  if (!map.getSource(AREA_GEOMETRY_SOURCE)) {
    map.addSource(AREA_GEOMETRY_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
  }
  if (!map.getLayer(AREA_FILL_LAYER)) {
    map.addLayer({
      id: AREA_FILL_LAYER,
      type: "fill",
      source: AREA_GEOMETRY_SOURCE,
      paint: { "fill-color": "#f59e0b", "fill-opacity": 0.14 },
    });
  }
  if (!map.getLayer(AREA_LINE_LAYER)) {
    map.addLayer({
      id: AREA_LINE_LAYER,
      type: "line",
      source: AREA_GEOMETRY_SOURCE,
      paint: { "line-color": "#fbbf24", "line-width": 2.5 },
    });
  }
  if (!map.getSource(AREA_VESSEL_SOURCE)) {
    map.addSource(AREA_VESSEL_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
      promoteId: "fid",
    });
  }
  if (!map.getLayer(AREA_VESSEL_LAYER)) {
    map.addLayer({
      id: AREA_VESSEL_LAYER,
      type: "circle",
      source: AREA_VESSEL_SOURCE,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 4.5, 10, 7],
        "circle-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          "#fde68a",
          "#f59e0b",
        ],
        "circle-opacity": 0.95,
        "circle-stroke-color": "#fff7ed",
        "circle-stroke-width": 2,
      },
    });
  }
  // Generic, caller-provided overlays (logistics-agnostic). Installed last so
  // they render above the built-in layers, and re-installed on every style
  // change via restoreOverlays. Idempotent: existing sources are updated via
  // setData and existing layers are not re-added (no duplicate registration).
  installGenericOverlays(map, overlays);
}

/** Install/refresh generic caller overlays without duplicating registrations. */
function installGenericOverlays(map: maplibregl.Map, overlays?: MapOverlays | null) {
  if (!overlays) return;
  for (const [sourceId, data] of Object.entries(overlays.sources)) {
    const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(data);
    } else {
      map.addSource(sourceId, { type: "geojson", data });
    }
  }
  for (const layer of overlays.layers) {
    if (!map.getLayer(layer.id)) {
      map.addLayer(layer);
    }
  }
}

function styleForStage(stage: BasemapStage, baseMap: LayerState["baseMap"]): StyleSpecification {
  if (stage === "pmtiles") return pmtilesStyle();
  if (stage === "emergency") return emergencyStyle();
  return nlscStyle(baseMap);
}

function restoreOverlays(
  map: maplibregl.Map,
  layers: LayerState,
  vessels: LiveVesselFeature[],
  selectedId: string | null,
  selectedSource: "live" | "datalastic" | null,
  areaGeometry: GeoJSON.Polygon | null,
  areaVessels: LiveVesselFeature[],
  overlays?: MapOverlays | null,
) {
  installOverlays(map, overlays);
  applyVessels(map, vessels, selectedId, selectedSource);
  applyAreaGeometry(map, areaGeometry);
  applyAreaVessels(map, areaVessels, selectedId, selectedSource);
  applyLayerVisibility(map, layers, selectedId);
  applyPorts(map, layers);
  applyAirspace(map, layers);
}

/** Push vessels onto the single source, computing visual-interpolated positions. */
function applyVessels(
  map: maplibregl.Map,
  vessels: LiveVesselFeature[],
  selectedId: string | null,
  selectedSource: "live" | "datalastic" | null,
) {
  const source = map.getSource(VESSEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  const now = Date.now();
  const features = vessels.map((v) => {
    const course = normalizeOrientation(v.properties.heading_deg, v.properties.cog_deg);
    const fix: MeasuredFix = {
      lon: v.geometry.coordinates[0],
      lat: v.geometry.coordinates[1],
      sogKnots: v.properties.sog_knots,
      courseDeg: course,
      observedAtMs: Date.parse(v.properties.observed_at ?? ""),
    };
    const projected = projectPosition(fix, now);
    const isInterpolated = projected.interpolated || v.properties.synthesized;
    return {
      type: "Feature" as const,
      id: v.id,
      geometry: { type: "Point" as const, coordinates: [projected.lon, projected.lat] },
      properties: {
        fid: v.id,
        provider_id: v.properties.provider_id,
        orientation: course ?? 0,
        isInterpolated,
        displayState: v.properties.display_state ?? "live",
      },
    };
  });
  source.setData({ type: "FeatureCollection", features });
  applySelectedState(map, vessels, selectedId, [], selectedSource);
}

function applyAreaGeometry(map: maplibregl.Map, geometry: GeoJSON.Polygon | null) {
  const source = map.getSource(AREA_GEOMETRY_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  source.setData(
    geometry
      ? { type: "Feature", geometry, properties: {} }
      : { type: "FeatureCollection", features: [] },
  );
}

function applyAreaVessels(
  map: maplibregl.Map,
  vessels: LiveVesselFeature[],
  selectedId: string | null,
  selectedSource: "live" | "datalastic" | null,
) {
  const source = map.getSource(AREA_VESSEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  source.setData({
    type: "FeatureCollection",
    features: vessels.map((v) => ({
      ...v,
      properties: { ...v.properties, fid: v.id },
    })),
  });
  applySelectedState(map, [], selectedId, vessels, selectedSource);
}

/** Set the "selected" feature-state on the active vessel, clearing others. */
function applySelectedState(
  map: maplibregl.Map,
  vessels: LiveVesselFeature[],
  selectedId: string | null,
  areaVessels: LiveVesselFeature[] = [],
  selectedSource: "live" | "datalastic" | null = null,
) {
  for (const [source, sourceVessels] of [
    [VESSEL_SOURCE, vessels],
    [AREA_VESSEL_SOURCE, areaVessels],
  ] as const) {
    if (!map.getSource(source)) continue;
    for (const v of sourceVessels) {
      try {
        map.setFeatureState(
          { source, id: v.id },
          {
            selected:
              selectedId !== null &&
              v.id === selectedId &&
              (source === AREA_VESSEL_SOURCE
                ? selectedSource === "datalastic"
                : selectedSource !== "datalastic"),
          },
        );
      } catch {
        // Feature not yet in the tile index; ignore.
      }
    }
  }
}

function polygonFromPoints(points: Array<[number, number]>): GeoJSON.Polygon {
  return { type: "Polygon", coordinates: [[...points, points[0]]] };
}

function rectangleFromCorners(
  start: [number, number],
  end: [number, number],
): GeoJSON.Polygon {
  return {
    type: "Polygon",
    coordinates: [[
      [start[0], start[1]],
      [end[0], start[1]],
      [end[0], end[1]],
      [start[0], end[1]],
      [start[0], start[1]],
    ]],
  };
}

/** Smoothly keep the map centered on the selected vessel while following. */
function maybeFollow(
  map: maplibregl.Map,
  vessels: LiveVesselFeature[],
  selectedId: string | null,
  followRef: React.MutableRefObject<boolean>,
  programmaticMoveRef: React.MutableRefObject<boolean>,
) {
  if (!followRef.current || !selectedId) return;
  const match = vessels.find((v) => v.id === selectedId);
  if (!match) return;
  const now = Date.now();
  const course = normalizeOrientation(match.properties.heading_deg, match.properties.cog_deg);
  const projected = match.properties.freshness_state === "stale"
    || match.properties.freshness_state === "unknown"
    ? {
        lon: match.geometry.coordinates[0],
        lat: match.geometry.coordinates[1],
      }
    : projectPosition(
        {
          lon: match.geometry.coordinates[0],
          lat: match.geometry.coordinates[1],
          sogKnots: match.properties.sog_knots,
          courseDeg: course,
          observedAtMs: Date.parse(match.properties.observed_at ?? ""),
        },
        now,
      );
  const center = map.getCenter();
  const dLon = Math.abs(center.lng - projected.lon);
  const dLat = Math.abs(center.lat - projected.lat);
  // Only re-center when drift is meaningful (avoid re-centering every frame).
  if (dLon < 0.0005 && dLat < 0.0005) return;
  programmaticMoveRef.current = true;
  map.easeTo({ center: [projected.lon, projected.lat], duration: 500 });
}

function showHoverPopup(
  map: maplibregl.Map,
  popupRef: React.MutableRefObject<maplibregl.Popup | null>,
  v: LiveVesselFeature,
  lngLat: maplibregl.LngLat,
) {
  const name = v.properties.name || "—";
  const sog = v.properties.sog_knots === null ? "—" : `${v.properties.sog_knots.toFixed(1)} kn`;
  const course = normalizeOrientation(v.properties.heading_deg, v.properties.cog_deg);
  const courseStr = course === null ? "—" : `${Math.round(course)}°`;
  const age = v.properties.data_age_seconds === null
    ? "—"
    : `${Math.round(v.properties.data_age_seconds)}s`;
  const html = `<div class="vessel-tooltip"><strong>${escapeHtml(name)}</strong><br/>${sog} · ${courseStr} · ${age}</div>`;
  if (!popupRef.current) {
    popupRef.current = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      className: "vessel-popup",
    });
  }
  popupRef.current.setLngLat(lngLat).setHTML(html).addTo(map);
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );
}

function applyLayerVisibility(map: maplibregl.Map, layers: LayerState, selectedId: string | null) {
  setVisible(map, VESSEL_LAYER, layers.liveVessels);
  setVisible(map, VESSEL_DOT_LAYER, layers.liveVessels);
  setVisible(map, HALO_LAYER, layers.liveVessels);
  // Trails are off by default, but the selected vessel's trail is always shown.
  setVisible(map, TRACK_LAYER, layers.vesselTracks || selectedId !== null);
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

/** Filter a layer-id list to those that currently exist in the style. */
function existingLayers(map: maplibregl.Map, ids: string[]): string[] {
  return ids.filter((id) => map.getLayer(id));
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

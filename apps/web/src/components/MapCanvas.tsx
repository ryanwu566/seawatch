import { useEffect, useRef, useState } from "react";
import maplibregl, {
  type ExpressionSpecification,
  type LayerSpecification,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { LiveVesselFeature, OperatingMode } from "../api/live";
import type { LayerState } from "../lib/layerState";
import {
  TAIWAN_CENTER,
  TAIWAN_ZOOM,
  airspaceGeoJson,
  onlineStyle,
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
import {
  MARITIME_REFERENCE_LAYER_IDS,
  MARITIME_REFERENCE_SOURCES,
  isMaritimeReferenceSourceId,
  maritimeReferenceUrl,
} from "../config/maritimeReference";
import { projectPosition, type MeasuredFix } from "../lib/interpolation";
import { normalizeOrientation } from "../lib/orientation";
import { makeShipIcon } from "../lib/shipIcon";
import { VESSEL_CATEGORY_COLORS, categoryForVessel } from "../lib/vesselCategory";
import { finalizePolygonPoints } from "../lib/areaGeometry";
import {
  HISTORICAL_TRAFFIC_FILL_LAYER_ID,
  HISTORICAL_TRAFFIC_SOURCE_ID,
  formatHistoricalTrafficPopup,
  installHistoricalTrafficLayers,
  setHistoricalTrafficVisibility,
  type HistoricalTrafficFeatureCollection,
  type HistoricalTrafficProperties,
} from "../lib/historicalTraffic";
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
  /** Whether remote vector tiles should precede the offline fallback chain. */
  onlineBasemap?: boolean;
  areaDrawMode?: AreaDrawMode;
  areaGeometry?: GeoJSON.Polygon | null;
  areaVessels?: LiveVesselFeature[];
  onAreaGeometryChange?: (geometry: GeoJSON.Polygon) => void;
  onAreaGeometryInvalid?: () => void;
  historicalTraffic?: HistoricalTrafficFeatureCollection | null;
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
const AREA_DRAFT_PATH_SOURCE = "area-scan-draft-path";
const AREA_DRAFT_PATH_LAYER = "area-scan-draft-path";
const AREA_DRAFT_VERTEX_SOURCE = "area-scan-draft-vertices";
const AREA_DRAFT_VERTEX_LAYER = "area-scan-draft-vertices";
const AREA_VESSEL_SOURCE = "area-scan-vessels";
const AREA_VESSEL_LAYER = "area-scan-vessels-symbols";
const AREA_VESSEL_HALO_LAYER = "area-scan-vessels-halo";
const POLYGON_CLOSE_TOLERANCE_PX = 12;

const VESSEL_INTERACTIVE_LAYERS = [VESSEL_LAYER];
const ALL_VESSEL_INTERACTIVE_LAYERS = [...VESSEL_INTERACTIVE_LAYERS, AREA_VESSEL_LAYER];

const FOLLOW_ZOOM = 11;

const MARITIME_REFERENCE_LAYER_SPECS: LayerSpecification[] = [
  {
    id: MARITIME_REFERENCE_LAYER_IDS.eez.fill,
    type: "fill",
    source: "seawatch-eez-reference",
    paint: { "fill-color": "#38bdf8", "fill-opacity": 0.05 },
  },
  {
    id: MARITIME_REFERENCE_LAYER_IDS.contiguousZone24Nm.fill,
    type: "fill",
    source: "seawatch-contiguous-zone-24nm",
    paint: { "fill-color": "#f59e0b", "fill-opacity": 0.055 },
  },
  {
    id: MARITIME_REFERENCE_LAYER_IDS.territorialSea12Nm.fill,
    type: "fill",
    source: "seawatch-territorial-sea-12nm",
    paint: { "fill-color": "#2dd4bf", "fill-opacity": 0.075 },
  },
  {
    id: MARITIME_REFERENCE_LAYER_IDS.eez.line,
    type: "line",
    source: "seawatch-eez-reference",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#38bdf8", "line-opacity": 0.72, "line-width": 1.2 },
  },
  {
    id: MARITIME_REFERENCE_LAYER_IDS.contiguousZone24Nm.line,
    type: "line",
    source: "seawatch-contiguous-zone-24nm",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": "#fbbf24",
      "line-opacity": 0.88,
      "line-width": 1.5,
      "line-dasharray": [2, 1.5],
    },
  },
  {
    id: MARITIME_REFERENCE_LAYER_IDS.territorialSea12Nm.line,
    type: "line",
    source: "seawatch-territorial-sea-12nm",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#5eead4", "line-opacity": 0.92, "line-width": 1.8 },
  },
];

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
  onlineBasemap,
  areaDrawMode = null,
  areaGeometry = null,
  areaVessels = [],
  onAreaGeometryChange,
  onAreaGeometryInvalid,
  historicalTraffic = null,
  overlays = null,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const vesselsRef = useRef<LiveVesselFeature[]>([]);
  const rafRef = useRef<number | null>(null);
  const currentBaseRef = useRef<string>(layers.baseMap);
  const layersRef = useRef<LayerState>(layers);
  const selectedIdRef = useRef<string | null>(selectedId);
  const selectedSourceRef = useRef<"live" | "datalastic" | null>(selectedSource);
  const followRef = useRef<boolean>(follow);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const programmaticMoveRef = useRef(false);
  const failureRef = useRef<OnlineFailureState>("healthy");
  const onlineBasemapRef = useRef(
    onlineBasemap ?? operatingMode === "CLOUD_LIVE",
  );
  const overlaysRef = useRef<MapOverlays | null>(overlays);
  const historicalTrafficRef = useRef<HistoricalTrafficFeatureCollection | null>(
    historicalTraffic,
  );
  const areaDrawModeRef = useRef<AreaDrawMode>(areaDrawMode);
  const areaGeometryRef = useRef<GeoJSON.Polygon | null>(areaGeometry);
  const areaVesselsRef = useRef<LiveVesselFeature[]>(areaVessels);
  const onAreaGeometryChangeRef = useRef(onAreaGeometryChange);
  const onAreaGeometryInvalidRef = useRef(onAreaGeometryInvalid);
  const polygonDraftRef = useRef<Array<[number, number]>>([]);
  const rectangleStartRef = useRef<[number, number] | null>(null);
  const rectanglePointerIdRef = useRef<number | null>(null);
  const prefersOnlineBasemap = onlineBasemap ?? operatingMode === "CLOUD_LIVE";
  const initialStage = selectOfflineBasemap(prefersOnlineBasemap, "healthy");
  const stageRef = useRef<BasemapStage>(initialStage);
  const [basemapStage, setBasemapStage] = useState<BasemapStage>(initialStage);

  // Keep latest props in refs for the animation loop and event handlers.
  vesselsRef.current = vessels;
  layersRef.current = layers;
  selectedIdRef.current = selectedId;
  selectedSourceRef.current = selectedSource;
  followRef.current = follow;
  onlineBasemapRef.current = prefersOnlineBasemap;
  overlaysRef.current = overlays;
  historicalTrafficRef.current = historicalTraffic;
  areaDrawModeRef.current = areaDrawMode;
  areaGeometryRef.current = areaGeometry;
  areaVesselsRef.current = areaVessels;
  onAreaGeometryChangeRef.current = onAreaGeometryChange;
  onAreaGeometryInvalidRef.current = onAreaGeometryInvalid;

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
      const sourceId = (e as { sourceId?: unknown }).sourceId;
      if (
        isMaritimeReferenceSourceId(sourceId) ||
        sourceId === HISTORICAL_TRAFFIC_SOURCE_ID
      ) return;
      const msg = (e?.error && (e.error as Error).message) || "";
      const basemapFailed =
        stageRef.current === "pmtiles" || /tile|source|network|fetch|response code/i.test(msg);
      if (msg && stageRef.current !== "emergency" && basemapFailed) {
        onBaseMapError?.(msg);
        const nextFailure =
          stageRef.current === "online"
            ? "online_failed"
            : stageRef.current === "pmtiles"
              ? "pmtiles_failed"
              : failureRef.current;
        const nextStage = selectOfflineBasemap(onlineBasemapRef.current, nextFailure);
        if (nextStage !== stageRef.current) {
          failureRef.current = nextFailure;
          stageRef.current = nextStage;
          setBasemapStage(nextStage);
          map.setStyle(styleForStage(nextStage, layersRef.current.baseMap));
          map.once("styledata", () =>
            restoreOverlays(
              map,
              layersRef.current,
              vesselsRef.current,
              selectedIdRef.current,
              selectedSourceRef.current,
              areaGeometryRef.current,
              areaVesselsRef.current,
              historicalTrafficRef.current,
              overlaysRef.current,
            ),
          );
        }
      }
    });

    map.on("load", () => {
      loadedRef.current = true;
      if (onlineBasemapRef.current && failureRef.current === "pmtiles_failed") {
        failureRef.current = "healthy";
      }
      const desiredStage = selectOfflineBasemap(
        onlineBasemapRef.current,
        failureRef.current,
      );
      if (desiredStage !== stageRef.current) {
        stageRef.current = desiredStage;
        setBasemapStage(desiredStage);
        map.setStyle(styleForStage(desiredStage, layersRef.current.baseMap));
        map.once("styledata", () =>
          restoreOverlays(
            map,
            layersRef.current,
            vesselsRef.current,
            selectedIdRef.current,
            selectedSourceRef.current,
            areaGeometryRef.current,
            areaVesselsRef.current,
            historicalTrafficRef.current,
            overlaysRef.current,
          ),
        );
        emitViewport(map, onViewportChange);
        return;
      }
      installOverlays(map, historicalTrafficRef.current, overlaysRef.current);
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
      applyLayerVisibility(map, layersRef.current, selectedIdRef.current);
      applyPorts(map, layersRef.current);
      applyAirspace(map, layersRef.current);
      emitViewport(map, onViewportChange);
    });

    map.on("moveend", () => emitViewport(map, onViewportChange));

    // Manual pan/zoom -> pause follow mode. Programmatic moves (flyTo/follow)
    // set a flag so they don't count as user interaction.
    map.on("dragstart", () => onUserInteract?.());
    map.on("zoomstart", () => {
      if (!programmaticMoveRef.current) onUserInteract?.();
    });

    // Click a MapLibre ship symbol to open the existing vessel workflow.
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
    const finalizePolygon = () => {
      const geometry = finalizePolygonPoints(polygonDraftRef.current);
      if (!geometry) {
        onAreaGeometryInvalidRef.current?.();
        return false;
      }
      polygonDraftRef.current = [];
      areaDrawModeRef.current = null;
      areaGeometryRef.current = geometry;
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      map.getCanvas().style.cursor = "";
      applyPolygonDraft(map, []);
      applyAreaGeometry(map, geometry);
      onAreaGeometryChangeRef.current?.(geometry);
      return true;
    };

    map.on("click", (e) => {
      if (areaDrawModeRef.current === "polygon") {
        const first = polygonDraftRef.current[0];
        if (first && isWithinPolygonCloseTolerance(map, e.point, first)) {
          if (polygonDraftRef.current.length >= 3) finalizePolygon();
          return;
        }
        polygonDraftRef.current.push([e.lngLat.lng, e.lngLat.lat]);
        applyPolygonDraft(map, polygonDraftRef.current);
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
      finalizePolygon();
    });

    // Rectangle drawing owns one native canvas pointer from press through
    // release. Pointer capture keeps moves/releases arriving when the cursor
    // leaves the canvas, while preventing MapLibre's compatibility mouse drag
    // from panning the map underneath the draft.
    const canvas = map.getCanvas();
    const rectangleCoordinate = (event: PointerEvent): [number, number] => {
      const bounds = canvas.getBoundingClientRect();
      const coordinate = map.unproject([
        event.clientX - bounds.left,
        event.clientY - bounds.top,
      ]);
      return [coordinate.lng, coordinate.lat];
    };
    const releaseRectanglePointer = () => {
      const pointerId = rectanglePointerIdRef.current;
      rectanglePointerIdRef.current = null;
      if (pointerId === null) return;
      try {
        if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
      } catch {
        // The browser may already have released capture after cancellation.
      }
    };
    const onRectanglePointerDown = (event: PointerEvent) => {
      if (
        areaDrawModeRef.current !== "rectangle" ||
        rectanglePointerIdRef.current !== null ||
        (event.pointerType === "mouse" && event.button !== 0)
      ) return;
      event.preventDefault();
      event.stopPropagation();
      rectangleStartRef.current = rectangleCoordinate(event);
      rectanglePointerIdRef.current = event.pointerId;
      map.dragPan.disable();
      try {
        canvas.setPointerCapture(event.pointerId);
      } catch {
        // Pointer capture can fail only if the pointer ended during dispatch;
        // the matching pointerup/cancel path will still clear the draft.
      }
    };
    const onRectanglePointerMove = (event: PointerEvent) => {
      const start = rectangleStartRef.current;
      if (
        areaDrawModeRef.current !== "rectangle" ||
        !start ||
        rectanglePointerIdRef.current !== event.pointerId
      ) return;
      event.preventDefault();
      event.stopPropagation();
      applyAreaGeometry(map, rectangleFromCorners(start, rectangleCoordinate(event)));
    };
    const onRectanglePointerUp = (event: PointerEvent) => {
      const start = rectangleStartRef.current;
      if (
        areaDrawModeRef.current !== "rectangle" ||
        !start ||
        rectanglePointerIdRef.current !== event.pointerId
      ) return;
      event.preventDefault();
      event.stopPropagation();
      const geometry = rectangleFromCorners(start, rectangleCoordinate(event));
      rectangleStartRef.current = null;
      releaseRectanglePointer();
      if (!geometry) {
        applyAreaGeometry(map, areaGeometryRef.current);
        return;
      }
      areaDrawModeRef.current = null;
      areaGeometryRef.current = geometry;
      map.dragPan.enable();
      canvas.style.cursor = "";
      applyAreaGeometry(map, geometry);
      onAreaGeometryChangeRef.current?.(geometry);
    };
    const onRectanglePointerCancel = (event: PointerEvent) => {
      if (rectanglePointerIdRef.current !== event.pointerId) return;
      rectangleStartRef.current = null;
      releaseRectanglePointer();
      applyAreaGeometry(map, areaGeometryRef.current);
    };
    canvas.addEventListener("pointerdown", onRectanglePointerDown);
    canvas.addEventListener("pointermove", onRectanglePointerMove);
    canvas.addEventListener("pointerup", onRectanglePointerUp);
    canvas.addEventListener("pointercancel", onRectanglePointerCancel);

    const cancelDrawing = () => {
      polygonDraftRef.current = [];
      rectangleStartRef.current = null;
      releaseRectanglePointer();
      areaDrawModeRef.current = null;
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      canvas.style.cursor = "";
      applyPolygonDraft(map, []);
      applyAreaGeometry(map, areaGeometryRef.current);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelDrawing();
    };
    window.addEventListener("keydown", onEscape);

    // Hover tooltip (desktop) — lightweight, does not open the panel.
    map.on("mousemove", ALL_VESSEL_INTERACTIVE_LAYERS, (e) => {
      if (areaDrawModeRef.current === "rectangle") {
        map.getCanvas().style.cursor = "crosshair";
        return;
      }
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
      map.getCanvas().style.cursor = areaDrawModeRef.current === "rectangle" ? "crosshair" : "";
      popupRef.current?.remove();
    });

    const historicalPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      className: "historical-traffic-map-popup",
    });
    map.on("mousemove", HISTORICAL_TRAFFIC_FILL_LAYER_ID, (e) => {
      if (areaDrawModeRef.current !== null) {
        map.getCanvas().style.cursor = "crosshair";
        historicalPopup.remove();
        return;
      }
      const operationalLayers = existingLayers(map, [
        TRACK_LAYER,
        HALO_LAYER,
        VESSEL_LAYER,
        AREA_FILL_LAYER,
        AREA_LINE_LAYER,
        AREA_DRAFT_PATH_LAYER,
        AREA_DRAFT_VERTEX_LAYER,
        AREA_VESSEL_HALO_LAYER,
        AREA_VESSEL_LAYER,
        ...(overlaysRef.current?.layers.map((layer) => layer.id) ?? []),
      ]);
      if (
        e.point
        && operationalLayers.length > 0
        && map.queryRenderedFeatures(e.point, { layers: operationalLayers }).length > 0
      ) {
        historicalPopup.remove();
        return;
      }
      const feature = e.features?.[0];
      if (!feature) return;
      map.getCanvas().style.cursor = "pointer";
      historicalPopup
        .setLngLat(e.lngLat)
        .setHTML(formatHistoricalTrafficPopup(
          feature.properties as Partial<HistoricalTrafficProperties>,
        ))
        .addTo(map);
    });
    map.on("mouseleave", HISTORICAL_TRAFFIC_FILL_LAYER_ID, () => {
      map.getCanvas().style.cursor = areaDrawModeRef.current === null ? "" : "crosshair";
      historicalPopup.remove();
    });

    mapRef.current = map;
    startAnimation();

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      loadedRef.current = false;
      popupRef.current?.remove();
      historicalPopup.remove();
      window.removeEventListener("keydown", onEscape);
      canvas.removeEventListener("pointerdown", onRectanglePointerDown);
      canvas.removeEventListener("pointermove", onRectanglePointerMove);
      canvas.removeEventListener("pointerup", onRectanglePointerUp);
      canvas.removeEventListener("pointercancel", onRectanglePointerCancel);
      releaseRectanglePointer();
      canvas.style.cursor = "";
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Online operation starts on OpenFreeMap; offline operation starts locally.
  // A latched failure advances through PMTiles to bundled emergency geography.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    // A PMTiles failure says nothing about the remote style. During startup the
    // dashboard may learn that online basemaps are preferred only after the
    // local fallback has already failed, so give the still-untried online
    // source its own chance instead of treating the PMTiles failure as final.
    if (prefersOnlineBasemap && failureRef.current === "pmtiles_failed") {
      failureRef.current = "healthy";
    }
    const nextStage = selectOfflineBasemap(prefersOnlineBasemap, failureRef.current);
    if (nextStage === stageRef.current) return;
    stageRef.current = nextStage;
    setBasemapStage(nextStage);
    map.setStyle(styleForStage(nextStage, layersRef.current.baseMap));
    map.once("styledata", () =>
      restoreOverlays(
        map,
        layersRef.current,
        vesselsRef.current,
        selectedIdRef.current,
        selectedSourceRef.current,
        areaGeometryRef.current,
        areaVesselsRef.current,
        historicalTrafficRef.current,
        overlaysRef.current,
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operatingMode, prefersOnlineBasemap]);

  // Switch base map when it changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (stageRef.current !== "online") return;
    if (currentBaseRef.current === layers.baseMap) return;
    currentBaseRef.current = layers.baseMap;
    onBaseMapError?.(null);
    map.setStyle(onlineStyle(layers.baseMap));
    map.once("styledata", () => {
      installOverlays(map, historicalTrafficRef.current, overlaysRef.current);
      applyVessels(map, vesselsRef.current, selectedIdRef.current, selectedSourceRef.current);
      applyAreaGeometry(map, areaGeometryRef.current);
      applyAreaVessels(
        map,
        areaVesselsRef.current,
        selectedIdRef.current,
        selectedSourceRef.current,
      );
      applyLayerVisibility(map, layersRef.current, selectedIdRef.current);
      applyPorts(map, layersRef.current);
      applyAirspace(map, layersRef.current);
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
    installHistoricalTrafficLayers(
      map,
      historicalTraffic,
      MARITIME_REFERENCE_LAYER_IDS.eez.fill,
    );
    setHistoricalTrafficVisibility(map, layers.historicalTraffic);
  }, [historicalTraffic, layers.historicalTraffic]);

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
    applyPolygonDraft(map, []);
    rectangleStartRef.current = null;
    const canvas = map.getCanvas();
    const activePointerId = rectanglePointerIdRef.current;
    rectanglePointerIdRef.current = null;
    if (activePointerId !== null) {
      try {
        if (canvas.hasPointerCapture(activePointerId)) {
          canvas.releasePointerCapture(activePointerId);
        }
      } catch {
        // Capture may already be gone after a pointer cancellation.
      }
    }
    if (areaDrawMode === "polygon") map.doubleClickZoom.disable();
    else map.doubleClickZoom.enable();
    if (areaDrawMode === "rectangle") {
      map.dragPan.disable();
      canvas.style.cursor = "crosshair";
    } else if (areaDrawMode === "polygon") {
      map.dragPan.enable();
      canvas.style.cursor = "crosshair";
    } else {
      map.dragPan.enable();
      canvas.style.cursor = "";
    }
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

function installOverlays(
  map: maplibregl.Map,
  historicalTraffic?: HistoricalTrafficFeatureCollection | null,
  overlays?: MapOverlays | null,
) {
  installHistoricalTrafficLayers(
    map,
    historicalTraffic,
    MARITIME_REFERENCE_LAYER_IDS.eez.fill,
  );
  installMaritimeReferenceOverlays(map);
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
  if (!map.getLayer(VESSEL_LAYER)) {
    map.addLayer({
      id: VESSEL_LAYER,
      type: "symbol",
      source: VESSEL_SOURCE,
      layout: {
        "icon-image": SHIP_ICON,
        "icon-size": ["interpolate", ["linear"], ["zoom"], 5, 0.22, 9, 0.34, 12, 0.5],
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
          categoryColorExpression(),
        ],
        "icon-opacity": [
          "case",
          ["==", ["get", "displayState"], "stale"],
          0.48,
          ["==", ["get", "freshnessState"], "unknown"],
          0.68,
          0.95,
        ],
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
        "text-field": ["get", "nameEn"],
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
  if (!map.getSource(AREA_DRAFT_PATH_SOURCE)) {
    map.addSource(AREA_DRAFT_PATH_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
  }
  if (!map.getLayer(AREA_DRAFT_PATH_LAYER)) {
    map.addLayer({
      id: AREA_DRAFT_PATH_LAYER,
      type: "line",
      source: AREA_DRAFT_PATH_SOURCE,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: {
        "line-color": "#67e8f9",
        "line-width": 2.5,
        "line-dasharray": [2, 1.5],
      },
    });
  }
  if (!map.getSource(AREA_DRAFT_VERTEX_SOURCE)) {
    map.addSource(AREA_DRAFT_VERTEX_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
  }
  if (!map.getLayer(AREA_DRAFT_VERTEX_LAYER)) {
    map.addLayer({
      id: AREA_DRAFT_VERTEX_LAYER,
      type: "circle",
      source: AREA_DRAFT_VERTEX_SOURCE,
      paint: {
        "circle-radius": ["case", ["==", ["get", "role"], "start"], 7, 4.5],
        "circle-color": [
          "case",
          ["==", ["get", "role"], "start"],
          "#fbbf24",
          "#e0f2fe",
        ],
        "circle-stroke-color": "#082f49",
        "circle-stroke-width": 2,
      },
    });
  }
  if (!map.getSource(AREA_VESSEL_SOURCE)) {
    map.addSource(AREA_VESSEL_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
      promoteId: "fid",
    });
  }
  if (!map.getLayer(AREA_VESSEL_HALO_LAYER)) {
    map.addLayer({
      id: AREA_VESSEL_HALO_LAYER,
      type: "circle",
      source: AREA_VESSEL_SOURCE,
      paint: {
        "circle-radius": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          16,
          0,
        ],
        "circle-color": "#fbbf24",
        "circle-opacity": 0.22,
        "circle-stroke-color": "#fbbf24",
        "circle-stroke-width": 2,
      },
    });
  }
  if (!map.getLayer(AREA_VESSEL_LAYER)) {
    map.addLayer({
      id: AREA_VESSEL_LAYER,
      type: "symbol",
      source: AREA_VESSEL_SOURCE,
      layout: {
        "icon-image": SHIP_ICON,
        "icon-size": ["interpolate", ["linear"], ["zoom"], 5, 0.24, 9, 0.38, 12, 0.54],
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
          categoryColorExpression(),
        ],
        "icon-opacity": [
          "case",
          ["==", ["get", "freshnessState"], "stale"],
          0.48,
          ["==", ["get", "freshnessState"], "unknown"],
          0.68,
          0.98,
        ],
        "icon-halo-color": "#f59e0b",
        "icon-halo-width": 1.5,
      },
    });
  }
  // Generic, caller-provided overlays (logistics-agnostic). Installed last so
  // they render above the built-in layers, and re-installed on every style
  // change via restoreOverlays. Idempotent: existing sources are updated via
  // setData and existing layers are not re-added (no duplicate registration).
  installGenericOverlays(map, overlays);
}

function installMaritimeReferenceOverlays(map: maplibregl.Map) {
  for (const source of MARITIME_REFERENCE_SOURCES) {
    if (!map.getSource(source.id)) {
      map.addSource(source.id, {
        type: "geojson",
        data: maritimeReferenceUrl(source.route),
        attribution: source.attribution,
      });
    }
  }
  for (const layer of MARITIME_REFERENCE_LAYER_SPECS) {
    if (!map.getLayer(layer.id)) map.addLayer(layer);
  }
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

function styleForStage(
  stage: BasemapStage,
  baseMap: LayerState["baseMap"],
): StyleSpecification | string {
  if (stage === "pmtiles") return pmtilesStyle();
  if (stage === "emergency") return emergencyStyle();
  return onlineStyle(baseMap);
}

function restoreOverlays(
  map: maplibregl.Map,
  layers: LayerState,
  vessels: LiveVesselFeature[],
  selectedId: string | null,
  selectedSource: "live" | "datalastic" | null,
  areaGeometry: GeoJSON.Polygon | null,
  areaVessels: LiveVesselFeature[],
  historicalTraffic?: HistoricalTrafficFeatureCollection | null,
  overlays?: MapOverlays | null,
) {
  installOverlays(map, historicalTraffic, overlays);
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
  const features = vessels.map((v) => mapVesselFeature(v, now, true));
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

function applyPolygonDraft(map: maplibregl.Map, points: Array<[number, number]>) {
  const pathSource = map.getSource(AREA_DRAFT_PATH_SOURCE) as maplibregl.GeoJSONSource | undefined;
  const vertexSource = map.getSource(AREA_DRAFT_VERTEX_SOURCE) as maplibregl.GeoJSONSource | undefined;
  pathSource?.setData(points.length >= 2
    ? {
        type: "FeatureCollection",
        features: [{
          type: "Feature",
          geometry: { type: "LineString", coordinates: points },
          properties: {},
        }],
      }
    : { type: "FeatureCollection", features: [] });
  vertexSource?.setData({
    type: "FeatureCollection",
    features: points.map((coordinates, index) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates },
      properties: { role: index === 0 ? "start" : "vertex" },
    })),
  });
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
    features: vessels.map((v) => mapVesselFeature(v, Date.now(), false)),
  });
  applySelectedState(map, [], selectedId, vessels, selectedSource);
}

function mapVesselFeature(vessel: LiveVesselFeature, now: number, interpolate: boolean) {
  const orientation = normalizeOrientation(
    vessel.properties.heading_deg,
    vessel.properties.cog_deg,
  );
  const fix: MeasuredFix = {
    lon: vessel.geometry.coordinates[0],
    lat: vessel.geometry.coordinates[1],
    sogKnots: vessel.properties.sog_knots,
    courseDeg: orientation,
    observedAtMs: Date.parse(vessel.properties.observed_at ?? ""),
  };
  const projected = interpolate
    ? projectPosition(fix, now)
    : { lon: fix.lon, lat: fix.lat, interpolated: false };
  return {
    type: "Feature" as const,
    id: vessel.id,
    geometry: {
      type: "Point" as const,
      coordinates: [projected.lon, projected.lat],
    },
    properties: {
      fid: vessel.id,
      publicId: vessel.id,
      orientation: orientation ?? 0,
      category: categoryForVessel(vessel),
      isInterpolated: projected.interpolated || vessel.properties.synthesized,
      displayState:
        vessel.properties.display_state ??
        (vessel.properties.freshness_state === "stale" ? "stale" : "live"),
      freshnessState: vessel.properties.freshness_state ?? "fresh",
      source: vessel.properties.source,
    },
  };
}

function categoryColorExpression(): ExpressionSpecification {
  return [
    "match",
    ["get", "category"],
    "Cargo", VESSEL_CATEGORY_COLORS.Cargo,
    "Tanker", VESSEL_CATEGORY_COLORS.Tanker,
    "Fishing", VESSEL_CATEGORY_COLORS.Fishing,
    "Passenger", VESSEL_CATEGORY_COLORS.Passenger,
    "Tug / Service", VESSEL_CATEGORY_COLORS["Tug / Service"],
    "Research / Survey", VESSEL_CATEGORY_COLORS["Research / Survey"],
    "Government / Law Enforcement", VESSEL_CATEGORY_COLORS["Government / Law Enforcement"],
    "Pleasure / Sailing", VESSEL_CATEGORY_COLORS["Pleasure / Sailing"],
    "Other", VESSEL_CATEGORY_COLORS.Other,
    "Unknown", VESSEL_CATEGORY_COLORS.Unknown,
    VESSEL_CATEGORY_COLORS.Unknown,
  ];
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

function isWithinPolygonCloseTolerance(
  map: maplibregl.Map,
  point: { x: number; y: number },
  first: [number, number],
): boolean {
  const projectedFirst = map.project(first);
  return Math.hypot(point.x - projectedFirst.x, point.y - projectedFirst.y) <=
    POLYGON_CLOSE_TOLERANCE_PX;
}

function rectangleFromCorners(
  start: [number, number],
  end: [number, number],
): GeoJSON.Polygon | null {
  const minLon = Math.min(start[0], end[0]);
  const minLat = Math.min(start[1], end[1]);
  const maxLon = Math.max(start[0], end[0]);
  const maxLat = Math.max(start[1], end[1]);
  if (minLon === maxLon || minLat === maxLat) return null;
  return {
    type: "Polygon",
    coordinates: [[
      [minLon, minLat],
      [maxLon, minLat],
      [maxLon, maxLat],
      [minLon, maxLat],
      [minLon, minLat],
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
  setVisible(map, MARITIME_REFERENCE_LAYER_IDS.eez.fill, layers.eezReference);
  setVisible(map, MARITIME_REFERENCE_LAYER_IDS.eez.line, layers.eezReference);
  setVisible(
    map,
    MARITIME_REFERENCE_LAYER_IDS.territorialSea12Nm.fill,
    layers.territorialSea12NmReference,
  );
  setVisible(
    map,
    MARITIME_REFERENCE_LAYER_IDS.territorialSea12Nm.line,
    layers.territorialSea12NmReference,
  );
  setVisible(
    map,
    MARITIME_REFERENCE_LAYER_IDS.contiguousZone24Nm.fill,
    layers.contiguousZone24NmReference,
  );
  setVisible(
    map,
    MARITIME_REFERENCE_LAYER_IDS.contiguousZone24Nm.line,
    layers.contiguousZone24NmReference,
  );
  setVisible(map, VESSEL_LAYER, layers.liveVessels);
  setVisible(map, HALO_LAYER, layers.liveVessels);
  // Trails are off by default, but the selected vessel's trail is always shown.
  setVisible(map, TRACK_LAYER, layers.vesselTracks || selectedId !== null);
  setVisible(map, PORT_LAYER, layers.ports);
  setVisible(map, PORT_LABEL, layers.ports);
  setVisible(map, AIRSPACE_FILL, layers.restrictedAirspace || layers.publicAirspace);
  setVisible(map, AIRSPACE_LINE, layers.restrictedAirspace || layers.publicAirspace);
  setHistoricalTrafficVisibility(map, layers.historicalTraffic);
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

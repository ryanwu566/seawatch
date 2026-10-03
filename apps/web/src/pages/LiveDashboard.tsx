import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchLiveHealth,
  fetchResilienceStatus,
  fetchLiveTrack,
  fetchLiveVessels,
  authenticateAreaScan,
  scanLiveArea,
  AreaScanApiError,
  type AreaScanResponse,
  type Bbox,
  type LiveHealth,
  type LiveTrack,
  type LiveVesselFeature,
  type OperatingMode,
  type ResilienceStatus,
} from "../api/live";
import { useI18n } from "../i18n/I18nContext";
import { AppHeader } from "../components/AppHeader";
import { ResilienceBanner } from "../components/ResilienceBanner";
import { OperatingStatusPanel } from "../components/OperatingStatusPanel";
import { StatusCards } from "../components/StatusCards";
import { LayerControl } from "../components/LayerControl";
import { SearchControl } from "../components/SearchControl";
import { VesselPanel } from "../components/VesselPanel";
import { MapCanvas, type Viewport } from "../components/MapCanvas";
import { AreaScanPanel, type AreaDrawMode } from "../components/AreaScanPanel";
import { DEFAULT_LAYER_STATE, type LayerState } from "../lib/layerState";
import { deriveLiveStatus } from "../lib/liveStatus";
import { modePresentation } from "../lib/resilience";
import { friendlySource } from "../lib/display";
import { LOCATION_PRESETS } from "../config/taiwanMap";
import { getDemoScenario } from "../features/intelligence/demoScenario";

const POLL_MS = 8000;
const VIEWPORT_DEBOUNCE_MS = 400;
type VesselSelectionSource = "live" | "datalastic";

/**
 * Taiwan-first, map-first live maritime awareness experience. The map dominates;
 * a compact header, floating status chip, floating search + layer controls, and
 * a right-side vessel drawer sit over it. Vessels poll by viewport bbox with
 * debounce; motion is smoothed on the client via visual interpolation.
 */
export function LiveDashboard({ vesselDemo = false }: { vesselDemo?: boolean }) {
  const { t } = useI18n();

  const [vessels, setVessels] = useState<LiveVesselFeature[]>([]);
  const [health, setHealth] = useState<LiveHealth | null>(null);
  const [resilience, setResilience] = useState<ResilienceStatus | null>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYER_STATE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<VesselSelectionSource | null>(null);
  const [track, setTrack] = useState<LiveTrack | null>(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const [follow, setFollow] = useState(false);
  const [paused, setPaused] = useState(false);
  const [baseMapError, setBaseMapError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fitBounds, setFitBounds] = useState<[number, number, number, number] | null>(null);
  const [fitNonce, setFitNonce] = useState(0);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [areaDrawMode, setAreaDrawMode] = useState<AreaDrawMode>(null);
  const [areaGeometry, setAreaGeometry] = useState<GeoJSON.Polygon | null>(null);
  const [areaResult, setAreaResult] = useState<AreaScanResponse | null>(null);
  const [areaLoading, setAreaLoading] = useState(false);
  const [areaError, setAreaError] = useState<string | null>(null);
  const [areaAuthenticated, setAreaAuthenticated] = useState(false);
  const [areaAuthenticating, setAreaAuthenticating] = useState(false);

  // DEMO fixture (frontend-only, illustrative). The demo vessel is NEVER added
  // to the live `vessels` array; it is held entirely separately and opens only
  // after the exact `?demo=vessel` route sets this prop. Live polling/selection
  // and source status remain unaffected.
  const [demoOpen, setDemoOpen] = useState(vesselDemo);
  const demoScenario = useMemo(() => getDemoScenario(), []);
  const openDemo = useCallback(() => {
    setSelectedId(null); // ensure no live vessel is selected simultaneously
    setSelectedSource(null);
    setDemoOpen(true);
  }, []);
  const closeDemo = useCallback(() => setDemoOpen(false), []);

  const viewportRef = useRef<Bbox | null>(null);
  const debounceRef = useRef<number | null>(null);
  const areaScanGenerationRef = useRef(0);
  const areaScanAbortRef = useRef<AbortController | null>(null);

  const loadVessels = useCallback(async () => {
    try {
      const [collection, h, resilient] = await Promise.all([
        fetchLiveVessels(viewportRef.current ?? undefined),
        fetchLiveHealth().catch(() => null),
        fetchResilienceStatus().catch(() => null),
      ]);
      setVessels(collection.features);
      if (h) setHealth(h);
      if (resilient) setResilience(resilient);
      setError(null);
      setLoadedOnce(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.errorLoadingVessels);
    }
  }, [t]);

  useEffect(() => {
    loadVessels();
    const id = window.setInterval(loadVessels, POLL_MS);
    return () => window.clearInterval(id);
  }, [loadVessels]);

  const handleViewportChange = useCallback(
    (viewport: Viewport) => {
      viewportRef.current = {
        minLat: viewport.minLat,
        minLon: viewport.minLon,
        maxLat: viewport.maxLat,
        maxLon: viewport.maxLon,
      };
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        loadVessels();
      }, VIEWPORT_DEBOUNCE_MS);
    },
    [loadVessels],
  );

  const areaVessels = areaResult?.vessels ?? [];
  const allSearchVessels = useMemo(() => {
    const byId = new Map(vessels.map((v) => [v.id, v]));
    for (const vessel of areaVessels) byId.set(vessel.id, vessel);
    return [...byId.values()];
  }, [vessels, areaVessels]);
  const selected = useMemo(
    () =>
      selectedId
        ? selectedSource === "datalastic"
          ? (areaVessels.find((v) => v.id === selectedId) ?? null)
          : (vessels.find((v) => v.id === selectedId) ?? null)
        : null,
    [areaVessels, vessels, selectedId, selectedSource],
  );
  const selectedMissing = selectedId !== null && selected === null;

  const lastKnownRef = useRef<LiveVesselFeature | null>(null);
  if (selected) lastKnownRef.current = selected;
  if (selectedId === null) lastKnownRef.current = null;
  const panelVessel = selected ?? lastKnownRef.current;

  useEffect(() => {
    if (!selectedId) {
      setTrack(null);
      return;
    }
    setTrack(null);
    setTrackLoading(true);
    const controller = new AbortController();
    fetchLiveTrack(
      selectedId,
      controller.signal,
      selectedSource === "datalastic" ? "datalastic" : undefined,
    )
      .then((tk) => {
        if (!controller.signal.aborted) setTrack(tk);
      })
      .catch(() => {
        if (!controller.signal.aborted) setTrack(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setTrackLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [selectedId, selectedSource]);

  const handleSelectVessel = useCallback((
    feature: LiveVesselFeature,
    source?: VesselSelectionSource,
  ) => {
    setDemoOpen(false); // live selection and demo are mutually exclusive
    setSelectedId(feature.id);
    setSelectedSource(
      source ?? (feature.properties.source === "datalastic" ? "datalastic" : "live"),
    );
    setFollow(true);
    setPaused(false);
  }, []);

  const handleDeselect = useCallback(() => {
    setSelectedId(null);
    setSelectedSource(null);
    setTrack(null);
    setFollow(false);
    setPaused(false);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAreaDrawMode(null);
        handleDeselect();
        closeDemo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleDeselect, closeDemo]);

  const handleUserInteract = useCallback(() => {
    setFollow((f) => {
      if (f) setPaused(true);
      return false;
    });
  }, []);

  const handleResumeFollow = useCallback(() => {
    setFollow(true);
    setPaused(false);
  }, []);

  const handleFitBounds = useCallback((bounds: [number, number, number, number]) => {
    setFitBounds(bounds);
    setFitNonce((n) => n + 1);
  }, []);

  const handleAreaDrawMode = useCallback((mode: Exclude<AreaDrawMode, null>) => {
    areaScanGenerationRef.current += 1;
    areaScanAbortRef.current?.abort();
    areaScanAbortRef.current = null;
    setAreaLoading(false);
    setAreaDrawMode(mode);
    setAreaGeometry(null);
    setAreaResult(null);
    setAreaError(null);
  }, []);

  const handleAreaGeometryChange = useCallback((geometry: GeoJSON.Polygon) => {
    areaScanGenerationRef.current += 1;
    areaScanAbortRef.current?.abort();
    areaScanAbortRef.current = null;
    setAreaLoading(false);
    setAreaGeometry(geometry);
    setAreaDrawMode(null);
    setAreaResult(null);
    setAreaError(null);
  }, []);

  const handleAreaAuthenticate = useCallback(async (operatorCredential: string) => {
    setAreaAuthenticating(true);
    setAreaError(null);
    try {
      await authenticateAreaScan(operatorCredential);
      setAreaAuthenticated(true);
    } catch {
      setAreaAuthenticated(false);
      setAreaError(t.areaScanAuthFailed);
    } finally {
      setAreaAuthenticating(false);
    }
  }, [t]);

  const handleAreaScan = useCallback(async () => {
    if (!areaGeometry || !areaAuthenticated) return;
    const generation = areaScanGenerationRef.current + 1;
    areaScanGenerationRef.current = generation;
    areaScanAbortRef.current?.abort();
    const controller = new AbortController();
    areaScanAbortRef.current = controller;
    setAreaLoading(true);
    setAreaError(null);
    try {
      const result = await scanLiveArea(areaGeometry, controller.signal);
      if (areaScanGenerationRef.current === generation) setAreaResult(result);
    } catch (err) {
      if (areaScanGenerationRef.current === generation && !controller.signal.aborted) {
        if (err instanceof AreaScanApiError && (err.status === 401 || err.status === 403)) {
          setAreaAuthenticated(false);
          setAreaError(t.areaScanSessionExpired);
        } else {
          setAreaError(err instanceof AreaScanApiError ? err.message : t.datalasticUnavailable);
        }
      }
    } finally {
      if (areaScanGenerationRef.current === generation) {
        setAreaLoading(false);
        areaScanAbortRef.current = null;
      }
    }
  }, [areaAuthenticated, areaGeometry, t]);

  const handleAreaClear = useCallback(() => {
    areaScanGenerationRef.current += 1;
    areaScanAbortRef.current?.abort();
    areaScanAbortRef.current = null;
    const selectedWasArea = selectedSource === "datalastic";
    setAreaLoading(false);
    setAreaDrawMode(null);
    setAreaGeometry(null);
    setAreaResult(null);
    setAreaError(null);
    if (selectedWasArea) handleDeselect();
  }, [selectedSource, handleDeselect]);

  useEffect(() => () => areaScanAbortRef.current?.abort(), []);

  const freshestAge = vessels.reduce<number | null>((minimum, vessel) => {
    const age = vessel.properties.data_age_seconds;
    if (age === null || !Number.isFinite(age)) return minimum;
    return minimum === null ? age : Math.min(minimum, age);
  }, null);

  const status = deriveLiveStatus({ demo: false, health, vesselCount: vessels.length });
  const effectiveResilience: ResilienceStatus =
    resilience ??
    ({
      mode: status === "live" ? "CLOUD_LIVE" : "NO_LIVE_SOURCE",
      coverage: status === "live" ? "taiwan_wide_network_feed" : "none",
      simulated: false,
      internet_available: status === "live",
      power_mode: "external",
      cloud: health?.cloud ?? {
        source: "open_waters",
        fresh: status === "live",
        message_age_seconds: health?.message_age_seconds ?? null,
        vessel_count: health?.vessel_count ?? 0,
        connected: health?.connected ?? false,
        input_kind: null,
      },
      edge: health?.edge ?? {
        source: "edge_ais",
        fresh: false,
        message_age_seconds: null,
        vessel_count: 0,
        connected: false,
        input_kind: "disabled",
      },
    } satisfies ResilienceStatus);
  const presentation = modePresentation(effectiveResilience, t);
  const previousModeRef = useRef<OperatingMode | null>(null);
  const previousMode = previousModeRef.current;
  useEffect(() => {
    previousModeRef.current = effectiveResilience.mode;
  }, [effectiveResilience.mode]);

  const selectedTrackGeo: GeoJSON.Feature | null =
    track && track.properties.point_count >= 2
      ? { type: "Feature", geometry: track.geometry, properties: {} }
      : null;

  const sourceLabel = friendlySource(health?.provider ?? "open_waters", t);

  // Empty-viewport state: loaded, live (not reconnecting), but no vessels here.
  const showEmptyState =
    loadedOnce && vessels.length === 0 && areaVessels.length === 0 && status !== "reconnecting";
  const taiwanPreset = LOCATION_PRESETS[0];

  return (
    <div className="live-dashboard lang-shell">
      <AppHeader presentation={presentation} />
      <ResilienceBanner status={effectiveResilience} previousMode={previousMode} />

      {vesselDemo && (
        <div
          className="offline-banner vessel-demo-banner"
          data-testid="vessel-demo-mode"
          role="note"
        >
          {t.demoIllustrativeLabel}
        </div>
      )}
      {effectiveResilience.mode === "OFFLINE_DEMO" && <div className="offline-banner">{t.offlineDemoNote}</div>}
      {status === "reconnecting" && <div className="warn-banner">{t.reconnectingAis}</div>}
      {error && (
        <div className="error-banner">
          {t.errorLoadingVessels}: {error}
        </div>
      )}
      {baseMapError && <div className="warn-banner">{t.corsNote}</div>}

      <div className="map-shell">
        <MapCanvas
          vessels={layers.liveVessels ? vessels : []}
          layers={layers}
          selectedId={selectedId}
          selectedSource={selectedSource}
          selectedTrack={selectedTrackGeo}
          follow={follow}
          fitBounds={fitBounds}
          fitBoundsNonce={fitNonce}
          onSelectVessel={handleSelectVessel}
          onDeselect={handleDeselect}
          onViewportChange={handleViewportChange}
          onUserInteract={handleUserInteract}
          onBaseMapError={setBaseMapError}
          operatingMode={effectiveResilience.mode}
          areaDrawMode={areaDrawMode}
          areaGeometry={areaGeometry}
          areaVessels={areaVessels}
          onAreaGeometryChange={handleAreaGeometryChange}
        />

        <div className="map-overlay-top-left">
          <OperatingStatusPanel status={effectiveResilience} />
          <AreaScanPanel
            drawMode={areaDrawMode}
            geometry={areaGeometry}
            loading={areaLoading}
            result={areaResult}
            error={areaError}
            authenticated={areaAuthenticated}
            authenticating={areaAuthenticating}
            onDrawMode={handleAreaDrawMode}
            onAuthenticate={handleAreaAuthenticate}
            onScan={handleAreaScan}
            onClear={handleAreaClear}
          />
          <SearchControl
            vessels={allSearchVessels}
            onSelectVessel={handleSelectVessel}
            onFitBounds={handleFitBounds}
          />
          <StatusCards
            vesselCount={vessels.length}
            needsReview={null}
            freshestAgeSeconds={freshestAge}
            source={sourceLabel}
          />
          {vesselDemo && !demoOpen && (
            <button
              type="button"
              className="demo-entry-btn"
              data-testid="demo-entry"
              onClick={openDemo}
            >
              {t.demoViewVessel}
            </button>
          )}
        </div>

        <div className="map-overlay-right">
          <LayerControl layers={layers} onChange={setLayers} />
        </div>

        {showEmptyState && (
          <div className="empty-viewport" role="status">
            <p>{t.emptyViewport}</p>
            <div className="empty-actions">
              <button type="button" onClick={() => handleFitBounds(taiwanPreset.bounds)}>
                {t.presetTaiwanWaters}
              </button>
            </div>
          </div>
        )}

        {selectedId && (
          <div className="follow-control">
            {follow ? (
              <span className="follow-pill active">{t.following}</span>
            ) : (
              <button type="button" className="follow-btn" onClick={handleResumeFollow}>
                {paused ? t.resumeFollow : t.followVessel}
              </button>
            )}
          </div>
        )}

        {demoOpen && (
          <VesselPanel
            vessel={demoScenario.vessel}
            track={demoScenario.track}
            trackLoading={false}
            demo
            demoContext={demoScenario.geographicContext}
            onClose={closeDemo}
          />
        )}

        {!demoOpen && selectedId && (
          <VesselPanel
            vessel={panelVessel}
            track={track}
            trackLoading={trackLoading}
            demo={false}
            missing={selectedMissing}
            onClose={handleDeselect}
          />
        )}
      </div>
    </div>
  );
}

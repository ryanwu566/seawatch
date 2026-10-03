import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchLiveHealth,
  fetchResilienceStatus,
  fetchLiveTrack,
  fetchLiveVessels,
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
import { DEFAULT_LAYER_STATE, type LayerState } from "../lib/layerState";
import { deriveLiveStatus } from "../lib/liveStatus";
import { modePresentation } from "../lib/resilience";
import { friendlySource } from "../lib/display";
import { LOCATION_PRESETS } from "../config/taiwanMap";
import { getDemoScenario } from "../features/intelligence/demoScenario";

const POLL_MS = 8000;
const VIEWPORT_DEBOUNCE_MS = 400;

function isDemoMode(): boolean {
  return String(import.meta.env?.VITE_DEMO_MODE ?? "false").toLowerCase() === "true";
}

/**
 * Taiwan-first, map-first live maritime awareness experience. The map dominates;
 * a compact header, floating status chip, floating search + layer controls, and
 * a right-side vessel drawer sit over it. Vessels poll by viewport bbox with
 * debounce; motion is smoothed on the client via visual interpolation.
 */
export function LiveDashboard() {
  const { t } = useI18n();
  const demo = isDemoMode();

  const [vessels, setVessels] = useState<LiveVesselFeature[]>([]);
  const [health, setHealth] = useState<LiveHealth | null>(null);
  const [resilience, setResilience] = useState<ResilienceStatus | null>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYER_STATE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [track, setTrack] = useState<LiveTrack | null>(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const [follow, setFollow] = useState(false);
  const [paused, setPaused] = useState(false);
  const [baseMapError, setBaseMapError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fitBounds, setFitBounds] = useState<[number, number, number, number] | null>(null);
  const [fitNonce, setFitNonce] = useState(0);
  const [loadedOnce, setLoadedOnce] = useState(false);

  // DEMO fixture (frontend-only, illustrative). The demo vessel is NEVER added
  // to the live `vessels` array; it is held entirely separately and only shown
  // when the judge explicitly opens it. Live polling/selection is unaffected.
  const [demoOpen, setDemoOpen] = useState(false);
  const demoScenario = useMemo(() => getDemoScenario(), []);
  const openDemo = useCallback(() => {
    setSelectedId(null); // ensure no live vessel is selected simultaneously
    setDemoOpen(true);
  }, []);
  const closeDemo = useCallback(() => setDemoOpen(false), []);

  const viewportRef = useRef<Bbox | null>(null);
  const debounceRef = useRef<number | null>(null);

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

  const selected = useMemo(
    () => (selectedId ? (vessels.find((v) => v.id === selectedId) ?? null) : null),
    [vessels, selectedId],
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
    let cancelled = false;
    fetchLiveTrack(selectedId)
      .then((tk) => {
        if (!cancelled) setTrack(tk);
      })
      .catch(() => {
        if (!cancelled) setTrack(null);
      })
      .finally(() => {
        if (!cancelled) setTrackLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const handleSelectVessel = useCallback((feature: LiveVesselFeature) => {
    setDemoOpen(false); // live selection and demo are mutually exclusive
    setSelectedId(feature.id);
    setFollow(true);
    setPaused(false);
  }, []);

  const handleDeselect = useCallback(() => {
    setSelectedId(null);
    setTrack(null);
    setFollow(false);
    setPaused(false);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
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

  const freshestAge =
    vessels.length === 0
      ? null
      : vessels.reduce((min, v) => Math.min(min, v.properties.data_age_seconds), Infinity);

  const status = deriveLiveStatus({ demo, health, vesselCount: vessels.length });
  const effectiveResilience: ResilienceStatus =
    resilience ??
    ({
      mode: demo ? "OFFLINE_DEMO" : status === "live" ? "CLOUD_LIVE" : "NO_LIVE_SOURCE",
      coverage: demo ? "demo" : status === "live" ? "taiwan_wide_network_feed" : "none",
      simulated: demo,
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
  const showEmptyState = loadedOnce && vessels.length === 0 && status !== "reconnecting";
  const taiwanPreset = LOCATION_PRESETS[0];

  return (
    <div className="live-dashboard lang-shell">
      <AppHeader presentation={presentation} />
      <ResilienceBanner status={effectiveResilience} previousMode={previousMode} />

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
        />

        <div className="map-overlay-top-left">
          <OperatingStatusPanel status={effectiveResilience} />
          <SearchControl
            vessels={vessels}
            onSelectVessel={handleSelectVessel}
            onFitBounds={handleFitBounds}
          />
          <StatusCards
            vesselCount={vessels.length}
            needsReview={null}
            freshestAgeSeconds={freshestAge}
            source={sourceLabel}
          />
          {demo && !demoOpen && (
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
            demo={demo}
            missing={selectedMissing}
            onClose={handleDeselect}
          />
        )}
      </div>
    </div>
  );
}

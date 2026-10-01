import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchLiveHealth,
  fetchLiveTrack,
  fetchLiveVessels,
  type Bbox,
  type LiveHealth,
  type LiveTrack,
  type LiveVesselFeature,
} from "../api/live";
import { useI18n } from "../i18n/I18nContext";
import { AppHeader } from "../components/AppHeader";
import { StatusCards } from "../components/StatusCards";
import { LayerControl } from "../components/LayerControl";
import { VesselPanel } from "../components/VesselPanel";
import { MapCanvas, type Viewport } from "../components/MapCanvas";
import { DEFAULT_LAYER_STATE, type LayerState } from "../lib/layerState";
import { deriveLiveStatus } from "../lib/liveStatus";
import { friendlySource } from "../lib/display";

const POLL_MS = 8000;
const VIEWPORT_DEBOUNCE_MS = 400;

function isDemoMode(): boolean {
  return String(import.meta.env?.VITE_DEMO_MODE ?? "false").toLowerCase() === "true";
}

/**
 * Taiwan-first live maritime awareness experience. The map is the main surface.
 * Vessels poll by viewport bbox with debounce; motion is smoothed on the client
 * via visual interpolation (never fabricated server-side). The selected vessel
 * is tracked by id so it survives data refreshes; a follow mode keeps the map
 * centered on it, pausing when the user manually pans.
 */
export function LiveDashboard() {
  const { t } = useI18n();
  const demo = isDemoMode();

  const [vessels, setVessels] = useState<LiveVesselFeature[]>([]);
  const [health, setHealth] = useState<LiveHealth | null>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYER_STATE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [track, setTrack] = useState<LiveTrack | null>(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const [follow, setFollow] = useState(false);
  const [paused, setPaused] = useState(false); // follow paused by manual drag
  const [baseMapError, setBaseMapError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const viewportRef = useRef<Bbox | null>(null);
  const debounceRef = useRef<number | null>(null);

  const loadVessels = useCallback(async () => {
    try {
      const [collection, h] = await Promise.all([
        fetchLiveVessels(viewportRef.current ?? undefined),
        fetchLiveHealth().catch(() => null),
      ]);
      setVessels(collection.features);
      if (h) setHealth(h);
      setError(null);
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

  // The selected vessel is resolved by id from the latest feed each render, so
  // it stays selected while new AIS positions arrive and reflects fresh data.
  const selected = useMemo(
    () => (selectedId ? (vessels.find((v) => v.id === selectedId) ?? null) : null),
    [vessels, selectedId],
  );
  const selectedMissing = selectedId !== null && selected === null;

  // Remember the last-known feature for the selected id so the panel can keep
  // showing its details (with a "no recent update" notice) if it drops out.
  const lastKnownRef = useRef<LiveVesselFeature | null>(null);
  if (selected) lastKnownRef.current = selected;
  if (selectedId === null) lastKnownRef.current = null;
  const panelVessel = selected ?? lastKnownRef.current;

  // Load the selected vessel's track when the selection id changes.
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

  // Escape closes the panel / deselects.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleDeselect();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleDeselect]);

  // Manual pan/zoom pauses follow mode.
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

  const freshestAge =
    vessels.length === 0
      ? null
      : vessels.reduce((min, v) => Math.min(min, v.properties.data_age_seconds), Infinity);

  const status = deriveLiveStatus({ demo, health, vesselCount: vessels.length });

  const selectedTrackGeo: GeoJSON.Feature | null =
    track && track.properties.point_count >= 2
      ? { type: "Feature", geometry: track.geometry, properties: {} }
      : null;

  const sourceLabel = friendlySource(health?.provider ?? "open_waters", t);

  return (
    <div className="live-dashboard lang-shell">
      <AppHeader status={status} />

      {status === "offline_demo" && <div className="offline-banner">{t.offlineDemoNote}</div>}
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
          onSelectVessel={handleSelectVessel}
          onDeselect={handleDeselect}
          onViewportChange={handleViewportChange}
          onUserInteract={handleUserInteract}
          onBaseMapError={setBaseMapError}
        />

        <div className="map-overlay-top">
          <StatusCards
            vesselCount={vessels.length}
            needsReview={0}
            freshestAgeSeconds={freshestAge}
            source={sourceLabel}
          />
        </div>

        <div className="map-overlay-right">
          <LayerControl layers={layers} onChange={setLayers} />
        </div>

        {selectedId && (
          <div className="follow-control">
            {follow ? (
              <span className="follow-pill active">{t.following}</span>
            ) : paused ? (
              <button type="button" className="follow-btn" onClick={handleResumeFollow}>
                {t.resumeFollow}
              </button>
            ) : (
              <button type="button" className="follow-btn" onClick={handleResumeFollow}>
                {t.followVessel}
              </button>
            )}
          </div>
        )}

        {selectedId && (
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

      <footer className="app-footer">
        <span>{t.attribution}</span>
      </footer>
    </div>
  );
}

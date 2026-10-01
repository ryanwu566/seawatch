import { useCallback, useEffect, useRef, useState } from "react";
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

// Poll the active viewport roughly every 8s. The backend serves this from its
// in-memory store (one upstream feed), so this does not hit Open Waters.
const POLL_MS = 8000;
const VIEWPORT_DEBOUNCE_MS = 400;

function isDemoMode(): boolean {
  return String(import.meta.env?.VITE_DEMO_MODE ?? "false").toLowerCase() === "true";
}

/**
 * Taiwan-first live maritime awareness experience. The map is the main surface;
 * a header, status cards, grouped layer control, and a vessel detail panel sit
 * over it. Vessels poll by viewport bbox with debounce; motion is smoothed on
 * the client via visual interpolation (never fabricated server-side).
 */
export function LiveDashboard() {
  const { t } = useI18n();
  const demo = isDemoMode();

  const [vessels, setVessels] = useState<LiveVesselFeature[]>([]);
  const [health, setHealth] = useState<LiveHealth | null>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYER_STATE);
  const [selected, setSelected] = useState<LiveVesselFeature | null>(null);
  const [track, setTrack] = useState<LiveTrack | null>(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const [baseMapError, setBaseMapError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const viewportRef = useRef<Bbox | null>(null);
  const debounceRef = useRef<number | null>(null);

  // Fetch vessels for the current viewport (or whole bbox if unset).
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

  // Poll on an interval.
  useEffect(() => {
    loadVessels();
    const id = window.setInterval(loadVessels, POLL_MS);
    return () => window.clearInterval(id);
  }, [loadVessels]);

  // Debounced viewport change -> refetch.
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

  // Load the selected vessel's track.
  const handleSelectVessel = useCallback((feature: LiveVesselFeature) => {
    setSelected(feature);
    setTrack(null);
    setTrackLoading(true);
    fetchLiveTrack(feature.id)
      .then((tk) => setTrack(tk))
      .catch(() => setTrack(null))
      .finally(() => setTrackLoading(false));
  }, []);

  const freshestAge =
    vessels.length === 0
      ? null
      : vessels.reduce((min, v) => Math.min(min, v.properties.data_age_seconds), Infinity);

  const status: LiveHealth["status"] = health?.status ?? (vessels.length ? "degraded" : "offline");

  const selectedTrackGeo: GeoJSON.Feature | null =
    track && track.properties.point_count >= 2
      ? { type: "Feature", geometry: track.geometry, properties: {} }
      : null;

  return (
    <div className={`live-dashboard lang-shell`}>
      <AppHeader status={status} demo={demo} />

      {demo && <div className="offline-banner">{t.offlineDemoNote}</div>}
      {error && <div className="error-banner">{t.errorLoadingVessels}: {error}</div>}
      {baseMapError && <div className="warn-banner">{t.corsNote}</div>}

      <div className="map-shell">
        <MapCanvas
          vessels={layers.liveVessels ? vessels : []}
          layers={layers}
          selectedTrack={selectedTrackGeo}
          onSelectVessel={handleSelectVessel}
          onViewportChange={handleViewportChange}
          onBaseMapError={setBaseMapError}
        />

        <div className="map-overlay-top">
          <StatusCards
            vesselCount={vessels.length}
            needsReview={0}
            freshestAgeSeconds={freshestAge}
            source={health?.provider ?? "open_waters"}
          />
        </div>

        <div className="map-overlay-right">
          <LayerControl layers={layers} onChange={setLayers} />
        </div>

        {selected && (
          <VesselPanel
            vessel={selected}
            track={track}
            trackLoading={trackLoading}
            demo={demo}
            onClose={() => {
              setSelected(null);
              setTrack(null);
            }}
          />
        )}
      </div>

      <footer className="app-footer">
        <span>{t.attribution}</span>
      </footer>
    </div>
  );
}

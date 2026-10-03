import { useState } from "react";
import { useI18n } from "../i18n/I18nContext";
import type { LiveVesselFeature, LiveTrack } from "../api/live";
import { classifyVessel, formatAge } from "../lib/integrity";
import { normalizeOrientation } from "../lib/orientation";
import { friendlySource, vesselTypeLabel } from "../lib/display";
import { IntegrityBadge } from "./IntegrityBadge";
import { VesselIntelligenceCard } from "../features/intelligence/VesselIntelligenceCard";
import type { GeographicContext } from "../features/intelligence/geographicTypes";
import type { SatelliteEvidence } from "../features/intelligence/satelliteEvidence";

interface VesselPanelProps {
  vessel: LiveVesselFeature | null;
  track: LiveTrack | null;
  trackLoading: boolean;
  demo: boolean;
  /** True when the selected vessel is no longer in the live feed (dropped out). */
  missing?: boolean;
  /**
   * Optional ILLUSTRATIVE demo geographic context. When set, the embedded
   * Vessel Intelligence Card renders in DEMO mode (banner + fixture context, no
   * live GIS fetch). Null for all live vessels.
   */
  demoContext?: GeographicContext | null;
  satellite_evidence?: SatelliteEvidence[];
  onClose: () => void;
}

/**
 * Polished consumer-tracking drawer (right-side on desktop, bottom sheet on
 * mobile). Traditional Chinese first with English secondary labels. No MMSI/IMO
 * is shown; raw provider id lives only under Advanced Analysis.
 */
export function VesselPanel({
  vessel,
  track,
  trackLoading,
  demo,
  missing,
  demoContext = null,
  satellite_evidence,
  onClose,
}: VesselPanelProps) {
  const { t, lang } = useI18n();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  if (!vessel) {
    return (
      <aside className="vessel-drawer empty" aria-label={t.vesselOverview}>
        <p className="muted">{t.selectVesselHint}</p>
      </aside>
    );
  }

  const p = vessel.properties;
  const integrity = classifyVessel(vessel, { demo });
  const trackPoints = track?.properties.point_count ?? 0;
  const hasTrail = trackPoints >= 2;
  const course = normalizeOrientation(p.heading_deg, p.cog_deg);

  // Per-vessel DEMO panel: a demoContext means this drawer is the illustrative
  // fixture, not a live/offline vessel. We override ONLY the Position-status and
  // Source *display* here so they no longer read "Offline Demo" / "Live AIS".
  // Live behavior (demoContext === null) is unchanged; classifyVessel,
  // friendlySource, evidence logic, and provenance are all untouched.
  const isDemoPanel = demoContext !== null;

  const positionStatus =
    integrity === "provider_interpolated"
      ? t.positionProviderInterp
      : integrity === "stale"
        ? t.positionStale
        : t.positionMeasured;

  return (
    <aside
      className={`vessel-drawer vessel-${integrity}`}
      data-display-state={integrity}
      aria-label={t.vesselOverview}
      role="dialog"
    >
      <button type="button" className="drawer-close" onClick={onClose} aria-label={t.closePanel}>
        ✕
      </button>

      {/* Header: ship glyph + name + type + last update */}
      <header className="drawer-header">
        <span className="drawer-ship-icon" aria-hidden="true">
          ⛴
        </span>
        <div className="drawer-identity">
          <h2 className="drawer-name">{p.name || t.noVesselName}</h2>
          <p className="drawer-type">{vesselTypeLabel(p.vessel_type, lang)}</p>
          <p className="drawer-updated">
            {t.dataFreshness}: {formatAge(p.data_age_seconds, t)}
          </p>
        </div>
      </header>

      {missing && <div className="vessel-missing">{t.noRecentUpdate}</div>}

      {/* Clean metric row */}
      <div className="drawer-metrics">
        <div className="metric">
          <span className="metric-value">
            {p.sog_knots === null ? "—" : p.sog_knots.toFixed(1)}
            {p.sog_knots !== null && <span className="metric-unit"> {t.knots}</span>}
          </span>
          <span className="metric-label">{t.speed}</span>
        </div>
        <div className="metric">
          <span className="metric-value">
            {course === null ? "—" : `${Math.round(course)}${t.degrees}`}
          </span>
          <span className="metric-label">{t.course}</span>
        </div>
        <div className="metric">
          <span className="metric-value small">{p.destination || "—"}</span>
          <span className="metric-label">{t.destination}</span>
        </div>
      </div>

      {/* Position status + source */}
      <dl className="drawer-fields">
        <dt>{t.positionStatus}</dt>
        <dd>
          {isDemoPanel ? (
            <span className="position-status-text" data-field="position-status">
              {t.demoPositionStatus}
            </span>
          ) : (
            <>
              <IntegrityBadge kind={integrity} />
              <span className="position-status-text" data-field="position-status">
                {positionStatus}
              </span>
            </>
          )}
        </dd>
        <dt>{t.source}</dt>
        <dd data-field="source">
          {isDemoPanel ? t.demoSourceLabel : friendlySource(p.source, t)}
        </dd>
      </dl>

      {/* Track */}
      <section className="drawer-section">
        <h3>{t.recentTrack}</h3>
        {trackLoading ? (
          <p className="muted">{t.loading}</p>
        ) : hasTrail ? (
          <p className="muted">
            {trackPoints} · {t.recentTrack}
          </p>
        ) : (
          <p className="muted building">{t.buildingTrackHistory}</p>
        )}
      </section>

      {/* Needs review — placeholder state, no fabricated score */}
      <section className="drawer-section">
        <h3>{t.reviewPriority}</h3>
        <p className="muted collecting">{t.collectingForAnalysis}</p>
      </section>

      {/* Explainable Vessel Intelligence — collapsed, additive, review support */}
      <VesselIntelligenceCard
        vessel={vessel}
        track={track}
        demoContext={demoContext}
        satellite_evidence={satellite_evidence}
      />

      {/* Advanced analysis — collapsed, technical fields live here */}
      <section className="advanced-analysis">
        <button
          type="button"
          className="advanced-toggle"
          onClick={() => setAdvancedOpen((v) => !v)}
          aria-expanded={advancedOpen}
        >
          {advancedOpen ? "▾" : "▸"} {t.advancedAnalysis}
        </button>
        {advancedOpen && (
          <div className="advanced-body">
            <dl className="drawer-fields">
              <dt>{t.heading}</dt>
              <dd>{p.heading_deg === null ? "—" : `${Math.round(p.heading_deg)}${t.degrees}`}</dd>
              <dt>{t.dataQuality}</dt>
              <dd>
                {p.source}
                {p.synthesized ? " · provider-interpolated" : ""}
              </dd>
              <dt>{t.benchmarkSource}</dt>
              <dd>NOAA MarineCadastre AIS (SF Bay)</dd>
            </dl>
            <p className="disclaimer">{t.benchmarkDisclaimer}</p>
          </div>
        )}
      </section>
    </aside>
  );
}

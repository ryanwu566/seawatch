import { useState } from "react";
import { useI18n } from "../i18n/I18nContext";
import type { LiveVesselFeature, LiveTrack } from "../api/live";
import { classifyVessel, formatAge } from "../lib/integrity";
import { normalizeOrientation } from "../lib/orientation";
import { friendlySource, vesselTypeLabel } from "../lib/display";
import { IntegrityBadge } from "./IntegrityBadge";

interface VesselPanelProps {
  vessel: LiveVesselFeature | null;
  track: LiveTrack | null;
  trackLoading: boolean;
  demo: boolean;
  /** True when the selected vessel is no longer in the live feed (dropped out). */
  missing?: boolean;
  onClose: () => void;
}

/**
 * Consumer-tracking style vessel panel (side panel on desktop, bottom sheet on
 * mobile). Traditional Chinese first with English secondary labels. No MMSI/IMO
 * is required or shown. Technical analysis lives under a collapsed section.
 */
export function VesselPanel({
  vessel,
  track,
  trackLoading,
  demo,
  missing,
  onClose,
}: VesselPanelProps) {
  const { t, lang } = useI18n();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  if (!vessel) {
    return (
      <aside className="vessel-panel empty" aria-label={t.vesselOverview}>
        <p className="muted">{t.selectVesselHint}</p>
      </aside>
    );
  }

  const p = vessel.properties;
  const integrity = classifyVessel(vessel, { demo });
  const trackPoints = track?.properties.point_count ?? 0;
  const hasTrail = trackPoints >= 2;
  const course = normalizeOrientation(p.heading_deg, p.cog_deg);

  // Position status: how trustworthy the on-screen position is.
  const positionStatus =
    integrity === "provider_interpolated"
      ? t.positionProviderInterp
      : integrity === "stale"
        ? t.positionStale
        : t.positionMeasured;

  return (
    <aside className="vessel-panel" aria-label={t.vesselOverview}>
      <div className="vessel-panel-head">
        <div>
          <h2>{p.name || t.noVesselName}</h2>
          <p className="vessel-sub">{vesselTypeLabel(p.vessel_type, lang)}</p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label={t.closePanel}>
          ✕
        </button>
      </div>

      {missing && <div className="vessel-missing">{t.noRecentUpdate}</div>}

      <div className="vessel-badges">
        <IntegrityBadge kind={integrity} />
        <span className="fix-age" title={t.measuredFix}>
          {formatAge(p.data_age_seconds, t)}
        </span>
      </div>

      <dl className="vessel-fields">
        <dt>{t.vesselType}</dt>
        <dd>{vesselTypeLabel(p.vessel_type, lang)}</dd>
        <dt>{t.speed}</dt>
        <dd>{p.sog_knots === null ? "—" : `${p.sog_knots.toFixed(1)} ${t.knots}`}</dd>
        <dt>{t.course}</dt>
        <dd>{course === null ? "—" : `${t.course} ${Math.round(course)}${t.degrees}`}</dd>
        <dt>{t.destination}</dt>
        <dd>{p.destination || "—"}</dd>
        <dt>{t.lastUpdate}</dt>
        <dd>{formatAge(p.data_age_seconds, t)}</dd>
        <dt>{t.source}</dt>
        <dd>{friendlySource(p.source, t)}</dd>
        <dt>{t.positionStatus}</dt>
        <dd>{positionStatus}</dd>
      </dl>

      <section className="vessel-track-section">
        <h3>{t.recentTrack}</h3>
        {trackLoading ? (
          <p className="muted">{t.loading}</p>
        ) : hasTrail ? (
          <p className="muted">
            {trackPoints} {t.recentTrack}
          </p>
        ) : (
          <p className="muted building">{t.buildingTrackHistory}</p>
        )}
      </section>

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
            <dl className="vessel-fields">
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

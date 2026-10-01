import { useState } from "react";
import { useI18n } from "../i18n/I18nContext";
import type { LiveVesselFeature, LiveTrack } from "../api/live";
import { classifyVessel, formatAge } from "../lib/integrity";
import { IntegrityBadge } from "./IntegrityBadge";

interface VesselPanelProps {
  vessel: LiveVesselFeature | null;
  track: LiveTrack | null;
  trackLoading: boolean;
  demo: boolean;
  onClose: () => void;
}

/**
 * Friendly vessel information panel (side panel on desktop, bottom sheet on
 * mobile). Traditional Chinese first with English secondary labels. Technical
 * analysis lives under a collapsed "Advanced Analysis" section. No MMSI/IMO is
 * required or shown.
 */
export function VesselPanel({ vessel, track, trackLoading, demo, onClose }: VesselPanelProps) {
  const { t } = useI18n();
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

  return (
    <aside className="vessel-panel" aria-label={t.vesselOverview}>
      <div className="vessel-panel-head">
        <div>
          <h2>{p.name || t.noVesselName}</h2>
          <p className="vessel-sub">{t.vesselOverview}</p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label={t.closePanel}>
          ✕
        </button>
      </div>

      <div className="vessel-badges">
        <IntegrityBadge kind={integrity} />
        <span className="fix-age" title={t.measuredFix}>
          {t.dataFreshness}: {formatAge(p.data_age_seconds, t)}
        </span>
      </div>

      <dl className="vessel-fields">
        <dt>{t.speed}</dt>
        <dd>{p.sog_knots === null ? "—" : `${p.sog_knots.toFixed(1)} ${t.knots}`}</dd>
        <dt>{t.course}</dt>
        <dd>{p.cog_deg === null ? "—" : `${Math.round(p.cog_deg)}${t.degrees}`}</dd>
        <dt>{t.heading}</dt>
        <dd>{p.heading_deg === null ? "—" : `${Math.round(p.heading_deg)}${t.degrees}`}</dd>
        <dt>{t.destination}</dt>
        <dd>{p.destination || "—"}</dd>
        <dt>{t.lastUpdate}</dt>
        <dd>{formatAge(p.data_age_seconds, t)}</dd>
        <dt>{t.source}</dt>
        <dd>{p.source}</dd>
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

      <section className="vessel-review-section">
        <h3>{t.reviewPriority}</h3>
        {/* Live vessels have no Taiwan-validated score; show collecting state. */}
        <p className="muted collecting">{t.collectingTrajectory}</p>
        <h4>{t.whyFlagged}</h4>
        <p className="muted">{t.collectingTrajectory}</p>
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
              <dt>{t.analysisMethod}</dt>
              <dd>empirical_percentile</dd>
              <dt>{t.percentile}</dt>
              <dd>—</dd>
              <dt>{t.supportingFeatures}</dt>
              <dd>—</dd>
              <dt>{t.dataQuality}</dt>
              <dd>
                {t.source}: {p.source}
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

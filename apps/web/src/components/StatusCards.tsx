import { useI18n } from "../i18n/I18nContext";
import { formatAge } from "../lib/integrity";

interface StatusCardsProps {
  vesselCount: number;
  needsReview: number | null;
  freshestAgeSeconds: number | null;
  source: string;
}

/**
 * Compact floating status widget overlaid on the map (not a large dashboard
 * box). Shows current vessels, needs-review, update freshness, and the friendly
 * data source. Needs-review shows a collecting state when no live score exists.
 */
export function StatusCards({
  vesselCount,
  needsReview,
  freshestAgeSeconds,
  source,
}: StatusCardsProps) {
  const { t } = useI18n();
  return (
    <div className="status-chip" aria-label={t.statusLabel}>
      <div className="status-item">
        <span className="status-label">{t.vesselsNow}</span>
        <span className="status-value">{vesselCount.toLocaleString()}</span>
      </div>
      <div className="status-divider" aria-hidden="true" />
      <div className="status-item">
        <span className="status-label">{t.needsReview}</span>
        <span className="status-value">
          {needsReview === null ? "—" : needsReview.toLocaleString()}
        </span>
      </div>
      <div className="status-divider" aria-hidden="true" />
      <div className="status-item">
        <span className="status-label">{t.lastUpdated}</span>
        <span className="status-value">
          {freshestAgeSeconds === null ? "—" : formatAge(freshestAgeSeconds, t)}
        </span>
      </div>
      <div className="status-divider" aria-hidden="true" />
      <div className="status-item">
        <span className="status-label">{t.source}</span>
        <span className="status-value small">{source}</span>
      </div>
    </div>
  );
}

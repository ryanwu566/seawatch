import { useI18n } from "../i18n/I18nContext";
import { formatAge } from "../lib/integrity";

interface StatusCardsProps {
  vesselCount: number;
  needsReview: number;
  freshestAgeSeconds: number | null;
  source: string;
}

/** Four simple, non-technical status cards shown over the map. */
export function StatusCards({
  vesselCount,
  needsReview,
  freshestAgeSeconds,
  source,
}: StatusCardsProps) {
  const { t } = useI18n();
  return (
    <div className="status-cards" aria-label="status">
      <div className="status-card">
        <span className="status-label">{t.vesselsNow}</span>
        <span className="status-value">{vesselCount.toLocaleString()}</span>
      </div>
      <div className="status-card">
        <span className="status-label">{t.needsReview}</span>
        <span className="status-value">{needsReview.toLocaleString()}</span>
      </div>
      <div className="status-card">
        <span className="status-label">{t.lastUpdated}</span>
        <span className="status-value">
          {freshestAgeSeconds === null ? "—" : formatAge(freshestAgeSeconds, t)}
        </span>
      </div>
      <div className="status-card">
        <span className="status-label">{t.source}</span>
        <span className="status-value small">{source}</span>
      </div>
    </div>
  );
}

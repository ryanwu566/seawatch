import type { ResilienceStatus } from "../api/live";
import { useI18n } from "../i18n/I18nContext";
import { operatingStatusPresentation } from "../lib/resilience";

export function OperatingStatusPanel({ status }: { status: ResilienceStatus }) {
  const { t } = useI18n();
  const presentation = operatingStatusPresentation(status, t);

  return (
    <aside
      className={`operating-status operating-status-${status.mode.toLowerCase()}`}
      data-testid="operating-status-panel"
      data-mode={status.mode}
      aria-label={t.operatingStatusTitle}
    >
      <div className="operating-status-heading">
        <span className="operating-status-kicker">{t.operatingStatusTitle}</span>
        <strong>{presentation.label}</strong>
      </div>
      <dl className="operating-status-grid">
        <div>
          <dt>{t.source}</dt>
          <dd className="mono">{presentation.source}</dd>
        </div>
        <div>
          <dt>{t.dataFreshness}</dt>
          <dd>{presentation.freshness}</dd>
        </div>
        <div>
          <dt>{t.coverageStatus}</dt>
          <dd>
            <strong>{presentation.coverageLabel}</strong>
            <span>{presentation.coverageDetail}</span>
          </dd>
        </div>
        <div>
          <dt>{t.provenance}</dt>
          <dd>{presentation.provenance}</dd>
        </div>
      </dl>
    </aside>
  );
}

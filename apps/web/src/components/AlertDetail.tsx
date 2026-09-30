import type { AlertDetail as AlertDetailData } from "../types";
import { formatFraction, formatPercentile, formatPriority, formatValue } from "./format";

interface AlertDetailProps {
  alert: AlertDetailData | null;
  loading?: boolean;
  error?: string | null;
}

/**
 * Investigation panel for a selected review candidate. Shows the ranking result,
 * feature-derived explanation reasons, supporting features, and data quality.
 *
 * Terminology is deliberately neutral: these are behavioral review candidates,
 * not threat, hostility, or legality determinations.
 */
export function AlertDetail({ alert, loading, error }: AlertDetailProps) {
  if (loading) {
    return (
      <div className="alert-detail">
        <h2 className="panel-title">Investigation</h2>
        <p className="muted">Loading review candidate…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert-detail">
        <h2 className="panel-title">Investigation</h2>
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!alert) {
    return (
      <div className="alert-detail">
        <h2 className="panel-title">Investigation</h2>
        <p className="muted">Select a review candidate to inspect its explanation.</p>
      </div>
    );
  }

  return (
    <div className="alert-detail" aria-label="Selected review candidate">
      <h2 className="panel-title">Investigation</h2>

      <div className="priority-banner">
        <span className="priority-label">Review Priority</span>
        <span className="priority-value">{formatPriority(alert.ranking_score)}</span>
      </div>

      <dl className="detail-grid">
        <dt>Alert ID</dt>
        <dd className="mono">{alert.alert_id}</dd>
        <dt>Track ID</dt>
        <dd className="mono">{alert.track_id}</dd>
        <dt>Date</dt>
        <dd>{alert.date}</dd>
        <dt>Ranking score</dt>
        <dd>{alert.ranking_score.toFixed(2)}</dd>
        <dt>Ranking method</dt>
        <dd>{alert.ranking_method}</dd>
        <dt>Rank</dt>
        <dd>{alert.rank}</dd>
        <dt>Shortlisted</dt>
        <dd>{alert.shortlisted ? "Yes" : "No"}</dd>
        <dt>Review status</dt>
        <dd>{alert.review_status}</dd>
      </dl>

      <section className="detail-section">
        <h3>Reasons</h3>
        {alert.explanation_reasons.length === 0 ? (
          <p className="muted">No explanation reasons recorded.</p>
        ) : (
          <ul className="reason-list">
            {alert.explanation_reasons.map((reason, index) => (
              <li key={`${reason.reason_code}-${index}`}>
                <span className="reason-message">{reason.message}</span>
                <span className="reason-meta">
                  {reason.feature_name} · {reason.direction} ·{" "}
                  {formatPercentile(reason.reference_percentile)} percentile
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail-section">
        <h3>Supporting features</h3>
        {alert.supporting_features.length === 0 ? (
          <p className="muted">No supporting features recorded.</p>
        ) : (
          <ul className="feature-list">
            {alert.supporting_features.map((feature, index) => (
              <li key={`${feature.feature_name}-${index}`}>
                <span className="mono">{feature.feature_name}</span>{" "}
                <span>{formatValue(feature.observed_value, feature.unit)}</span>{" "}
                <span className="muted">
                  ({formatPercentile(feature.reference_percentile)} percentile)
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail-section">
        <h3>Data quality</h3>
        <dl className="detail-grid">
          <dt>Observations</dt>
          <dd>{alert.data_quality.observation_count}</dd>
          <dt>Observed duration</dt>
          <dd>{Math.round(alert.data_quality.observed_duration_seconds)} s</dd>
          <dt>Max gap</dt>
          <dd>
            {alert.data_quality.max_gap_seconds === null
              ? "—"
              : `${Math.round(alert.data_quality.max_gap_seconds)} s`}
          </dd>
          <dt>Speed valid</dt>
          <dd>{formatFraction(alert.data_quality.sog_valid_fraction)}</dd>
          <dt>Course valid</dt>
          <dd>{formatFraction(alert.data_quality.cog_valid_fraction)}</dd>
        </dl>
      </section>

      <p className="disclaimer">
        Review priority ranks behavioral deviations for human review only. It is
        not a probability, confidence value, or determination of intent.
      </p>
    </div>
  );
}

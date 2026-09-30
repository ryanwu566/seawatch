import type { AlertDetail } from "../types";
import { formatDuration } from "./format";

interface TimelineProps {
  alert: AlertDetail | null;
}

/**
 * Simple trajectory time information for the selected review candidate.
 * No animation: a compact static summary bar of the observation window.
 */
export function Timeline({ alert }: TimelineProps) {
  if (!alert) {
    return (
      <div className="timeline" aria-label="Trajectory timeline">
        <h2 className="panel-title">Timeline</h2>
        <p className="muted">Select a review candidate to view its time window.</p>
      </div>
    );
  }

  const duration = alert.data_quality.observed_duration_seconds;
  const observations = alert.data_quality.observation_count;
  const cadence =
    observations > 1 && duration > 0 ? duration / (observations - 1) : null;

  return (
    <div className="timeline" aria-label="Trajectory timeline">
      <h2 className="panel-title">Timeline</h2>
      <div className="timeline-bar" role="presentation">
        <span className="timeline-start">start</span>
        <span className="timeline-track" />
        <span className="timeline-end">end</span>
      </div>
      <dl className="timeline-grid">
        <dt>Date</dt>
        <dd>{alert.date}</dd>
        <dt>Observed duration</dt>
        <dd>{formatDuration(duration)}</dd>
        <dt>Observations</dt>
        <dd>{observations}</dd>
        <dt>Avg. cadence</dt>
        <dd>{cadence === null ? "—" : `${Math.round(cadence)} s / obs`}</dd>
      </dl>
    </div>
  );
}

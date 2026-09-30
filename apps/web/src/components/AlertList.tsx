import type { AlertSummary } from "../types";
import { formatPriority } from "./format";

interface AlertListProps {
  alerts: AlertSummary[];
  selectedId: string | null;
  onSelect: (alertId: string) => void;
  loading?: boolean;
}

/**
 * Ranked list of behavioral review candidates.
 * Columns: rank, track, score (review priority), method. One row is selectable.
 */
export function AlertList({ alerts, selectedId, onSelect, loading }: AlertListProps) {
  return (
    <div className="alert-list" aria-label="Ranked review candidates">
      <h2 className="panel-title">Review Candidates</h2>
      {loading ? (
        <p className="muted">Loading alerts…</p>
      ) : alerts.length === 0 ? (
        <p className="muted">No review candidates available.</p>
      ) : (
        <table className="alert-table">
          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Track</th>
              <th scope="col">Score</th>
              <th scope="col">Method</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((alert) => {
              const selected = alert.alert_id === selectedId;
              return (
                <tr
                  key={alert.alert_id}
                  className={selected ? "row selected" : "row"}
                  aria-selected={selected}
                  tabIndex={0}
                  onClick={() => onSelect(alert.alert_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(alert.alert_id);
                    }
                  }}
                >
                  <td>{alert.rank}</td>
                  <td className="mono" title={alert.track_id}>
                    {alert.track_id}
                  </td>
                  <td>{formatPriority(alert.ranking_score)}</td>
                  <td>{alert.ranking_method}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

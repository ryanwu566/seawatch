import { useCallback, useEffect, useState } from "react";
import { ApiError, getAlert, getAlerts, getHealth } from "../api/client";
import { AlertDetail } from "../components/AlertDetail";
import { AlertList } from "../components/AlertList";
import { MapView } from "../components/MapView";
import { Timeline } from "../components/Timeline";
import type { AlertDetail as AlertDetailData, AlertSummary } from "../types";

type HealthState = "checking" | "online" | "offline";

/**
 * Investigation dashboard. Loads the ranked review candidates, tracks the
 * selected candidate, and fetches its full detail on demand.
 */
export function Dashboard() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AlertDetailData | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Health check.
  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then((res) => setHealth(res.status === "ok" ? "online" : "offline"))
      .catch(() => setHealth("offline"));
    return () => controller.abort();
  }, []);

  // Load the ranked alerts.
  useEffect(() => {
    const controller = new AbortController();
    setAlertsLoading(true);
    setAlertsError(null);
    getAlerts({}, controller.signal)
      .then((res) => setAlerts(res.alerts))
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setAlertsError(describeError(err, "Failed to load review candidates."));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setAlertsLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  // Load detail for the selected alert.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError(null);
    getAlert(selectedId, controller.signal)
      .then((res) => setDetail(res))
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setDetail(null);
        setDetailError(describeError(err, "Failed to load review candidate."));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedId]);

  const handleSelect = useCallback((alertId: string) => {
    setSelectedId(alertId);
  }, []);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>SeaWatch</h1>
          <p className="tagline">Maritime Investigation Dashboard</p>
        </div>
        <span className={`health health-${health}`}>API: {health}</span>
      </header>

      {alertsError && <div className="banner error">{alertsError}</div>}

      <div className="dashboard-grid">
        <section className="col col-list">
          <AlertList
            alerts={alerts}
            selectedId={selectedId}
            onSelect={handleSelect}
            loading={alertsLoading}
          />
        </section>

        <section className="col col-map">
          <MapView alerts={alerts} selectedId={selectedId} />
          <Timeline alert={detail} />
        </section>

        <section className="col col-detail">
          <AlertDetail alert={detail} loading={detailLoading} error={detailError} />
        </section>
      </div>
    </div>
  );
}

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    return `${fallback} (${err.status}: ${err.message})`;
  }
  if (err instanceof Error) {
    return `${fallback} ${err.message}`;
  }
  return fallback;
}

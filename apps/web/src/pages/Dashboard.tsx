import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import {
  fetchAlert,
  fetchAlerts,
  fetchHealth,
  fetchTrackGeometry,
  isDemoMode,
} from "../api/dataSource";
import { AlertDetail } from "../components/AlertDetail";
import { AlertList } from "../components/AlertList";
import { MapView } from "../components/MapView";
import { Timeline } from "../components/Timeline";
import type {
  AlertDetail as AlertDetailData,
  AlertSummary,
  LineStringGeometry,
} from "../types";

type HealthState = "checking" | "online" | "offline";

/**
 * Investigation dashboard. Loads ranked review candidates, tracks the selected
 * candidate, and fetches its detail and track geometry on demand. In demo mode
 * it reads bundled fixtures and clearly labels the data as non-live.
 */
export function Dashboard() {
  const demo = isDemoMode();

  const [health, setHealth] = useState<HealthState>("checking");
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AlertDetailData | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [geometry, setGeometry] = useState<LineStringGeometry | null>(null);
  const [geometryLoading, setGeometryLoading] = useState(false);
  const [geometryError, setGeometryError] = useState<string | null>(null);

  // Health check.
  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((res) => setHealth(res.status === "ok" ? "online" : "offline"))
      .catch(() => setHealth("offline"));
    return () => controller.abort();
  }, []);

  // Load the ranked alerts.
  useEffect(() => {
    const controller = new AbortController();
    setAlertsLoading(true);
    setAlertsError(null);
    fetchAlerts(controller.signal)
      .then((res) => setAlerts(res.alerts))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setAlertsError(describeError(err, "Failed to load review candidates."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setAlertsLoading(false);
      });
    return () => controller.abort();
  }, []);

  // Load detail + geometry for the selected alert.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      setGeometry(null);
      setGeometryError(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError(null);
    setGeometry(null);
    setGeometryError(null);

    fetchAlert(selectedId, controller.signal)
      .then((res) => {
        setDetail(res);
        // Chain the geometry fetch once we know the track id.
        setGeometryLoading(true);
        return fetchTrackGeometry(res.track_id, controller.signal)
          .then((geo) => setGeometry(geo.geometry))
          .catch((err: unknown) => {
            if (controller.signal.aborted) return;
            setGeometry(null);
            setGeometryError(describeError(err, "No track geometry available."));
          })
          .finally(() => {
            if (!controller.signal.aborted) setGeometryLoading(false);
          });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setDetail(null);
        setDetailError(describeError(err, "Failed to load review candidate."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });

    return () => controller.abort();
  }, [selectedId]);

  const handleSelect = useCallback((alertId: string) => {
    setSelectedId(alertId);
  }, []);

  const selectedTrackId = detail?.track_id ?? null;

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div>
          <h1>SeaWatch</h1>
          <p className="tagline">Maritime Investigation Dashboard</p>
        </div>
        <div className="header-status">
          {demo && (
            <span className="demo-badge" title="Showing bundled demo fixtures, not live data">
              Demo Mode
            </span>
          )}
          <span className={`health health-${health}`}>API: {health}</span>
        </div>
      </header>

      {demo && (
        <div className="banner demo">
          Demo Mode is on. Data shown is bundled sample data for presentation, not
          live backend results.
        </div>
      )}
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
          <MapView
            geometry={geometry}
            selectedTrackId={selectedTrackId}
            loading={geometryLoading}
            error={geometryError}
          />
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

import { useEffect, useMemo, useState } from "react";
import "./watch.css";
import { AlertPanel } from "./AlertPanel";
import { AlertQueue } from "./AlertQueue";
import { ReplayBar } from "./ReplayBar";
import { TuningLab } from "./TuningLab";
import { WatchMap } from "./WatchMap";
import { LEVEL_COLOR, fmtClock } from "./lib";
import { useWatch } from "./useWatch";

/**
 * Watch Floor - the operator's main screen.
 *
 * Left: risk-ranked alert queue. Centre: map with live tracks, zones and the
 * evidence for the selected alert. Right: the explanation (why, timeline, what
 * else it could be, what we cannot know) and the operator's decision.
 * Bottom: replay clock so continuous monitoring can be demonstrated.
 */
export function WatchFloor() {
  const w = useWatch();
  const [lab, setLab] = useState(false);
  const [showTruth, setShowTruth] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (showTruth && w.truth.length === 0) void w.loadTruth();
  }, [showTruth, w]);

  useEffect(() => {
    setLoadingDetail(!!w.selectedId && !w.detail);
  }, [w.selectedId, w.detail]);

  const counts = useMemo(() => {
    const c = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    w.alerts.forEach((a) => (c[a.level] += 1));
    return c;
  }, [w.alerts]);

  if (w.error && !w.ready) {
    return (
      <div className="wf wf-fatal" role="alert">
        <h1>SeaWatch can’t reach its detection service</h1>
        <p>{w.error}</p>
        <pre>uvicorn apps.api.seawatch.main:app --port 8000</pre>
      </div>
    );
  }
  if (!w.ready || !w.scenario || !w.config) {
    return (
      <div className="wf wf-fatal">
        <div className="wf-spin big" aria-label="Loading" />
        <p>Loading simulated Taiwan-waters picture…</p>
      </div>
    );
  }

  return (
    <div className="wf">
      <header className="wf-top">
        <div className="wf-brand">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
            <circle cx="16" cy="16" r="14" fill="none" stroke="#38bdf8" strokeWidth="2" />
            <circle cx="16" cy="16" r="8" fill="none" stroke="#38bdf8" strokeWidth="1.5" opacity=".6" />
            <path d="M16 16 L26 8" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" />
            <circle cx="16" cy="16" r="2.4" fill="#38bdf8" />
          </svg>
          <div>
            <strong>SeaWatch</strong>
            <span>Maritime behaviour analytics · {w.scenario.region_label}</span>
          </div>
        </div>

        <div className="wf-summary" aria-label="Alert summary">
          {(["HIGH", "MEDIUM", "LOW"] as const).map((l) => (
            <span key={l} className={`wf-count ${counts[l] ? "has" : ""}`} style={{ ["--c" as string]: LEVEL_COLOR[l] }}>
              <i />
              <b>{counts[l]}</b> {l[0] + l.slice(1).toLowerCase()}
            </span>
          ))}
          <span className="wf-sep" />
          <span className="wf-stat">
            <b>{w.scenario.vessels}</b> vessels · <b>{w.scenario.fixes.toLocaleString()}</b> AIS reports
          </span>
        </div>

        <div className="wf-top-right">
          {w.regions.filter((r) => r.available).length > 1 && (
            <select className="wf-region" value={w.region} onChange={(e) => void w.switchRegion(e.target.value)} aria-label="Monitored region">
              {w.regions.filter((r) => r.available).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          )}
          <span className="wf-sim" title={w.scenario.note}>
            {w.scenario.data_kind === "simulated" ? "SIMULATED DATA" : "REAL AIS + INJECTED EVENTS"}
          </span>
          <span className="wf-clock">{fmtClock(w.clock)}</span>
          <button className={`wf-lab-btn ${lab ? "on" : ""}`} onClick={() => setLab((v) => !v)} aria-pressed={lab}>
            ⚙ Tuning lab
          </button>
        </div>
      </header>

      <main className="wf-main">
        <AlertQueue alerts={w.alerts} dismissed={w.dismissed} selectedId={w.selectedId} clock={w.clock} onSelect={w.select} />

        <WatchMap
          scenario={w.scenario}
          tracks={w.tracks}
          alerts={w.alerts}
          detail={w.detail}
          selectedId={w.selectedId}
          clock={w.clock}
          truth={w.truth}
          showTruth={showTruth}
          onSelect={w.select}
        />

        {lab ? (
          <TuningLab
            config={w.config}
            evaluation={w.evaluation}
            alertCount={w.alerts.length}
            busy={w.busy}
            showTruth={showTruth}
            onShowTruth={setShowTruth}
            onChange={w.changeConfig}
            onReset={w.resetConfig}
            onResetFeedback={w.resetFeedback}
            onClose={() => setLab(false)}
          />
        ) : (
          <AlertPanel
            detail={w.detail}
            loading={loadingDetail}
            busy={w.busy}
            onStatus={(s, n) => (w.selectedId ? w.setStatus(w.selectedId, s, n) : Promise.resolve())}
            onNote={(t) => (w.selectedId ? w.addNote(w.selectedId, t) : Promise.resolve())}
            onClose={() => w.select(null)}
          />
        )}
      </main>

      <ReplayBar
        scenario={w.scenario}
        clock={w.clock}
        playing={w.playing}
        speed={w.speed}
        alerts={w.endAlerts}
        selectedId={w.selectedId}
        onClock={w.setClock}
        onPlay={w.setPlaying}
        onSpeed={w.setSpeed}
        onSelect={w.select}
      />
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import "./watch.css";
import { AlertPanel } from "./AlertPanel";
import { AlertQueue } from "./AlertQueue";
import { HistoricalRuntimeCard } from "./HistoricalRuntimeCard";
import { Insight } from "./Insight";
import { ReplayBar } from "./ReplayBar";
import { TuningLab } from "./TuningLab";
import { WatchMap } from "./WatchMap";
import { LEVEL_COLOR, fmtClock } from "./lib";
import { useHistoricalTraffic } from "../../lib/useHistoricalTraffic";
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
  const historicalTraffic = useHistoricalTraffic();
  const [lab, setLab] = useState(false);
  const [insight, setInsight] = useState(false);
  const [showTruth, setShowTruth] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const scenario = w.scenario;
  const config = w.config;
  const ready = !!scenario && !!config;

  useEffect(() => {
    if (showTruth && w.truth.length === 0) void w.loadTruth();
  }, [showTruth, w]);

  useEffect(() => {
    setLoadingDetail(!!w.selectedId && !w.detail);
  }, [w.selectedId, w.detail]);

  useEffect(() => {
    if (w.source === "live") {
      setLab(false);
      setInsight(false);
      setShowTruth(false);
    }
  }, [w.source]);

  const counts = useMemo(() => {
    const c = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    w.alerts.forEach((a) => (c[a.level] += 1));
    return c;
  }, [w.alerts]);

  const liveStatus = (scenario?.detection_status ?? "waiting_for_scan")
    .replace(/_/g, " ")
    .replace(/^./, (letter) => letter.toUpperCase());
  const analysisTime = scenario?.analysis_at ? Date.parse(scenario.analysis_at) / 1000 : null;

  if (w.error && !w.ready) {
    return (
      <div className="wf wf-fatal" role="alert">
        <h1>SeaWatch can’t reach its detection service</h1>
        <p>{w.error}</p>
        <pre>uvicorn apps.api.seawatch.main:app --port 8000</pre>
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
            <span>
              {ready
                ? `Maritime behaviour analytics · ${scenario.region_label}`
                : w.source === "live"
                  ? "Loading Live Area Scan…"
                  : "Loading Scenario replay…"}
            </span>
          </div>
        </div>

        <div className="wf-summary" aria-label="Alert summary">
          {ready ? (
            <>
              {(["HIGH", "MEDIUM", "LOW"] as const).map((l) => (
                <span key={l} className={`wf-count ${counts[l] ? "has" : ""}`} style={{ ["--c" as string]: LEVEL_COLOR[l] }}>
                  <i />
                  <b>{counts[l]}</b> {l[0] + l.slice(1).toLowerCase()}
                </span>
              ))}
              <span className="wf-sep" />
              <span className="wf-stat">
                <b>{scenario.vessels}</b> vessels · <b>{scenario.fixes.toLocaleString()}</b> AIS reports
              </span>
            </>
          ) : (
            <span className="wf-source-loading" role="status">
              Loading detection source…
            </span>
          )}
        </div>

        <div className="wf-top-right">
          <select
            className="wf-region"
            value={w.source}
            onChange={(e) => w.switchSource(e.target.value as "scenario" | "live")}
            aria-label="Detection source"
          >
            <option value="scenario">Scenario replay</option>
            <option value="live">Live Area Scan</option>
          </select>
          {ready && (
            <>
              {w.source === "scenario" && w.regions.filter((r) => r.available).length > 1 && (
                <select className="wf-region" value={w.region} onChange={(e) => void w.switchRegion(e.target.value)} aria-label="Monitored region">
                  {w.regions.filter((r) => r.available).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              )}
              {w.source === "live" ? (
                <span className="wf-sim" title={scenario.note}>Live detection · {liveStatus}</span>
              ) : (
                <span className="wf-sim" title={scenario.note}>
                  {scenario.data_kind === "simulated" ? "SIMULATED DATA" : scenario.data_kind === "real" ? "REAL AIS" : "REAL AIS + INJECTED EVENTS"}
                </span>
              )}
              {w.source === "live" ? (
                <span className="wf-clock" aria-label="Analysis time" title={scenario.analysis_at ?? undefined}>
                  {analysisTime !== null && Number.isFinite(analysisTime) ? `Analysed ${fmtClock(analysisTime)}` : "Not analysed"}
                </span>
              ) : (
                <span className="wf-clock">{fmtClock(w.clock)}</span>
              )}
              {w.source === "scenario" && (
                <>
                  <button className={`wf-lab-btn ${insight ? "on" : ""}`} onClick={() => setInsight((v) => !v)} aria-pressed={insight}>
                    ◎ Rules &amp; accuracy
                  </button>
                  <button className={`wf-lab-btn ${lab ? "on" : ""}`} onClick={() => setLab((v) => !v)} aria-pressed={lab}>
                    ⚙ Tuning lab
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </header>

      {ready && w.source === "scenario" && insight && <Insight onClose={() => setInsight(false)} />}
      <main className="wf-main">
        <div className="wf-queue-column">
          {ready ? (
            <AlertQueue source={w.source} alerts={w.alerts} dismissed={w.dismissed} selectedId={w.selectedId} clock={w.clock} onSelect={w.select} />
          ) : (
            <aside className="wf-queue" aria-label="Alert queue">
              <header className="wf-panel-head">
                <h2>Alert queue</h2>
              </header>
              <p className="wf-empty wf-source-loading-queue">Waiting for source data…</p>
            </aside>
          )}
          <HistoricalRuntimeCard />
        </div>

        {ready ? (
          <WatchMap
            scenario={scenario}
            tracks={w.tracks}
            alerts={w.alerts}
            detail={w.detail}
            selectedId={w.selectedId}
            clock={w.clock}
            truth={w.truth}
            showTruth={showTruth}
            historicalTraffic={historicalTraffic.data}
            historicalTrafficStatus={historicalTraffic.status}
            onSelect={w.select}
          />
        ) : (
          <section className="wf-map wf-source-placeholder" aria-label="Watch map">
            <div className="wf-spin big" aria-hidden />
            <p>Preparing map…</p>
          </section>
        )}

        {ready ? (
          w.source === "scenario" && lab ? (
            <TuningLab
              config={config}
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
              source={w.source}
              detail={w.detail}
              loading={loadingDetail}
              busy={w.busy}
              onStatus={(s, n) => (w.selectedId ? w.setStatus(w.selectedId, s, n) : Promise.resolve())}
              onNote={(t) => (w.selectedId ? w.addNote(w.selectedId, t) : Promise.resolve())}
              onClose={() => w.select(null)}
            />
          )
        ) : (
          <aside className="wf-detail wf-detail-empty" aria-label="Alert detail">
            <p className="wf-empty">Preparing alert details…</p>
          </aside>
        )}
      </main>

      {ready && w.source === "scenario" && (
        <ReplayBar
          scenario={scenario}
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
      )}
    </div>
  );
}

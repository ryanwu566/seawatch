import { useMemo } from "react";
import type { ConfigPayload, Evaluation } from "./api";
import { kindMeta } from "./lib";

interface Props {
  config: ConfigPayload;
  evaluation: Evaluation | null;
  alertCount: number;
  busy: boolean;
  showTruth: boolean;
  onShowTruth: (on: boolean) => void;
  onChange: (values: Record<string, number>) => void;
  onReset: () => void;
  onResetFeedback: () => void;
  onClose: () => void;
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

export function TuningLab({ config, evaluation, alertCount, busy, showTruth, onShowTruth, onChange, onReset, onResetFeedback, onClose }: Props) {
  const groups = useMemo(() => {
    const g = new Map<string, typeof config.specs>();
    config.specs.forEach((s) => g.set(s.group, [...(g.get(s.group) ?? []), s]));
    return [...g.entries()];
  }, [config]);

  const changed = config.specs.filter((s) => config.values[s.name] !== config.defaults[s.name]).length;

  return (
    <section className="wf-lab" aria-label="Tuning lab">
      <header className="wf-panel-head">
        <div>
          <h2>Tuning lab</h2>
          <p className="wf-fine">Trade sensitivity against false alarms. Alerts re-compute instantly and are scored against the simulator’s known answers.</p>
        </div>
        <button className="wf-x" onClick={onClose} aria-label="Close tuning lab">
          ✕
        </button>
      </header>

      <div className="wf-lab-body">
        <div className="wf-lab-sliders">
          {groups.map(([group, specs]) => (
            <fieldset key={group}>
              <legend>{group}</legend>
              {specs.map((s) => {
                const v = config.values[s.name];
                const dirty = v !== config.defaults[s.name];
                return (
                  <label key={s.name} className={dirty ? "dirty" : ""} title={s.help}>
                    <span className="wf-sl-top">
                      <span>{s.label}</span>
                      <output>
                        {v}
                        <small> {s.unit}</small>
                      </output>
                    </span>
                    <input type="range" min={s.min} max={s.max} step={s.step} value={v} onChange={(e) => onChange({ [s.name]: Number(e.target.value) })} />
                  </label>
                );
              })}
            </fieldset>
          ))}
          <div className="wf-lab-actions">
            <button onClick={onReset} disabled={!changed}>
              Reset thresholds{changed ? ` (${changed})` : ""}
            </button>
            <button onClick={onResetFeedback}>Clear operator feedback</button>
          </div>
        </div>

        <div className="wf-lab-eval" aria-live="polite">
          <h3>
            Measured against ground truth {busy && <span className="wf-spin" aria-label="recomputing" />}
          </h3>
          {evaluation ? (
            <>
              <div className="wf-kpis">
                <div><b>{alertCount}</b><span>alerts shown</span></div>
                <div className={evaluation.recall < 0.8 ? "warn" : "good"}><b>{pct(evaluation.recall)}</b><span>behaviours caught</span></div>
                <div className={evaluation.precision < 0.7 ? "warn" : "good"}><b>{pct(evaluation.precision)}</b><span>{evaluation.real_background ? "alerts on added events" : "alerts that were real"}</span></div>
                <div><b>{evaluation.false_alarms}</b><span>{evaluation.real_background ? "unverified" : "false alarms"}</span></div>
              </div>
              <table className="wf-eval-table">
                <thead>
                  <tr><th>Injected behaviour</th><th>Caught</th></tr>
                </thead>
                <tbody>
                  {Object.entries(evaluation.per_kind).map(([k, v]) => (
                    <tr key={k} className={v.detected < v.truth ? "miss" : ""}>
                      <td>{kindMeta(k).label !== k ? kindMeta(k).label : k.replace(/_/g, " ")}</td>
                      <td>{v.detected}/{v.truth}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="wf-fine">
                {evaluation.real_background
                  ? "Background traffic is genuine recorded AIS, so alerts on vessels we did not touch are 'unverified' - they may be real oddities or routine behaviour nobody labelled. Only the added behaviours have known answers."
                  : "Includes benign look-alikes (fishing fleets, anchorages, a vessel sheltering from weather, satellite-only gaps) so false alarms are measured, not assumed."}
                {evaluation.false_alarms_on_benign_lookalikes > 0 && ` ${evaluation.false_alarms_on_benign_lookalikes} false alarm(s) came from those look-alikes.`}
              </p>
              <label className="wf-check">
                <input type="checkbox" checked={showTruth} onChange={(e) => onShowTruth(e.target.checked)} />
                Reveal ground-truth locations on the map
              </label>
            </>
          ) : (
            <p className="wf-fine">Evaluating…</p>
          )}
        </div>
      </div>
    </section>
  );
}

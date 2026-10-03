import { FactorCards } from "./Insight";
import { useState } from "react";
import type { AlertDetail, ReviewStatus } from "./api";
import { ConfidenceMeter, RiskGauge } from "./Gauge";
import { FLAG_NAME, KIND_META, LEVEL_COLOR, STATUS_LABEL, fmtClock, fmtDur, fmtHM, fmtPos, kindMeta } from "./lib";

interface Props {
  detail: AlertDetail | null;
  loading: boolean;
  busy: boolean;
  onStatus: (status: ReviewStatus, note?: string) => Promise<void>;
  onNote: (text: string) => Promise<void>;
  onClose: () => void;
}

export function AlertPanel({ detail, loading, busy, onStatus, onNote, onClose }: Props) {
  const [note, setNote] = useState("");
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");

  if (!detail) {
    return (
      <aside className="wf-detail wf-detail-empty" aria-label="Alert detail">
        <div className="wf-hint">
          <div className="wf-hint-icon" aria-hidden>◎</div>
          <h2>{loading ? "Loading alert…" : "Select an alert"}</h2>
          <p>
            Each alert shows <b>why</b> it was raised, the <b>evidence timeline</b>, what <b>else</b> could explain it and what the
            data <b>cannot</b> tell you — before you decide.
          </p>
          <p className="wf-fine">Alerts are candidates for human review. Nothing here is a finding of intent or wrongdoing.</p>
        </div>
      </aside>
    );
  }

  const color = LEVEL_COLOR[detail.level];
  const done = detail.status === "false_alarm";

  return (
    <aside className="wf-detail" aria-label="Alert detail">
      <header className="wf-detail-head" style={{ ["--c" as string]: color }}>
        <button className="wf-x" onClick={onClose} aria-label="Close alert">
          ✕
        </button>
        <RiskGauge risk={detail.risk} level={detail.level} size={76} />
        <div>
          <div className="wf-detail-id">
            {detail.id} · <span className={`wf-status st-${detail.status}`}>{STATUS_LABEL[detail.status]}</span>
          </div>
          <h2>{detail.title}</h2>
          <ConfidenceMeter value={detail.confidence} />
        </div>
      </header>

      <div className="wf-scroll">
        {detail.suppressed_by_feedback && (
          <div className="wf-callout learned">
            <b>Down-weighted by operator feedback.</b> {detail.suppressed_by_feedback}.
          </div>
        )}

        <section className="wf-action" style={{ ["--c" as string]: color }}>
          <h3>Recommended action</h3>
          <p>{detail.recommended_action}</p>
        </section>

        <section>
          <h3>Vessels involved</h3>
          <ul className="wf-vessels">
            {detail.vessels.map((v) => (
              <li key={v.mmsi}>
                <b>{v.name}</b>
                <span>
                  {v.type} · {FLAG_NAME[v.flag] ?? v.flag} · MMSI {v.mmsi}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3>Why it was flagged</h3>
          <ol className="wf-reasons">
            {detail.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ol>
        </section>

        <section>
          <h3>What drives the score</h3>
          <div className="wf-breakdown">
            {detail.breakdown.map((b) => (
              <div key={b.kind} className="wf-bd-row" title={kindMeta(b.kind).what}>
                <span className="wf-bd-label" style={{ ["--c" as string]: kindMeta(b.kind).color }}>
                  {b.label}
                </span>
                <span className="wf-bd-bar">
                  <i style={{ width: `${Math.min(100, b.severity)}%`, background: kindMeta(b.kind).color }} />
                </span>
                <span className="wf-bd-val">
                  {b.severity.toFixed(0)}
                  <small> sev · {Math.round(b.confidence * 100)}% conf</small>
                </span>
              </div>
            ))}
          </div>
          <p className="wf-fine">Risk combines behaviours as independent evidence (noisy-OR), weighted by data confidence. It is a review priority, not a probability of wrongdoing.</p>
        </section>

        {detail.ml?.available && (
          <section className={`wf-ml ${detail.ml.agreement}`}>
            <h3>Statistical second opinion</h3>
            <p>
              <b>{detail.ml.agreement === "agree" ? "Model agrees" : "Rules only"}</b> - {detail.ml.note}
            </p>
            <div className="wf-ml-scores">
              <span>Anomaly score <b>{detail.ml.if_score?.toFixed(0)}</b>/100 <small>(unsupervised)</small></span>
              <span>Behaviour match <b>{detail.ml.gb_score?.toFixed(0)}</b>/100 <small>(supervised)</small></span>
            </div>
            {detail.ml.deviations && detail.ml.deviations.length > 0 && (
              <ul className="wf-bullets">
                {detail.ml.deviations.map((d) => (
                  <li key={d.label}>
                    {d.label}: <b>{d.value}{d.unit && ` ${d.unit}`}</b> vs typical {d.typical}{d.unit && ` ${d.unit}`}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <section>
          <h3>Event timeline</h3>
          <ol className="wf-timeline">
            {detail.timeline.map((e, i) => {
              const m = KIND_META[e.kind];
              return (
                <li key={e.id} style={{ ["--c" as string]: m?.color ?? "#adb5bd" }}>
                  <span className="wf-tl-n">{i + 1}</span>
                  <div>
                    <div className="wf-tl-top">
                      <b>{m?.label ?? e.kind}</b>
                      <span>
                        {fmtClock(e.t_start)} → {fmtHM(e.t_end)} · {fmtDur(e.t_end - e.t_start)}
                      </span>
                    </div>
                    <div className="wf-tl-sum">{e.summary}</div>
                    {e.kind === "survey_threat" && <FactorCards metrics={e.metrics} />}
                    <div className="wf-tl-meta">
                      {fmtPos(e.lat, e.lon)} · severity {e.severity.toFixed(0)} · confidence {Math.round(e.confidence * 100)}%
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="wf-two">
          <div>
            <h3>Could also be</h3>
            <ul className="wf-bullets benign">
              {detail.benign_explanations.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3>What we can’t tell</h3>
            <ul className="wf-bullets unknown">
              {detail.uncertainty.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
        </section>

        <section className="wf-ops">
          <h3>Operator decision</h3>
          {!dismissing ? (
            <div className="wf-ops-btns">
              <button disabled={busy} className="b-review" onClick={() => onStatus("under_review")}>
                Under review
              </button>
              <button disabled={busy} className="b-confirm" onClick={() => onStatus("confirmed")}>
                Confirm
              </button>
              <button disabled={busy} className="b-escalate" onClick={() => onStatus("escalated")}>
                Escalate
              </button>
              <button disabled={busy || done} className="b-fa" onClick={() => setDismissing(true)}>
                False alarm
              </button>
            </div>
          ) : (
            <div className="wf-dismiss">
              <label htmlFor="fa-reason">Why is this a false alarm? (helps the system learn)</label>
              <select id="fa-reason" value={reason} onChange={(e) => setReason(e.target.value)}>
                <option value="">Select a reason…</option>
                <option>Known fishing activity</option>
                <option>Weather shelter / hove-to</option>
                <option>Known coverage gap or receiver outage</option>
                <option>Authorised vessel / operation</option>
                <option>Port or anchorage activity</option>
                <option>Other</option>
              </select>
              <div className="wf-ops-btns">
                <button
                  disabled={busy || !reason}
                  className="b-fa"
                  onClick={async () => {
                    await onStatus("false_alarm", `False alarm: ${reason}`);
                    setDismissing(false);
                    setReason("");
                  }}
                >
                  Dismiss as false alarm
                </button>
                <button className="b-ghost" onClick={() => setDismissing(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          <ul className="wf-notes">
            {detail.notes.map((n, i) => (
              <li key={i} className={n.system ? "sys" : ""}>
                <span>
                  {n.operator} · {fmtClock(n.t)}
                </span>
                {n.text}
              </li>
            ))}
          </ul>
          <form
            className="wf-note-form"
            onSubmit={async (ev) => {
              ev.preventDefault();
              if (!note.trim()) return;
              await onNote(note.trim());
              setNote("");
            }}
          >
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note for the shift log…" maxLength={500} aria-label="Add a note" />
            <button type="submit" disabled={!note.trim() || busy}>
              Add
            </button>
          </form>
        </section>
      </div>
    </aside>
  );
}

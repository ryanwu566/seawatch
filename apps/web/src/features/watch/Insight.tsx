import { useEffect, useState } from "react";
import { watchApi, type Assessment, type Rulebook } from "./api";

type Tab = "assessment" | "rulebook";

const FACTOR = ["territory", "velocity", "declared", "pattern"] as const;

/** Full-screen explanation of what counts as suspicious, how well it is found, and how noise is removed. */
export function Insight({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("assessment");
  const [a, setA] = useState<Assessment | null>(null);
  const [r, setR] = useState<Rulebook | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    watchApi.rulebook().then(setR).catch((e: Error) => setErr(e.message));
    watchApi.assessment().then(setA).catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <div className="wf-insight" role="dialog" aria-label="Detection insight">
      <div className="wf-insight-bar">
        <div className="wf-tabs">
          <button className={tab === "assessment" ? "on" : ""} onClick={() => setTab("assessment")}>
            How well it works
          </button>
          <button className={tab === "rulebook" ? "on" : ""} onClick={() => setTab("rulebook")}>
            Rulebook: what is “suspicious”
          </button>
        </div>
        <button onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="wf-insight-body">
        {err && (
          <p className="wf-fine" role="alert">
            {err}
          </p>
        )}
        {tab === "assessment" ? (
          a ? (
            <AssessmentView a={a} />
          ) : (
            <p className="wf-fine">Computing… (the first run on a month of real traffic takes a minute)</p>
          )
        ) : r ? (
          <RulebookView r={r} />
        ) : (
          <p className="wf-fine">Loading…</p>
        )}
      </div>
    </div>
  );
}

function Bar({ v, max, label }: { v: number; max: number; label: string }) {
  return (
    <div className="wf-bar">
      <span>{label}</span>
      <div>
        <i style={{ width: `${Math.max(1, (100 * v) / Math.max(max, 1))}%` }} />
      </div>
      <b>{v.toLocaleString()}</b>
    </div>
  );
}

function AssessmentView({ a }: { a: Assessment }) {
  const max = a.funnel[0]?.count ?? 1;
  const ev = a.evaluation;
  const maxD = a.discards[0]?.count ?? 1;
  return (
    <>
      <section>
        <h3>1. From traffic to alerts (signal vs noise)</h3>
        <p className="wf-fine">Every stage drops the vessels that are ordinary. Only a small share of traffic reaches an alert.</p>
        {a.funnel.map((f) => (
          <Bar key={f.stage} v={f.count} max={max} label={f.stage} />
        ))}
        {a.ml_agreement.agree + a.ml_agreement.rules_only === 0 && (
          <p className="wf-fine">Statistical-model confirmation is not available for this run.</p>
        )}
      </section>

      <section>
        <h3>2. What was thrown away as normal, and why</h3>
        <p className="wf-fine">Cases a detector examined and discarded (this is the dense-traffic noise).</p>
        {a.discards.slice(0, 12).map((d) => (
          <Bar key={d.detector + d.reason} v={d.count} max={maxD} label={`${d.detector}: ${d.reason}`} />
        ))}
      </section>

      {a.factors && (
        <section>
          <h3>3. Survey-threat factors: single factors are common, combinations are rare</h3>
          <p className="wf-fine">
            Of {a.factors.single.foreign.toLocaleString()} foreign vessels: {a.factors.single.T.toLocaleString()} were inside Taiwan’s 24 nm,{" "}
            {a.factors.single.V.toLocaleString()} moved at survey speed, {a.factors.single.A} declare research, {a.factors.single.P} sailed a zig-zag pattern.
            T = territory, V = velocity, A = AIS declaration, P = pattern.
          </p>
          <table className="wf-table">
            <thead>
              <tr>
                <th>T</th>
                <th>V</th>
                <th>A</th>
                <th>P</th>
                <th>vessels</th>
              </tr>
            </thead>
            <tbody>
              {a.factors.combinations.slice(0, 10).map((c, i) => (
                <tr key={i} className={c.factors_met >= 3 ? "hot" : ""}>
                  {FACTOR.map((k) => (
                    <td key={k}>{c[k] ? "●" : "·"}</td>
                  ))}
                  <td>{c.vessels.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section>
        <h3>4. What it identified</h3>
        {Object.keys(a.threat_classes).length === 0 && <p className="wf-fine">No survey-threat classification in this scenario.</p>}
        {Object.entries(a.threat_classes).map(([k, n]) => (
          <Bar key={k} v={n} max={Math.max(...Object.values(a.threat_classes))} label={k} />
        ))}
        <ul className="wf-bullets">
          {a.threat_top.slice(0, 8).map((t) => (
            <li key={t.mmsi + t.rule}>
              <b>{t.name || t.mmsi}</b> · rule {t.rule} · severity {t.severity.toFixed(0)}: {t.classification}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>5. Measured accuracy on labelled behaviours</h3>
        <p className="wf-fine">
          Real traffic plus added labelled events: precision {Math.round(ev.precision * 100)}%, recall {Math.round(ev.recall * 100)}%, {ev.alerts} alerts, of
          which {ev.true_alerts} match an added event. The rest are unverified real vessels (not necessarily false alarms).
        </p>
        {Object.entries(ev.per_kind).map(([k, v]) => (
          <Bar key={k} v={v.detected} max={Math.max(v.truth, 1)} label={`${k}: ${v.detected} of ${v.truth} found`} />
        ))}
        <p className="wf-fine">Real labels (sanctions, reported research vessels) show no behavioural separability: see docs/real-outcomes.md.</p>
      </section>
    </>
  );
}

function RulebookView({ r }: { r: Rulebook }) {
  const t = r.threat_model;
  return (
    <>
      <p className="wf-fine">{r.principle}</p>
      <section>
        <h3>{t.title}</h3>
        <p>{t.premise}</p>
        <div className="wf-factors">
          {t.factors.map((f) => (
            <div key={f.code} className="wf-factor">
              <b>
                {f.code} · {f.name}
              </b>
              <p>{f.rule}</p>
              <p className="wf-fine">{f.note}</p>
            </div>
          ))}
        </div>
        <table className="wf-table">
          <thead>
            <tr>
              <th>rule</th>
              <th>classification</th>
              <th>needs</th>
              <th>severity</th>
            </tr>
          </thead>
          <tbody>
            {t.rules.map((x) => (
              <tr key={x.id}>
                <td>{x.id}</td>
                <td>
                  {x.name}
                  <div className="wf-fine">{x.meaning}</div>
                </td>
                <td>{x.needs}</td>
                <td>{x.severity}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="wf-fine">{t.noise}</p>
        <p className="wf-fine">{t.legal}</p>
      </section>
      <section>
        <h3>Behaviour detectors</h3>
        {r.detectors.map((d) => (
          <details key={d.id}>
            <summary>
              <b>{d.name}</b>: {d.sees}
            </summary>
            <p>
              <b>Why it matters:</b> {d.why}
            </p>
            {Object.keys(d.thresholds).length > 0 && (
              <p>
                <b>Thresholds:</b> {Object.entries(d.thresholds).map(([k, v]) => `${k} = ${v}`).join("; ")}
              </p>
            )}
            {d.discards.length > 0 && (
              <p>
                <b>Discarded as noise:</b> {d.discards.join("; ")}
              </p>
            )}
            <p>
              <b>Innocent explanations:</b> {d.benign.join("; ")}
            </p>
            <p className="wf-fine">{d.data}</p>
          </details>
        ))}
      </section>
      <section>
        <h3>From events to alerts</h3>
        <ul className="wf-bullets">
          {Object.entries(r.fusion).map(([k, v]) => (
            <li key={k}>
              <b>{k}:</b> {typeof v === "string" ? v : Object.entries(v).map(([x, y]) => `${x} ${y}`).join(" · ")}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

type F = { met: boolean } & Record<string, unknown>;

/** T / V / A / P cards for one survey-threat event. */
export function FactorCards({ metrics }: { metrics: Record<string, unknown> }) {
  const f = metrics.factors as Record<string, F> | undefined;
  if (!f) return null;
  const t = f.territory;
  const v = f.velocity;
  const d = f.declared;
  const p = f.pattern;
  const band = v.band_kn as number[];
  const card = (code: string, name: string, x: F, text: string) => (
    <div className={`wf-fc ${x.met ? "met" : ""}`} title={name}>
      <b>
        {code} {x.met ? "✓" : "–"}
      </b>
      <span>{text}</span>
    </div>
  );
  return (
    <div className="wf-fcs" aria-label="Threat factors">
      {card("T", "Territory", t, `${String(t.ts_fixes)} fixes ≤12 nm, ${String(t.cz_fixes)} to 24 nm, ${String(t.eez_fixes)} in EEZ`)}
      {card("V", "Velocity", v, `${Math.round(Number(v.share_in_band) * 100)}% of fixes at ${band[0]}–${band[1]} kn`)}
      {card("A", "AIS declaration", d, d.met ? "declares survey / research" : "no declaration")}
      {card("P", "Pattern", p, p.met ? `${String(p.legs)} zig-zag legs` : "no pattern")}
    </div>
  );
}

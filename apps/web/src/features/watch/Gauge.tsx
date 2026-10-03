import type { Level } from "./api";
import { LEVEL_COLOR, confidenceLabel } from "./lib";

/** Circular risk score. Colour AND text carry the level, so it never relies on colour alone. */
export function RiskGauge({ risk, level, size = 64 }: { risk: number; level: Level; size?: number }) {
  const r = size / 2 - 5;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, risk / 100));
  const color = LEVEL_COLOR[level];
  return (
    <div className="wf-gauge" style={{ width: size, height: size }} role="img" aria-label={`Risk score ${Math.round(risk)} out of 100, ${level}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(148,163,184,.18)" strokeWidth="5" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${c * frac} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="wf-gauge-num" style={{ color }}>
        <b>{Math.round(risk)}</b>
        <small>{level}</small>
      </div>
    </div>
  );
}

/** Five-segment evidence-quality meter with an explicit word. */
export function ConfidenceMeter({ value }: { value: number }) {
  const segs = Math.round(value * 5);
  return (
    <span className="wf-conf" title="How complete and clean the underlying AIS evidence is. Not the probability that the vessel is doing something wrong.">
      <span className="wf-conf-bar" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (
          <i key={i} className={i < segs ? "on" : ""} />
        ))}
      </span>
      <span>{confidenceLabel(value)} data confidence</span>
    </span>
  );
}

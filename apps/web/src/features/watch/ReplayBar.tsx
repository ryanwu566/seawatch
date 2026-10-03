import type { AlertSummary, Scenario } from "./api";
import { LEVEL_COLOR, fmtClock } from "./lib";
import { SPEEDS } from "./useWatch";

interface Props {
  scenario: Scenario;
  clock: number;
  playing: boolean;
  speed: number;
  alerts: AlertSummary[];
  selectedId: string | null;
  onClock: (t: number) => void;
  onPlay: (p: boolean) => void;
  onSpeed: (s: number) => void;
  onSelect: (id: string) => void;
}

export function ReplayBar({ scenario, clock, playing, speed, alerts, selectedId, onClock, onPlay, onSpeed, onSelect }: Props) {
  const span = scenario.t1 - scenario.t0;
  const pos = (t: number) => `${((t - scenario.t0) / span) * 100}%`;
  const hours = Array.from({ length: Math.floor(span / 3600 / 6) + 1 }, (_, i) => scenario.t0 + i * 6 * 3600);

  return (
    <footer className="wf-replay" aria-label="Replay control">
      <div className="wf-replay-btns">
        <button
          className="wf-play"
          onClick={() => {
            if (!playing && clock >= scenario.t1) onClock(scenario.t0);
            onPlay(!playing);
          }}
          aria-label={playing ? "Pause replay" : "Play replay"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="wf-speed" role="group" aria-label="Replay speed">
          {SPEEDS.map((s) => (
            <button key={s.sec} className={speed === s.sec ? "on" : ""} onClick={() => onSpeed(s.sec)}>
              {s.label}
            </button>
          ))}
        </div>
        <button className="wf-live" onClick={() => { onPlay(false); onClock(scenario.t1); }} title="Jump to the end of the simulated period">
          ⏭ End
        </button>
      </div>

      <div className="wf-track">
        <div className="wf-ticks" aria-hidden>
          {hours.map((h) => (
            <span key={h} style={{ left: pos(h) }}>
              {fmtClock(h)}
            </span>
          ))}
        </div>
        <div className="wf-marks">
          {alerts.map((a) => (
            <button
              key={a.id}
              className={`wf-mark ${a.id === selectedId ? "sel" : ""}`}
              style={{ left: pos(a.raised_at), background: LEVEL_COLOR[a.level] }}
              title={`${a.level} · ${a.title}`}
              onClick={() => {
                onPlay(false);
                onClock(Math.max(a.raised_at, scenario.t0));
                onSelect(a.id);
              }}
              aria-label={`Jump to alert: ${a.title}`}
            />
          ))}
        </div>
        <input
          type="range"
          min={scenario.t0}
          max={scenario.t1}
          step={60}
          value={clock}
          onChange={(e) => {
            onPlay(false);
            onClock(Number(e.target.value));
          }}
          aria-label="Simulation time"
        />
      </div>

      <div className="wf-now" aria-live="off">
        <small>Taiwan time</small>
        <b>{fmtClock(clock)}</b>
      </div>
    </footer>
  );
}

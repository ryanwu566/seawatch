import { useMemo, useState } from "react";
import type { AlertSummary, Level } from "./api";
import { RiskGauge } from "./Gauge";
import { LEVEL_COLOR, STATUS_LABEL, ago, kindMeta } from "./lib";

interface Props {
  alerts: AlertSummary[];
  dismissed: AlertSummary[];
  selectedId: string | null;
  clock: number;
  onSelect: (id: string) => void;
}

const LEVELS: Level[] = ["HIGH", "MEDIUM", "LOW"];

export function AlertQueue({ alerts, dismissed, selectedId, clock, onSelect }: Props) {
  const [filter, setFilter] = useState<Level | "ALL">("ALL");
  const [tab, setTab] = useState<"active" | "dismissed">("active");

  const counts = useMemo(() => {
    const c: Record<Level, number> = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    alerts.forEach((a) => (c[a.level] += 1));
    return c;
  }, [alerts]);

  const list = tab === "active" ? alerts.filter((a) => filter === "ALL" || a.level === filter) : dismissed;

  return (
    <aside className="wf-queue" aria-label="Alert queue">
      <header className="wf-panel-head">
        <h2>Alert queue</h2>
        <div className="wf-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "active"} className={tab === "active" ? "on" : ""} onClick={() => setTab("active")}>
            Active <b>{alerts.length}</b>
          </button>
          <button role="tab" aria-selected={tab === "dismissed"} className={tab === "dismissed" ? "on" : ""} onClick={() => setTab("dismissed")}>
            Dismissed <b>{dismissed.length}</b>
          </button>
        </div>
      </header>

      {tab === "active" && (
        <div className="wf-filters" role="group" aria-label="Filter by risk level">
          <button className={filter === "ALL" ? "on" : ""} onClick={() => setFilter("ALL")}>
            All
          </button>
          {LEVELS.map((l) => (
            <button key={l} className={filter === l ? "on" : ""} onClick={() => setFilter(l)} style={{ ["--c" as string]: LEVEL_COLOR[l] }}>
              <i /> {l[0] + l.slice(1).toLowerCase()} <b>{counts[l]}</b>
            </button>
          ))}
        </div>
      )}

      <div className="wf-list">
        {list.length === 0 && (
          <p className="wf-empty">
            {tab === "active"
              ? alerts.length === 0
                ? "Nothing needs review at this moment. Press ▶ to replay the simulated 36 hours."
                : "No alerts at this level."
              : "Alerts you mark as false alarms appear here, and the system learns to down-weight similar ones."}
          </p>
        )}
        {list.map((a) => (
          <button
            key={a.id}
            className={`wf-card lv-${a.level.toLowerCase()} ${a.id === selectedId ? "sel" : ""} ${a.status !== "new" ? "reviewed" : ""}`}
            onClick={() => onSelect(a.id)}
            aria-pressed={a.id === selectedId}
          >
            <RiskGauge risk={a.risk} level={a.level} size={54} />
            <div className="wf-card-body">
              <div className="wf-card-title">{a.title}</div>
              <div className="wf-card-reason">{a.top_reason}</div>
              <div className="wf-card-meta">
                {a.kinds.slice(0, 3).map((k) => (
                  <span key={k} className="wf-chip" style={{ ["--c" as string]: kindMeta(k).color }}>
                    {kindMeta(k).short}
                  </span>
                ))}
                <span className="wf-time">{ago(clock, a.raised_at)}</span>
                {a.status !== "new" && <span className={`wf-status st-${a.status}`}>{STATUS_LABEL[a.status]}</span>}
                {a.suppressed_by_feedback && <span className="wf-status st-learned" title={a.suppressed_by_feedback}>↓ learned</span>}
              </div>
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}

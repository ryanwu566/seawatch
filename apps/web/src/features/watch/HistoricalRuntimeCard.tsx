import { useEffect, useState } from "react";
import {
  getHistoricalRuntimeSummary,
  type HistoricalDateRange,
  type HistoricalRuntimeSummary,
} from "../../api/historicalRuntime";


type CountStyle = "compact" | "grouped";
type CardState =
  | { status: "loading" }
  | { status: "available"; summary: HistoricalRuntimeSummary }
  | { status: "unavailable" };

const integerFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});


export function formatHistoricalCount(
  value: number | null | undefined,
  style: CountStyle,
): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return "—";
  }
  if (style === "grouped") return integerFormat.format(value);
  if (value >= 1_000_000) return `${stripTrailingZero(value / 1_000_000)}M`;
  if (value >= 1_000) return `${stripTrailingZero(value / 1_000)}K`;
  return integerFormat.format(value);
}


function stripTrailingZero(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}


function isoDay(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = value.match(
    /^(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$/,
  );
  if (!match) return null;
  const day = match[1];
  const parsedDay = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(parsedDay.valueOf()) || parsedDay.toISOString().slice(0, 10) !== day) {
    return null;
  }
  return Number.isNaN(new Date(value.length === 10 ? `${value}T00:00:00Z` : value).valueOf())
    ? null
    : day;
}


function normalizedRange(
  value: HistoricalRuntimeSummary["date_range"],
): HistoricalDateRange | null {
  if (Array.isArray(value)) {
    const start = isoDay(value[0]);
    const end = isoDay(value[1]);
    return start && end ? { start, end } : null;
  }
  if (value !== null && typeof value === "object") {
    const start = isoDay(value.start) ?? isoDay(value.startUtc);
    const end = isoDay(value.end) ?? isoDay(value.endUtc);
    return start && end ? { start, end } : null;
  }
  return null;
}


function formatCoverage(value: HistoricalRuntimeSummary["date_range"]): string {
  const range = normalizedRange(value);
  if (!range?.start || !range.end) return "Coverage unavailable";

  const start = new Date(`${range.start}T00:00:00Z`);
  const end = new Date(`${range.end}T00:00:00Z`);
  if (Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf())) {
    return "Coverage unavailable";
  }
  const day = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  const year = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    timeZone: "UTC",
  });
  if (start.getUTCFullYear() === end.getUTCFullYear()) {
    return `${day.format(start)}–${day.format(end)}, ${year.format(end)} coverage`;
  }
  return `${day.format(start)}, ${year.format(start)}–${day.format(end)}, ${year.format(end)} coverage`;
}


export function HistoricalRuntimeCard() {
  const [state, setState] = useState<CardState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getHistoricalRuntimeSummary(controller.signal)
      .then((summary) => {
        if (controller.signal.aborted) return;
        setState(
          summary.available
            ? { status: "available", summary }
            : { status: "unavailable" },
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "unavailable" });
      });
    return () => controller.abort();
  }, []);

  if (state.status === "loading") {
    return (
      <section className="wf-history is-loading" aria-label="Historical Runtime">
        <div className="wf-history-state" role="status">
          <span className="wf-spin" aria-hidden="true" />
          Loading historical context
        </div>
      </section>
    );
  }

  if (state.status === "unavailable") {
    return (
      <section className="wf-history is-unavailable" aria-label="Historical Runtime">
        <div className="wf-history-state">Historical context unavailable</div>
      </section>
    );
  }

  const { summary } = state;
  const candidateCount =
    summary.mmsi_join_status_counts?.unique_9digit_candidate;
  const runtimeLabel = summary.runtime === "SeaWatch_Runtime_Taiwan_2026_v2"
    ? summary.runtime
    : "Historical Runtime v2";

  return (
    <section className="wf-history is-available" aria-label="Historical Runtime">
      <div className="wf-history-head">
        <div>
          <strong>Historical context available</strong>
          <span>{runtimeLabel}</span>
        </div>
        <i aria-hidden="true" />
      </div>
      <p className="wf-history-coverage">{formatCoverage(summary.date_range)}</p>
      <div className="wf-history-stats">
        <div>
          <b>{formatHistoricalCount(summary.row_count, "compact")}</b>
          <span>historical presence observations</span>
        </div>
        <div>
          <b>{formatHistoricalCount(summary.unique_vessel_count, "compact")}</b>
          <span>vessels</span>
        </div>
        <div>
          <b>{formatHistoricalCount(summary.traffic_cell_count, "grouped")}</b>
          <span>traffic cells</span>
        </div>
        <div>
          <b>{formatHistoricalCount(summary.dataset_hour_buckets, "grouped")}</b>
          <span>hourly buckets</span>
        </div>
        <div title="Conservative cross-source join candidates">
          <b>{formatHistoricalCount(candidateCount, "grouped")}</b>
          <span>conservative join candidates</span>
        </div>
      </div>
      <p className="wf-history-source">GFW standardized hourly vessel presence</p>
      <p className="wf-history-disclaimer">Not raw/message-level AIS</p>
      <p className="wf-history-note">
        Only dataset-internal one-to-one nine-digit MMSI candidates are eligible
        for conservative cross-source matching.
      </p>
    </section>
  );
}

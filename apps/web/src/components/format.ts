// Small presentation helpers. No business logic is duplicated from the backend.

/** Format a review priority score (0-100 ranking value) as a percentage label. */
export function formatPriority(score: number): string {
  const clamped = Math.max(0, Math.min(100, score));
  return `${Math.round(clamped)}%`;
}

/** Format a duration in seconds as a compact H:MM:SS / M:SS string. */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

/** Format a percentile (0..1) as a percentage label. */
export function formatPercentile(p: number): string {
  if (!Number.isFinite(p)) {
    return "—";
  }
  return `${(p * 100).toFixed(1)}%`;
}

/** Format a numeric value with an optional unit. */
export function formatValue(value: number, unit: string): string {
  const num = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return unit ? `${num} ${unit}` : num;
}

/** Optional fraction (0..1) or null -> percentage label. */
export function formatFraction(fraction: number | null): string {
  if (fraction === null || !Number.isFinite(fraction)) {
    return "—";
  }
  return `${(fraction * 100).toFixed(0)}%`;
}

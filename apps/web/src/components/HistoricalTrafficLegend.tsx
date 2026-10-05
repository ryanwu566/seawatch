export function HistoricalTrafficLegend() {
  return (
    <aside className="historical-traffic-legend" aria-label="Historical presence legend">
      <strong>Historical Traffic Density</strong>
      <div className="historical-traffic-scale" aria-label="Relative historical presence from low to high">
        <span>Low</span>
        <i aria-hidden="true" />
        <span>High</span>
      </div>
      <p>standardized hourly vessel presence · ~0.1° cells · not raw/message-level AIS</p>
    </aside>
  );
}

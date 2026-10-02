import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../../i18n/I18nContext";
import { MapCanvas } from "../../components/MapCanvas";
import { DEFAULT_LAYER_STATE } from "../../lib/layerState";
import { buildLogisticsOverlays } from "./logisticsLayers";
import {
  fetchScenarioContext,
  fetchScenarios,
  runSimulation,
} from "./logisticsApi";
import type {
  DecisionBrief,
  ScenarioContext,
  ScenarioSummary,
} from "./logisticsTypes";

/**
 * Resilience Logistics (RESPOND) view: scenario select → load context →
 * Run Simulation → render the decision brief. Reuses the shared getBaseUrl API
 * client. The result panel (allocation table, brief, TruthBadge) is provided by
 * Slice I via the LogisticsPanel component; this view owns orchestration.
 */
export function LogisticsView({
  renderResult,
}: {
  // Injected by Slice I. Kept optional so Slice G stands alone.
  renderResult?: (args: {
    context: ScenarioContext | null;
    brief: DecisionBrief | null;
  }) => React.ReactNode;
}) {
  const { t, lang } = useI18n();
  const L = t.logistics;

  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [context, setContext] = useState<ScenarioContext | null>(null);
  const [brief, setBrief] = useState<DecisionBrief | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load the scenario list once.
  useEffect(() => {
    const ctrl = new AbortController();
    fetchScenarios(ctrl.signal)
      .then((res) => {
        setScenarios(res.scenarios);
        if (res.scenarios.length > 0) {
          setSelectedId((prev) => prev || res.scenarios[0].id);
        }
      })
      .catch(() => setError(L.loadError));
    return () => ctrl.abort();
  }, [L.loadError]);

  // Load context whenever the selected scenario changes.
  useEffect(() => {
    if (!selectedId) return;
    const ctrl = new AbortController();
    setBrief(null);
    fetchScenarioContext(selectedId, ctrl.signal)
      .then(setContext)
      .catch(() => setError(L.loadError));
    return () => ctrl.abort();
  }, [selectedId, L.loadError]);

  const onRun = useCallback(() => {
    if (!selectedId) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);
    setError(null);
    runSimulation(selectedId, undefined, ctrl.signal)
      .then((result) => setBrief(result))
      .catch(() => setError(L.loadError))
      .finally(() => setRunning(false));
  }, [selectedId, L.loadError]);

  const scenarioName = (s: ScenarioSummary) => (lang === "zh-Hant" ? s.name_zh : s.name_en);

  // Build the generic overlay payload fed into the reused Phase 8 MapCanvas
  // seam. Logistics owns all map-specific knowledge in logisticsLayers.ts.
  const overlays = useMemo(
    () => buildLogisticsOverlays(context, brief?.recommended_allocations ?? []),
    [context, brief],
  );

  return (
    <section className="logistics-view" aria-label={L.title}>
      <header className="logistics-header">
        <h1>{L.title}</h1>
        <p className="logistics-subtitle">{L.subtitle}</p>
      </header>

      <div className="logistics-controls">
        <label htmlFor="logistics-scenario">{L.scenarioLabel}</label>
        <select
          id="logistics-scenario"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          aria-label={L.selectScenario}
        >
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {scenarioName(s)}
            </option>
          ))}
        </select>

        <button type="button" onClick={onRun} disabled={!selectedId || running}>
          {running ? L.running : L.runSimulation}
        </button>
      </div>

      {context && (
        <div className="logistics-context">
          <p>
            <strong>{L.disruptedPort}:</strong>{" "}
            {context.scenario.disrupted_ports.join(", ")}
          </p>
          <ul className="logistics-demand-list">
            {context.affected_demands.map((d) => (
              <li key={d.id}>
                {commodityLabel(d.commodity, L)} ({L.priority} {d.priority})
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p role="alert" className="logistics-error">{error}</p>}

      <div className="logistics-map-shell">
        <MapCanvas
          vessels={[]}
          layers={DEFAULT_LAYER_STATE}
          selectedId={null}
          selectedTrack={null}
          follow={false}
          onSelectVessel={noop}
          onDeselect={noop}
          onViewportChange={noop}
          overlays={overlays}
        />
      </div>

      <div className="logistics-result" data-has-result={brief ? "true" : "false"}>
        {renderResult ? renderResult({ context, brief }) : null}
      </div>
    </section>
  );
}

function noop() {
  /* no-op: the logistics map is read-only context, not an interactive selector */
}

function commodityLabel(commodity: string, L: ReturnType<typeof useI18n>["t"]["logistics"]) {
  switch (commodity) {
    case "medical":
      return L.commodityMedical;
    case "food":
      return L.commodityFood;
    case "fuel":
      return L.commodityFuel;
    default:
      return commodity;
  }
}

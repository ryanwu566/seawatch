import { useI18n } from "../../i18n/I18nContext";
import { TruthBadge } from "./TruthBadge";
import type { DecisionBrief, ScenarioContext } from "./logisticsTypes";

/**
 * Results panel for the Resilience Logistics view. Renders, from the structured
 * typed response (never parsed prose):
 *  - the recommended allocation table with split rows (one per port assignment);
 *  - the per-port alternatives comparison (ETA / distance / scenario cost /
 *    capacity utilization / risk);
 *  - the bilingual Decision Brief summary and trade-offs;
 *  - unmet demand when present;
 *  - an ALWAYS-VISIBLE TruthBadge derived from provenance_summary + note.
 *
 * Nothing here upgrades provenance or presents scenario/synthetic figures as
 * real data; the TruthBadge is rendered unconditionally whenever a brief exists.
 */
export function LogisticsPanel({
  context: _context,
  brief,
}: {
  context: ScenarioContext | null;
  brief: DecisionBrief | null;
}) {
  const { t, lang } = useI18n();
  const L = t.logistics;

  if (!brief) return null;

  const summary = lang === "zh-Hant" ? brief.summary_zh : brief.summary_en;
  const returnedText = (value: string) =>
    lang === "zh-Hant" ? value : englishOnlyText(value);
  const routedTotal = brief.recommended_allocations.reduce(
    (total, allocation) => total + allocation.satisfied_units,
    0,
  );
  const unmetTotal = brief.unmet_demand.reduce(
    (total, demand) => total + demand.unmet_units,
    0,
  );
  const priorityAllocation = brief.recommended_allocations[0];

  return (
    <div className="logistics-panel" data-testid="logistics-panel">
      <section className="decision-brief-hero" aria-label={L.decisionBrief}>
        <div className="decision-brief-heading">
          <span>{L.decisionBrief}</span>
          <h2>{summary}</h2>
        </div>
        <div className="decision-kpis">
          <div><span>{L.routedTotal}</span><strong>{routedTotal}</strong></div>
          <div><span>{L.unmetTotal}</span><strong>{unmetTotal}</strong></div>
        </div>
        {priorityAllocation && priorityAllocation.assignments.length > 0 ? (
          <div className="priority-allocation">
            <span>{L.highestPriority}</span>
            <strong>{demandLabel(priorityAllocation.demand_id, L)}</strong>
            <p>{priorityAllocation.satisfied_units} {L.colUnits}</p>
            <ul>
              {priorityAllocation.assignments.map((assignment, index) => (
                <li key={`${assignment.port_id}-${index}`}>
                  {assignment.units} {L.colUnits} {L.allocationTo}{" "}
                  <b>{assignment.port_id}</b>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="decision-tradeoffs">
          <h3>{L.tradeOffs}</h3>
          <ul className="logistics-tradeoffs">
            {brief.trade_offs.map(returnedText).filter(Boolean).map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
        <TruthBadge
          provenanceSummary={brief.provenance_summary}
          provenanceNote={returnedText(brief.provenance_note)}
        />
      </section>

      <h2 className="supporting-detail-heading">{L.supportingDetail}</h2>
      {/* Alternatives comparison (per-port metrics). */}
      <section className="logistics-alternatives" aria-label={L.alternatives}>
        <h2>{L.alternatives}</h2>
        <table>
          <thead>
            <tr>
              <th>{L.colPort}</th>
              <th>{L.colEta}</th>
              <th>{L.colDistance}</th>
              <th>{L.colCost}</th>
              <th>{L.colCapacity}</th>
              <th>{L.colRisk}</th>
            </tr>
          </thead>
          <tbody>
            {brief.alternatives.map((row) => (
              <tr key={row.port_id} data-port={row.port_id}>
                <td>
                  {lang === "zh-Hant" ? row.port_label : englishPortLabel(row.port_label, row.port_id)}
                  {row.schematic && row.schematic_label ? (
                    <span className="schematic-flag"> · {L.schematicConnector}</span>
                  ) : null}
                </td>
                <td>
                  {row.eta_hours} {L.etaHours}
                </td>
                <td>
                  {row.distance_km} {L.distanceKm}
                </td>
                <td>{row.per_unit_cost}</td>
                <td>{Math.round(row.capacity_utilization * 100)}%</td>
                <td>{row.risk}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Recommended allocation table with split rows (one per assignment). */}
      <section className="logistics-allocation" aria-label={L.recommendedAllocation}>
        <h2>{L.recommendedAllocation}</h2>
        <table>
          <thead>
            <tr>
              <th>{L.criticalDemand}</th>
              <th>{L.colPort}</th>
              <th>{L.colUnits}</th>
              <th>{L.colEta}</th>
              <th>{L.colCost}</th>
              <th>{L.colRisk}</th>
            </tr>
          </thead>
          <tbody>
            {brief.recommended_allocations.flatMap((alloc) =>
              alloc.assignments.map((asg, idx) => (
                <tr key={`${alloc.demand_id}-${asg.port_id}-${idx}`} data-demand={alloc.demand_id}>
                  <td>{demandLabel(alloc.demand_id, L)}</td>
                  <td>{asg.port_id}</td>
                  <td>{asg.units}</td>
                  <td>
                    {asg.eta_hours} {L.etaHours}
                  </td>
                  <td>{asg.cost}</td>
                  <td>{asg.risk}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </section>

      {/* Assumptions remain below the first-screen summary. */}
      <section className="logistics-brief" aria-label={L.decisionBrief}>
        <h3>{L.assumptions}</h3>
        <ul className="logistics-assumptions">
          {brief.assumptions.map(returnedText).filter(Boolean).map((item, idx) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      </section>

      {/* Unmet demand (explicit, never hidden). */}
      <section className="logistics-unmet" aria-label={L.unmetDemand}>
        <h2>{L.unmetDemand}</h2>
        {brief.unmet_demand.length === 0 ? (
          <p className="logistics-unmet-none">{L.noUnmetDemand}</p>
        ) : (
          <ul>
            {brief.unmet_demand.map((row) => (
              <li key={row.demand_id} data-unmet={row.demand_id}>
                {row.commodity ? demandCommodityLabel(row.commodity, L) : row.demand_id}:{" "}
                {row.unmet_units} {L.colUnits}
              </li>
            ))}
          </ul>
        )}
      </section>

    </div>
  );
}

type LogisticsStrings = ReturnType<typeof useI18n>["t"]["logistics"];

function demandCommodityLabel(commodity: string, L: LogisticsStrings): string {
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

function demandLabel(demandId: string, L: LogisticsStrings): string {
  if (demandId.startsWith("medical")) return L.commodityMedical;
  if (demandId.startsWith("food")) return L.commodityFood;
  if (demandId.startsWith("fuel")) return L.commodityFuel;
  return demandId;
}

function englishPortLabel(label: string, fallbackId: string): string {
  const englishSuffix = label.match(/[A-Za-z][A-Za-z .'-]*$/u)?.[0].trim();
  return englishSuffix || fallbackId;
}

function englishOnlyText(value: string): string {
  return value
    .replace(/[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

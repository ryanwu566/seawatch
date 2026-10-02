import type { DecisionBrief, ScenarioContext } from "./logisticsTypes";

/**
 * Results panel for the Resilience Logistics view. Fleshed out in Slice I with
 * the allocation table, decision brief, trade-offs, unmet demand, and the
 * always-visible TruthBadge. This stub renders nothing until a brief exists.
 */
export function LogisticsPanel({
  context: _context,
  brief,
}: {
  context: ScenarioContext | null;
  brief: DecisionBrief | null;
}) {
  if (!brief) return null;
  return <div data-testid="logistics-panel" />;
}

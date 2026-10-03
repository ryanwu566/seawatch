// Frontend mirror of the backend logistics language hard gate
// (apps/api/seawatch/logistics/brief.py FORBIDDEN_TERMS). Rendered logistics
// output must never contain these directive/military terms. Matched on whole
// words / exact phrases so benign substrings (e.g. "ordering") do not trip.

export const FORBIDDEN_TERMS: readonly string[] = [
  "command",
  "dispatch immediately",
  "dispatch directive",
  "military recommendation",
  "military",
  "confirmed disruption",
  "real capacity",
  "verified inventory",
  "order",
  "tasking",
  "deploy",
  "deployment",
  "weapon",
  "troop",
  "strike",
  "attack",
  "enemy",
  "threat level",
];

/** Return the first forbidden term found in `text`, or null if safe. */
export function findForbiddenTerm(text: string): string | null {
  const lowered = text.toLowerCase();
  for (const term of FORBIDDEN_TERMS) {
    const pattern = new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`);
    if (pattern.test(lowered)) return term;
  }
  return null;
}

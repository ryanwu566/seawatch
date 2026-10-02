import { useI18n } from "../../i18n/I18nContext";

/**
 * Always-visible provenance / truth badge. It renders the four source-class
 * counts from the backend `provenance_summary` and the `provenance_note`
 * verbatim, so a human always sees that capacity/cost/risk figures are
 * scenario/synthetic planning estimates for human review — never real
 * operational data. This component must never be hidden when a result exists.
 */
export function TruthBadge({
  provenanceSummary,
  provenanceNote,
}: {
  provenanceSummary: Record<string, number>;
  provenanceNote: string;
}) {
  const { t } = useI18n();
  const L = t.logistics;
  const classes: Array<[string, string]> = [
    ["official", "official"],
    ["derived", "derived"],
    ["scenario", "scenario"],
    ["synthetic", "synthetic"],
  ];

  return (
    <aside className="logistics-truth-badge" data-testid="truth-badge" role="note">
      <strong>{L.truthBadgeTitle}</strong>
      <ul className="truth-badge-counts">
        {classes.map(([key, label]) => (
          <li key={key} data-source-class={key}>
            <span className="truth-badge-label">{label}</span>
            <span className="truth-badge-count">{provenanceSummary?.[key] ?? 0}</span>
          </li>
        ))}
      </ul>
      <p className="truth-badge-note">{provenanceNote}</p>
    </aside>
  );
}

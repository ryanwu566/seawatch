import { useMemo, useState } from "react";
import { useI18n } from "../../i18n/I18nContext";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import { vesselTypeLabel } from "../../lib/display";
import { ProvenanceTag } from "./ProvenanceTag";
import { buildVesselIntelligence, hasEvidenceBackedReason } from "./buildIntelligence";
import type { Provenanced } from "./intelligenceTypes";

/**
 * Explainable Vessel Intelligence Card — a collapsed, additive section inside
 * VesselPanel. Human-in-the-loop review support: it summarizes identity,
 * in-session behavior, and evidence-backed review notes, each with a provenance
 * tag. It never classifies, scores, or uses threat/suspicion wording, never
 * exposes MMSI/IMO, and shows "Unknown" for anything the live data lacks.
 */
export function VesselIntelligenceCard({
  vessel,
  track,
}: {
  vessel: LiveVesselFeature;
  track: LiveTrack | null;
}) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);

  const intel = useMemo(() => buildVesselIntelligence(vessel, track), [vessel, track]);

  const typeLabel =
    intel.profile.type.value === null
      ? null
      : vesselTypeLabel(vessel.properties.vessel_type, lang);

  const evidenceBacked = hasEvidenceBackedReason(intel);

  return (
    <section className="vessel-intelligence">
      <button
        type="button"
        className="intelligence-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "▾" : "▸"} {t.intelligenceTitle}
      </button>

      {open && (
        <div className="intelligence-body" data-testid="vessel-intelligence">
          {/* Identity */}
          <h4 className="intelligence-group">{t.intelligenceIdentity}</h4>
          <dl className="intelligence-fields">
            <IdentityRow label={t.intelligenceName} field={intel.profile.name} unknownText={t.valueUnknown} />
            <IdentityRow
              label={t.intelligenceType}
              field={intel.profile.type}
              displayValue={typeLabel}
              unknownText={t.valueUnknown}
            />
            <IdentityRow label={t.intelligenceFlag} field={intel.profile.flag} unknownText={t.valueUnknown} />
            <IdentityRow label={t.intelligenceImo} field={intel.profile.imo} unknownText={t.valueUnknown} />
          </dl>

          {/* Behavior summary (in-session) */}
          <h4 className="intelligence-group">{t.intelligenceBehavior}</h4>
          <dl className="intelligence-fields">
            <IdentityRow
              label={t.intelligenceObservations}
              field={intel.behavior.sessionObservationCount}
              displayValue={
                intel.behavior.sessionObservationCount.value === null
                  ? null
                  : String(intel.behavior.sessionObservationCount.value)
              }
              unknownText={t.valueUnknown}
            />
            <IdentityRow
              label={t.intelligenceSessionSpan}
              field={intel.behavior.sessionSpan}
              displayValue={intel.behavior.sessionSpan.evidence ?? intel.behavior.sessionSpan.value}
              unknownText={t.valueUnknown}
            />
            <IdentityRow
              label={t.intelligenceTypicalRoute}
              field={intel.behavior.typicalRoute}
              unknownText={t.valueUnknown}
            />
            <IdentityRow
              label={t.intelligenceUsualArea}
              field={intel.behavior.usualOperatingArea}
              unknownText={t.valueUnknown}
            />
          </dl>

          {/* Review notes — evidence-backed only */}
          <h4 className="intelligence-group">{t.intelligenceReviewNotes}</h4>
          {evidenceBacked ? (
            <ul className="intelligence-reasons">
              {intel.reasons
                .filter((r) => r.provenance === "derived")
                .map((r) => (
                  <li key={r.kind} data-reason={r.kind}>
                    <span className="reason-mark" aria-hidden="true">
                      ✓
                    </span>{" "}
                    {t[r.labelKey]}
                    {r.evidence ? <span className="reason-evidence"> · {r.evidence}</span> : null}{" "}
                    <ProvenanceTag provenance={r.provenance} />
                  </li>
                ))}
            </ul>
          ) : (
            <p className="muted collecting">{t.intelligenceNoReasons}</p>
          )}

          {/* Route-baseline-unavailable is always shown explicitly (unknown). */}
          <p className="intelligence-baseline" data-reason="route_baseline_unavailable">
            <span className="reason-mark" aria-hidden="true">
              ⓘ
            </span>{" "}
            {t.intelligenceNoBaseline} <ProvenanceTag provenance="unknown" />
          </p>

          <p className="intelligence-human-review">{t.intelligenceHumanReview}</p>
        </div>
      )}
    </section>
  );
}

/** One label/value row with a provenance tag; shows "Unknown" when absent. */
function IdentityRow({
  label,
  field,
  displayValue,
  unknownText,
}: {
  label: string;
  field: Provenanced<unknown>;
  displayValue?: string | null;
  unknownText: string;
}) {
  const isKnown = field.value !== null;
  const text = isKnown ? (displayValue ?? String(field.value)) : unknownText;
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <span className="intelligence-value">{text}</span> <ProvenanceTag provenance={field.provenance} />
      </dd>
    </>
  );
}

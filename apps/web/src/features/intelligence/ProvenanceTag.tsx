import { useI18n } from "../../i18n/I18nContext";
import type { Provenance } from "./intelligenceTypes";

const LABEL_KEY: Record<Provenance, "provenanceOfficial" | "provenanceObserved" | "provenanceDerived" | "provenanceUnknown"> = {
  official: "provenanceOfficial",
  observed: "provenanceObserved",
  derived: "provenanceDerived",
  unknown: "provenanceUnknown",
};

/**
 * A small, color-coded provenance chip. Every value in the Vessel Intelligence
 * Card is accompanied by one of these so a reviewer always sees how a field is
 * known: official / observed / derived / unknown. Mirrors the IntegrityBadge
 * visual language without modifying it.
 */
export function ProvenanceTag({ provenance }: { provenance: Provenance }) {
  const { t } = useI18n();
  return (
    <span
      className={`provenance-tag provenance-${provenance}`}
      data-provenance={provenance}
    >
      {t[LABEL_KEY[provenance]] as string}
    </span>
  );
}

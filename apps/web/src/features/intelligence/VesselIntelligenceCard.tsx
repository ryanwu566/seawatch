import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n/I18nContext";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import { vesselTypeLabel } from "../../lib/display";
import { ProvenanceTag } from "./ProvenanceTag";
import { buildVesselIntelligence, hasEvidenceBackedReason } from "./buildIntelligence";
import type { Provenanced } from "./intelligenceTypes";
import { readRouteDeviation } from "./routeDeviation";
import type { RouteDeviationView } from "./routeDeviation";
import { fetchGeographicContext } from "./geographicContextClient";
import type { Confidence, GeographicContext } from "./geographicTypes";

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

  // Route Deviation evidence (route-deviation-1): read from the track payload
  // when present, else an all-Unknown view. No geometry done here.
  const routeDeviation = useMemo(() => readRouteDeviation(track), [track]);

  // Maritime GIS context (gis-context-1): fetched from the existing
  // GET /context/geographic route using the vessel position. Degrades to null
  // (treated as unknown) on error or while loading; the backend returns a
  // fully-unknown result for positions outside reference coverage.
  const [gis, setGis] = useState<GeographicContext | null>(null);
  const [lon, lat] = vessel.geometry.coordinates;
  useEffect(() => {
    if (!open) return;
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      setGis(null);
      return;
    }
    const controller = new AbortController();
    fetchGeographicContext(lon, lat, controller.signal)
      .then((ctx) => setGis(ctx))
      .catch(() => setGis(null));
    return () => controller.abort();
  }, [open, lon, lat]);

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

          {/* Route Deviation (route-deviation-1) — always renders the five
              fields; Unknown when no evidence is available. */}
          <RouteDeviationSection view={routeDeviation} />

          {/* Maritime GIS Context (gis-context-1) — distance to coast, nearest
              port + distance, maritime area context. Unknown out of coverage. */}
          <GeographicContextSection gis={gis} />

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

/** Localized confidence label (HIGH / MEDIUM / LOW). */
function useConfidenceLabel(): (c: Confidence) => string {
  const { t } = useI18n();
  return (c: Confidence) =>
    c === "HIGH" ? t.confidenceHigh : c === "MEDIUM" ? t.confidenceMedium : t.confidenceLow;
}

/**
 * Route Deviation (route-deviation-1). Always shows status, distance, baseline,
 * confidence, source, and the evidence explanation. Each field carries a
 * provenance tag and renders "Unknown" when the backend did not produce it.
 */
function RouteDeviationSection({ view }: { view: RouteDeviationView }) {
  const { t } = useI18n();
  const confidenceLabel = useConfidenceLabel();

  const statusText =
    view.statusKey === "route_deviation_detected"
      ? t.routeDeviationDetected
      : view.statusKey === "route_within_corridor"
        ? t.routeWithinCorridor
        : t.valueUnknown;

  return (
    <section className="route-deviation" data-testid="route-deviation">
      <h4 className="intelligence-group">{t.routeDeviationTitle}</h4>
      {view.statusProvenance === "unknown" ? (
        <p className="muted route-deviation-unknown">
          {t.routeDeviationUnknown} <ProvenanceTag provenance="unknown" />
        </p>
      ) : null}
      <dl className="intelligence-fields route-deviation-fields">
        <dt>{t.routeDeviationStatus}</dt>
        <dd>
          <span className="intelligence-value" data-field="status">
            {statusText}
          </span>{" "}
          <ProvenanceTag provenance={view.statusProvenance} />
        </dd>

        <dt>{t.routeDeviationDistance}</dt>
        <dd>
          <span className="intelligence-value" data-field="distance">
            {view.deviationKm === null ? t.valueUnknown : `${view.deviationKm.toFixed(1)} km`}
          </span>{" "}
          <ProvenanceTag provenance={view.deviationProvenance} />
        </dd>

        <dt>{t.routeDeviationBaseline}</dt>
        <dd>
          <span className="intelligence-value" data-field="baseline">
            {view.baseline ?? t.valueUnknown}
          </span>{" "}
          <ProvenanceTag provenance={view.baselineProvenance} />
        </dd>

        <dt>{t.routeDeviationConfidence}</dt>
        <dd>
          <span className="intelligence-value" data-field="confidence">
            {view.confidence === null ? t.valueUnknown : confidenceLabel(view.confidence)}
          </span>{" "}
          <ProvenanceTag provenance={view.statusProvenance} />
        </dd>

        <dt>{t.routeDeviationSource}</dt>
        <dd>
          <span className="intelligence-value" data-field="source">
            {view.source ?? t.valueUnknown}
          </span>{" "}
          <ProvenanceTag provenance={view.source ? "derived" : "unknown"} />
        </dd>

        {view.explanation ? (
          <>
            <dt>{t.routeDeviationExplanation}</dt>
            <dd>
              <span className="intelligence-value" data-field="explanation">
                {view.explanation}
              </span>{" "}
              <ProvenanceTag provenance={view.explanationProvenance} />
            </dd>
          </>
        ) : null}
      </dl>
    </section>
  );
}

/**
 * Maritime GIS Context (gis-context-1). Shows distance to coast, nearest port,
 * distance to port, and maritime area context. When the backend reports a value
 * as unavailable (null position / outside coverage), each field renders
 * "Unknown". An empty named-area list is a real "not within a named area" fact,
 * distinct from Unknown.
 */
function GeographicContextSection({ gis }: { gis: GeographicContext | null }) {
  const { t, lang } = useI18n();
  const inCoverage = gis?.coverage.value === "in_coverage";

  const coast = gis?.distance_to_coast_km;
  const port = gis?.nearest_port;
  const portVal = port?.value ?? null;

  const portName =
    portVal === null ? null : lang === "en" ? portVal.name_en : portVal.name_zh;

  const areaText = (() => {
    if (!gis || !gis.named_areas_computed) return t.valueUnknown;
    if (gis.within_named_areas.length === 0) return t.gisNotWithinArea;
    return gis.within_named_areas
      .map((a) => (lang === "en" ? a.name_en : a.name_zh))
      .join(" · ");
  })();
  const areaProvenance = !gis || !gis.named_areas_computed ? "unknown" : "derived";

  return (
    <section className="geographic-context" data-testid="geographic-context">
      <h4 className="intelligence-group">{t.gisContextTitle}</h4>
      {!inCoverage ? (
        <p className="muted gis-outside-coverage">
          {t.gisOutsideCoverage} <ProvenanceTag provenance="unknown" />
        </p>
      ) : null}
      <dl className="intelligence-fields geographic-context-fields">
        <dt>{t.gisDistanceToCoast}</dt>
        <dd>
          <span className="intelligence-value" data-field="coast">
            {coast && coast.value !== null ? `~${coast.value.toFixed(1)} km` : t.valueUnknown}
          </span>{" "}
          <ProvenanceTag provenance={coast?.provenance ?? "unknown"} />
        </dd>

        <dt>{t.gisNearestPort}</dt>
        <dd>
          <span className="intelligence-value" data-field="port">
            {portName ?? t.valueUnknown}
          </span>{" "}
          <ProvenanceTag provenance={portName ? "official" : "unknown"} />
        </dd>

        <dt>{t.gisDistanceToPort}</dt>
        <dd>
          <span className="intelligence-value" data-field="port-distance">
            {portVal ? `~${portVal.distance_km.toFixed(1)} km` : t.valueUnknown}
          </span>{" "}
          <ProvenanceTag provenance={portVal ? "derived" : "unknown"} />
        </dd>

        <dt>{t.gisMaritimeArea}</dt>
        <dd>
          <span className="intelligence-value" data-field="area">
            {areaText}
          </span>{" "}
          <ProvenanceTag provenance={areaProvenance} />
        </dd>
      </dl>
    </section>
  );
}

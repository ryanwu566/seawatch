import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n/I18nContext";
import { ApiError } from "../../api/client";
import {
  fetchHistoricalBaseline,
  type HistoricalBaselineState,
} from "../../api/historical";
import type { LiveVesselFeature, LiveTrack } from "../../api/live";
import { vesselTypeLabel } from "../../lib/display";
import { ProvenanceTag } from "./ProvenanceTag";
import { buildVesselIntelligence, hasEvidenceBackedReason } from "./buildIntelligence";
import type { Provenanced } from "./intelligenceTypes";
import { readRouteDeviation } from "./routeDeviation";
import type { RouteDeviationView } from "./routeDeviation";
import { fetchGeographicContext } from "./geographicContextClient";
import type { Confidence, GeographicContext } from "./geographicTypes";
import type {
  SatelliteEvidence,
  SatelliteEvidenceProvenance,
  SatelliteEvidenceValue,
} from "./satelliteEvidence";

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
  demoContext = null,
  satellite_evidence,
}: {
  vessel: LiveVesselFeature;
  track: LiveTrack | null;
  /**
   * Optional ILLUSTRATIVE demo geographic context. When provided, the card is in
   * demo mode: it renders a DEMO/illustrative banner, uses this fixture context,
   * and NEVER calls the live `/context/geographic` endpoint. Live rendering is
   * entirely unaffected when this is null (the default).
   */
  demoContext?: GeographicContext | null;
  satellite_evidence?: SatelliteEvidence[];
}) {
  const { t, lang } = useI18n();
  const isDemo = demoContext !== null;
  const [open, setOpen] = useState(isDemo);

  const intel = useMemo(() => buildVesselIntelligence(vessel, track), [vessel, track]);

  const typeLabel =
    intel.profile.type.value === null
      ? null
      : vesselTypeLabel(vessel.properties.vessel_type, lang);

  const evidenceBacked = hasEvidenceBackedReason(intel);

  // Route Deviation evidence (route-deviation-1): read from the track payload
  // when present, else an all-Unknown view. No geometry done here.
  const routeDeviation = useMemo(() => readRouteDeviation(track), [track]);

  // Maritime GIS context (gis-context-1): in demo mode use the fixture and skip
  // the network entirely. In live mode, fetch from the existing
  // GET /context/geographic route using the vessel position. Degrades to null
  // (treated as unknown) on error or while loading; the backend returns a
  // fully-unknown result for positions outside reference coverage.
  const [liveGis, setLiveGis] = useState<GeographicContext | null>(null);
  const [historical, setHistorical] = useState<HistoricalBaselineState>({ status: "idle" });
  const [lon, lat] = vessel.geometry.coordinates;
  useEffect(() => {
    if (isDemo) return; // demo context is injected; never touch the live endpoint
    if (!open) return;
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      setLiveGis(null);
      return;
    }
    const controller = new AbortController();
    fetchGeographicContext(lon, lat, controller.signal)
      .then((ctx) => setLiveGis(ctx))
      .catch(() => setLiveGis(null));
    return () => controller.abort();
  }, [isDemo, open, lon, lat]);

  useEffect(() => {
    if (isDemo || !open) return;

    const controller = new AbortController();
    let active = true;
    setHistorical({ status: "loading" });
    fetchHistoricalBaseline(vessel.id, controller.signal)
      .then((baseline) => {
        if (!active) return;
        setHistorical({
          status: baseline.sufficient ? "sufficient" : "insufficient",
          baseline,
        });
      })
      .catch((error: unknown) => {
        if (!active || controller.signal.aborted) return;
        setHistorical(
          error instanceof ApiError && error.status === 404
            ? { status: "not-found" }
            : { status: "unavailable" },
        );
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [isDemo, open, vessel.id]);

  const gis = isDemo ? demoContext : liveGis;

  return (
    <section className="vessel-intelligence" data-demo={isDemo ? "true" : undefined}>
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
          {isDemo ? (
            <p className="intelligence-demo-banner" data-testid="demo-banner" role="note">
              {t.demoIllustrativeLabel}
            </p>
          ) : null}
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

          <HistoricalBaselineSection
            state={isDemo ? { status: "unavailable" } : historical}
          />

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

          {/* Route Deviation (route-deviation-1) — always renders the five
              fields; Unknown when no evidence is available. */}
          <RouteDeviationSection view={routeDeviation} />

          {/* Maritime GIS Context (gis-context-1) — distance to coast, nearest
              port + distance, maritime area context. Unknown out of coverage. */}
          <GeographicContextSection gis={gis} />

          {satellite_evidence && satellite_evidence.length > 0 ? (
            <SatelliteEvidenceSection evidence={satellite_evidence} />
          ) : null}

          <p className="intelligence-human-review">{t.intelligenceHumanReview}</p>
        </div>
      )}
    </section>
  );
}

function HistoricalBaselineSection({ state }: { state: HistoricalBaselineState }) {
  const { t } = useI18n();
  const confidenceLabel = useConfidenceLabel();

  if (state.status === "idle" || state.status === "loading") {
    return (
      <section className="historical-baseline" data-testid="historical-baseline">
        <h4 className="intelligence-group">{t.historicalBaselineTitle}</h4>
        <p className="muted">{t.loading}</p>
      </section>
    );
  }

  if (state.status === "not-found" || state.status === "unavailable") {
    return (
      <section className="historical-baseline" data-testid="historical-baseline">
        <h4 className="intelligence-group">{t.historicalBaselineTitle}</h4>
        <p className="muted historical-baseline-status">
          {state.status === "not-found" ? t.historicalNotFound : t.historicalUnavailable}{" "}
          <ProvenanceTag provenance="unknown" />
        </p>
      </section>
    );
  }

  const baseline = state.baseline;
  const corridorAvailable =
    state.status === "sufficient" && baseline.typical_routes.length > 0;
  const sourceAvailable = baseline.data_source === "gfw_presence";

  return (
    <section className="historical-baseline" data-testid="historical-baseline">
      <h4 className="intelligence-group">{t.historicalBaselineTitle}</h4>
      <p className="historical-baseline-status">
        {state.status === "sufficient"
          ? t.historicalBaselineAvailable
          : t.historicalInsufficient}{" "}
        <ProvenanceTag provenance="derived" />
      </p>
      <dl className="intelligence-fields historical-baseline-fields">
        <HistoricalValueRow
          label={t.historicalObservedDays}
          field={baseline.history_summary.observed_day_count}
        />
        <HistoricalValueRow
          label={t.historicalObservations}
          field={baseline.history_summary.total_observations}
        />
        <HistoricalValueRow
          label={t.historicalTracks}
          field={{ value: baseline.historical_track_count, provenance: "derived" }}
        />
        <HistoricalValueRow
          label={t.historicalMovementCorridor}
          field={{
            value: corridorAvailable ? t.historicalCorridorAvailable : null,
            provenance: corridorAvailable ? "derived" : "unknown",
          }}
        />
        <HistoricalValueRow
          label={t.routeDeviationConfidence}
          field={{
            ...baseline.confidence,
            value:
              baseline.confidence.value === null
                ? null
                : confidenceLabel(baseline.confidence.value),
          }}
        />
        <HistoricalValueRow
          label={t.routeDeviationSource}
          field={{
            value: sourceAvailable ? t.historicalGfwSource : null,
            provenance: sourceAvailable ? "observed" : "unknown",
          }}
        />
      </dl>
    </section>
  );
}

function HistoricalValueRow({
  label,
  field,
}: {
  label: string;
  field: {
    value: number | string | null;
    provenance: Provenanced<unknown>["provenance"];
  };
}) {
  const { t } = useI18n();
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <span className="intelligence-value">
          {field.value === null ? t.valueUnknown : String(field.value)}
        </span>{" "}
        <ProvenanceTag provenance={field.provenance} />
      </dd>
    </>
  );
}

function satelliteProvenance(
  provenance: SatelliteEvidenceProvenance | undefined,
): Provenanced<unknown>["provenance"] {
  if (provenance === "Observed") return "observed";
  if (provenance === "Derived") return "derived";
  return "unknown";
}

function SatelliteEvidenceRow({
  label,
  value,
  provenance,
}: {
  label: string;
  value: SatelliteEvidenceValue | undefined;
  provenance: Provenanced<unknown>["provenance"];
}) {
  const { t } = useI18n();
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <span className="intelligence-value">
          {value === undefined || value === null ? t.valueUnknown : String(value)}
        </span>{" "}
        <ProvenanceTag provenance={value === undefined || value === null ? "unknown" : provenance} />
      </dd>
    </>
  );
}

function SatelliteEvidenceSection({ evidence }: { evidence: SatelliteEvidence[] }) {
  const { t } = useI18n();
  const scenes = evidence.filter(
    (scene) =>
      scene.availability !== undefined ||
      scene.provider !== undefined ||
      scene.scene_id !== undefined ||
      scene.platform !== undefined ||
      scene.datetime !== undefined ||
      scene.orbit !== undefined,
  );

  if (scenes.length === 0) return null;

  return (
    <section className="satellite-evidence" data-testid="satellite-evidence">
      <h4 className="intelligence-group">{t.satelliteEvidenceTitle}</h4>
      {scenes.map((scene, index) => (
        <dl className="intelligence-fields satellite-scene" data-testid="satellite-scene" key={index}>
          {scene.availability !== undefined ? (
            <SatelliteEvidenceRow
              label={t.satelliteAvailability}
              value={scene.availability}
              provenance={satelliteProvenance(scene.provenance?.availability)}
            />
          ) : null}
          {scene.provider !== undefined ? (
            <SatelliteEvidenceRow
              label={t.satelliteProvider}
              value={scene.provider}
              provenance="unknown"
            />
          ) : null}
          {scene.scene_id !== undefined ? (
            <SatelliteEvidenceRow
              label={t.satelliteSceneId}
              value={scene.scene_id}
              provenance={satelliteProvenance(scene.provenance?.scene_id)}
            />
          ) : null}
          {scene.platform !== undefined ? (
            <SatelliteEvidenceRow
              label={t.satellitePlatform}
              value={scene.platform}
              provenance={satelliteProvenance(scene.provenance?.platform)}
            />
          ) : null}
          {scene.datetime !== undefined ? (
            <SatelliteEvidenceRow
              label={t.satelliteObservedDatetime}
              value={scene.datetime}
              provenance={satelliteProvenance(scene.provenance?.datetime)}
            />
          ) : null}
          {scene.orbit !== undefined ? (
            <SatelliteEvidenceRow
              label={t.satelliteOrbit}
              value={scene.orbit}
              provenance={satelliteProvenance(scene.provenance?.orbit)}
            />
          ) : null}
        </dl>
      ))}
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

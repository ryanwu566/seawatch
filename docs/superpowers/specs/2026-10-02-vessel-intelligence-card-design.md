# Vessel Intelligence Card — design specification

Date: 2026-10-02 (Asia/Taipei)
Status: **Design only. No implementation.** Awaiting approval before any code.

## Purpose

Give a human reviewer an honest, explainable answer to:

> "How do you know this vessel deserves attention?"

The answer is never "AI says dangerous." It is a transparent, provenance-labeled
summary of **what changed**, **compared with what baseline**, and **what
evidence a human should review**.

The Vessel Intelligence Card is a small, additive **human-in-the-loop review
support** surface inside the existing `VesselPanel`. It is explicitly **not** a
threat classifier, a dangerous-vessel detector, an autonomous decision system,
or an intelligence database.

### Non-goals (hard constraints)

- No global vessel database, owner intelligence, or sanctions data.
- No risk classifier, ML model, or external/paid API.
- No new database or persistence layer.
- No modification of Phase 8 Edge Resilience (`live/`, `edge/`, `resilience/`,
  `MapCanvas` generic seam, API-base contract, offline map behavior, Cloud/Edge
  source semantics).
- No modification of Phase 9 Resilience Logistics (`logistics/` backend or
  `features/logistics/` frontend).
- No invented data. A field with no evidence is `unknown`, never guessed.
- No "normal/abnormal", "suspicious", "dangerous", or "threat" language.

---

## 1. Current architecture review

SeaWatch (reviewed in `apps/`) already provides the pieces this card composes
from — it adds no new data source.

- **Live AIS path (Phase 8, protected).** `apps/api/seawatch/live/`:
  `LiveVesselStore` holds, per vessel keyed by an opaque `provider_id`, the
  latest `LiveVesselObservation` plus a **bounded rolling trajectory** (default
  last 30 minutes, ≤ 720 points; stale vessels dropped after 15 minutes). The
  public API exposes `GET /live/vessels` (FeatureCollection) and
  `GET /live/vessels/{id}/track` (LineString + `point_count`, `observed_from`,
  `observed_to`). `active_view.py` adds Cloud/Edge provenance
  (`observation_origin`, `display_state`, `coverage`, `operating_mode`).
- **Identity privacy (protected).** `live/identity.py` maps internal MMSI/IMO to
  an HMAC-derived opaque `provider_id` (prefix `v_`). MMSI/IMO are carried
  internally **for deduplication and trajectory building only** and are
  deliberately **never** in any public payload (`schema.py`
  `to_public_properties` omits them).
- **Explainable review-ranking foundation (offline).**
  `apps/api/seawatch/review_ranking/` and `trajectories/` produce feature-based,
  statistical deviation **explanations** over **offline NOAA MarineCadastre AIS
  cohorts**. They are keyed to offline track ids, **not** to live `provider_id`,
  and are not wired into the live path.
- **Frontend.** `apps/web/src/api/live.ts` typed client; `components/VesselPanel.tsx`
  selection drawer; `lib/integrity.ts` (freshness classification),
  `lib/display.ts` (`vesselTypeLabel`, `friendlySource`), `lib/orientation.ts`;
  bilingual `i18n/dictionaries.ts`.

**Key architectural fact that constrains the MVP:** the live path keeps only a
**short in-session rolling trajectory**, not a persistent per-vessel history.
Long-term "typical route" / "usual operating area" / multi-day observation
counts do **not** exist in the live product and cannot be produced without a new
persistence/analytics system — which is out of scope. The card therefore
distinguishes **in-session derived** behavior (available now) from **historical
baseline** (not available → `unknown`), and never fabricates the latter.

---

## 2. Existing VesselPanel analysis

`apps/web/src/components/VesselPanel.tsx` (reviewed) renders, for the selected
`LiveVesselFeature`:

- Header: ship glyph, `name || t.noVesselName`, `vesselTypeLabel(vessel_type)`,
  freshness (`formatAge(data_age_seconds)`).
- Metric row: speed (`sog_knots`), course (`normalizeOrientation(heading, cog)`),
  destination.
- Position status + `IntegrityBadge` (live / cached / stale /
  provider_interpolated / offline_demo) and friendly source.
- `Recent Track` section (uses `track.properties.point_count`).
- `Review Priority` section — currently an **honest placeholder**:
  `t.collectingForAnalysis` ("collecting for analysis"), with **no fabricated
  score**. This is the natural anchor for the card.
- `Advanced Analysis` — a collapsed `<section>` with a toggle
  (`advancedOpen`), where technical fields and the benchmark disclaimer live.

Observations relevant to the design:

- The panel already uses a **collapsed/expandable section pattern** (Advanced
  Analysis) and an `IntegrityBadge` provenance pattern — the card reuses both.
- The panel already honors the privacy boundary (no MMSI/IMO shown; raw
  `provider_id` only under Advanced).
- The panel already receives `vessel` and `track`; the card needs **no new
  props on the live path** for its in-session content, and one optional new prop
  for the composed profile (below).
- The "Review Priority — collecting for analysis" placeholder is exactly where
  explainable review notes belong once they are evidence-backed.

---

## 3. Data availability assessment (honest)

Every card field maps to one provenance class: `official` | `observed` |
`derived` | `unknown`. "Do not invent missing data" is enforced by defaulting to
`unknown`.

### Identity

| Field | Available now? | Provenance | Notes |
|---|---|---|---|
| Name | Yes, when AIS provides it (`properties.name`) | `observed` | AIS self-reported, not an official register. `unknown` when null. |
| Type | Yes (`properties.vessel_type` AIS code → `vesselTypeLabel`) | `observed` | AIS self-reported category bucket. `unknown` when null. |
| Flag | **No** | `unknown` | Not in AIS position reports or the live schema. Could in principle derive from MMSI MID, but MMSI is intentionally not exposed and surfacing it violates the privacy boundary. MVP shows `unknown`. |
| IMO | **No** | `unknown` | Not present in the live public schema at all. MVP shows `unknown`. |
| MMSI (internal/public) | Internal only | n/a | Never displayed. The card shows the opaque `provider_id` only under the existing Advanced Analysis, exactly as today. |

### Historical behavior summary

| Field | Available now? | Provenance | Notes |
|---|---|---|---|
| In-session observation count | Yes (`track.point_count`) | `derived` | Count of retained rolling-trajectory points **this session** (≤ 30 min window). Must be labeled "this session", not lifetime. |
| In-session track span | Yes (`observed_from`/`observed_to`) | `derived` | Time span of the retained trajectory. |
| Typical route / usual operating area | **No** | `unknown` | No persistent multi-day per-vessel history in the live path. Shown as `unknown` ("No historical baseline available"). The example "Kaohsiung ↔ Japan" is illustrative only and must **not** be fabricated at runtime. |
| Lifetime / previous-session observation count | **No** | `unknown` | Live store drops stale vessels; no cross-session persistence. |

### Current observation

| Field | Available now? | Provenance | Notes |
|---|---|---|---|
| Current speed (`sog_knots`) | Yes | `observed` | `unknown` when null. |
| Current heading / course | Yes (`heading_deg`, `cog_deg`) | `observed` | Reuse `normalizeOrientation`. |
| Last update time | Yes (`observed_at`, `data_age_seconds`) | `observed` | Reuse `formatAge`. |
| Track freshness / integrity | Yes (`classifyVessel`, `display_state`) | `observed`/`derived` | Reuse `IntegrityBadge`. |

### Explainable review reasons

Review reasons are **only** emitted when there is in-session evidence to back
them. In MVP, candidate reasons derivable from the rolling trajectory:

- **In-session loitering duration** (`derived`): extended low-SOG dwell within
  the retained window → "Low-speed dwell of ~N minutes observed this session."
- **In-session speed change** (`derived`): change in SOG across retained points
  beyond a documented threshold → "Speed changed from ~A to ~B knots this
  session."
- **In-session course change** (`derived`): heading/COG change beyond a
  documented threshold → "Course changed by ~N° this session."
- **Route-baseline deviation** (`unknown` in MVP): the ideal reason ("Current
  track deviates 42 km from historical route baseline") **requires a historical
  baseline that does not exist** in the live path. MVP therefore shows this as
  an explicit **"No historical baseline available for route-deviation review"**
  note, never a fabricated distance.

Every reason carries its evidence (the numbers it was computed from) and its
provenance. If no in-session evidence exists, the card shows the existing
honest "collecting for analysis" state — not an empty "all clear" or a score.

---

## 4. MVP design

A single additive, collapsed **"Vessel Intelligence"** expandable section inside
`VesselPanel`, mirroring the existing Advanced Analysis pattern. It composes
only from data already available to the panel (`vessel`, `track`) plus pure
derivations; it adds **no** network call and **no** new backend route in MVP.

### Provenance tag

A tiny inline chip rendered next to every field value: `official` | `observed` |
`derived` | `unknown`, bilingual (官方 / 觀測 / 推導 / 未知). Reuses the
`IntegrityBadge` visual language (a new sibling component `ProvenanceTag`, not a
modification of `IntegrityBadge`).

### Section layout (bilingual, zh-Hant first)

```
▸ 船舶情報  Vessel Intelligence                    [collapsed by default]

  身分  Identity
    名稱 Name:        Unknown                 (unknown)
    類型 Type:        Cargo                   (observed · AIS)
    船旗 Flag:        Unknown                 (unknown)
    IMO:              Unknown                 (unknown)

  行為摘要  Behavior Summary
    本次觀測點數 Observations (this session): 1240   (derived)
    觀測時間跨度 Session span:  14:02–14:30         (derived)
    慣常航線 Typical route:  No historical baseline available   (unknown)

  複審註記  Review Notes
    ✓ 本次低速滯留約 18 分鐘                    (derived · evidence: SOG≤1kn, 18m)
      Low-speed dwell of ~18 min observed this session
    ✓ 本次航速由 ~12 降至 ~2 節                  (derived · evidence: 12→2 kn)
      Speed changed from ~12 to ~2 knots this session
    ⓘ 無歷史航線基準，無法進行航線偏離複審         (unknown)
      No historical baseline available for route-deviation review

  需人工複審  Human review required
```

Rules encoded in the layout:

- Every value shows a provenance tag; `unknown` values literally say "Unknown"
  with the `unknown` tag — never a guess.
- Review Notes are evidence-backed derivations only; each shows the numbers it
  came from. No "normal/abnormal", no score, no threat word.
- The closing line is always "Human review required" — the card supports a
  decision, it does not make one.
- If no in-session evidence and no identity beyond type: the section still
  renders Identity/Current with `unknown`s and shows the existing
  "collecting for analysis" note under Review Notes.

### Current Observation

Current speed/heading/last-update/freshness are already rendered in the main
drawer body; the Intelligence section **does not duplicate** them. It instead
references them and adds the provenance framing (all `observed`). (Alternative,
if reviewers prefer self-containment: a compact read-only echo labeled
`observed` — decided at implementation per reviewer preference, no new data
either way.)

---

## 5. Data model (additive interfaces, no new DB)

Pure, frontend-side TypeScript types assembled from the existing
`LiveVesselFeature` + `LiveTrack`. No backend schema change, no persistence, no
new route in MVP. All types live in a new, isolated
`apps/web/src/features/intelligence/` folder (sibling to `features/logistics/`),
touching no Phase 8/9 code.

```ts
export type Provenance = "official" | "observed" | "derived" | "unknown";

export interface Provenanced<T> {
  value: T | null;        // null ⇒ unavailable
  provenance: Provenance; // "unknown" whenever value is null
  evidence?: string;      // optional: how a "derived" value was computed
}

export interface VesselProfile {
  publicId: string;                       // opaque provider_id (never MMSI/IMO)
  name: Provenanced<string>;              // observed | unknown
  type: Provenanced<string>;              // observed | unknown (bucket label)
  flag: Provenanced<string>;              // unknown in MVP
  imo: Provenanced<string>;               // unknown in MVP
}

export interface VesselObservation {
  speedKnots: Provenanced<number>;        // observed
  headingDeg: Provenanced<number>;        // observed
  lastUpdate: Provenanced<string>;        // observed (ISO)
  freshness: Provenanced<string>;         // observed/derived (integrity kind)
}

export interface BehaviorSummary {
  sessionObservationCount: Provenanced<number>;  // derived (track.point_count)
  sessionSpan: Provenanced<string>;              // derived (observed_from–to)
  typicalRoute: Provenanced<string>;             // unknown in MVP
  usualOperatingArea: Provenanced<string>;       // unknown in MVP
}

export type ReviewReasonKind =
  | "session_loitering"
  | "session_speed_change"
  | "session_course_change"
  | "route_baseline_unavailable";

export interface ReviewReason {
  kind: ReviewReasonKind;
  provenance: Provenance;   // "derived" for evidence-backed; "unknown" for baseline-unavailable
  summaryZh: string;        // template text, no threat language
  summaryEn: string;
  evidence?: string;        // the numbers it was computed from
}

export interface VesselIntelligence {
  profile: VesselProfile;
  observation: VesselObservation;
  behavior: BehaviorSummary;
  reasons: ReviewReason[];  // only evidence-backed entries; may be empty
}
```

A pure builder `buildVesselIntelligence(vessel: LiveVesselFeature, track: LiveTrack | null): VesselIntelligence`
assembles these from existing data, defaulting every unavailable field to
`unknown`. Review-reason thresholds are documented constants (loitering minutes,
speed-delta knots, course-delta degrees); reasons are omitted when evidence is
absent. The builder is deterministic and dependency-free.

### Why frontend-only in MVP

All inputs (`sog_knots`, `heading_deg`, `cog_deg`, `data_age_seconds`,
`vessel_type`, `name`, `track.point_count`, `observed_from/to`) are already in
the public payloads the panel receives. No backend change is required, which
keeps the card fully isolated from Phase 8/9 and avoids any new persistence. A
future, separately-approved phase could move derivation server-side if a real
historical baseline store is ever introduced — explicitly out of this scope.

---

## 6. UI integration

- **Add** one collapsed `<section className="vessel-intelligence">` to
  `VesselPanel.tsx`, placed near the existing "Review Priority" block, using the
  same `useState` toggle pattern as Advanced Analysis.
- **Reuse** `formatAge`, `normalizeOrientation`, `vesselTypeLabel`,
  `classifyVessel`, `IntegrityBadge` styling.
- **Add** a small `ProvenanceTag` presentational component and the
  `features/intelligence/` builder + types.
- **Do not** change the drawer's existing header/metrics/track/advanced blocks,
  the map, or any Phase 8/9 surface. The panel's public props are unchanged
  (the card derives from the `vessel`/`track` it already has).
- Collapsed by default so the polished FR24-style drawer is visually unchanged
  until a reviewer expands the card.

---

## 7. Files to modify / add

Additive-only; no Phase 8/9 file is modified.

| Path | Change |
|---|---|
| `apps/web/src/features/intelligence/intelligenceTypes.ts` | **New.** The types in §5. |
| `apps/web/src/features/intelligence/buildIntelligence.ts` | **New.** Pure deterministic builder + documented thresholds. |
| `apps/web/src/features/intelligence/VesselIntelligenceCard.tsx` | **New.** The collapsed section UI. |
| `apps/web/src/features/intelligence/ProvenanceTag.tsx` | **New.** Provenance chip. |
| `apps/web/src/components/VesselPanel.tsx` | **Modify (additive).** Render `<VesselIntelligenceCard vessel={vessel} track={track} />` in a new collapsed section. No existing block changed. |
| `apps/web/src/i18n/dictionaries.ts` | **Modify (additive).** New Intelligence keys only (zh-Hant + en); no existing key changed. |
| `apps/web/src/styles.css` | **Modify (additive).** New `.vessel-intelligence` / `.provenance-tag` classes only. |

No backend file, no `live/`/`edge/`/`resilience/`/`logistics/` file, no
`MapCanvas`, no `api/client.ts`, no `requirements.txt`/`package.json`.

---

## 8. Tests needed

Frontend (Vitest + Testing Library), all additive:

1. **Builder — provenance correctness** (`buildIntelligence.test.ts`):
   - Name/type present ⇒ `observed`; null ⇒ `value: null`, `unknown`.
   - Flag and IMO always `unknown` in MVP (never populated/guessed).
   - `sessionObservationCount`/`sessionSpan` from `track` ⇒ `derived`; null track
     ⇒ `unknown`.
   - `typicalRoute`/`usualOperatingArea` always `unknown` in MVP.
   - Determinism: same input ⇒ identical output.
2. **Builder — review reasons** (`buildIntelligence.test.ts`):
   - Loitering/speed-change/course-change emitted **only** when evidence crosses
     documented thresholds; each carries `derived` + `evidence`.
   - `route_baseline_unavailable` always present as `unknown` (never a fabricated
     km distance).
   - No reasons ⇒ empty list (no fabricated "all clear").
3. **Card render** (`VesselIntelligenceCard.test.tsx`):
   - Collapsed by default; expands on toggle.
   - Every rendered value has a visible provenance tag; `unknown` fields show
     "Unknown".
   - "Human review required" always present when the card is expanded.
   - Bilingual labels render (zh-Hant default, en toggle).
4. **Language guard** (`VesselIntelligenceCard.test.tsx`):
   - Rendered output contains **no** prohibited wording ("dangerous",
     "suspicious", "threat", "normal/abnormal"). Reuse/extend a forbidden-term
     check so the honesty boundary is machine-enforced.
5. **VesselPanel non-regression** (extend `components` tests):
   - Existing header/metrics/track/advanced blocks still render unchanged with
     the card collapsed.
6. **Privacy non-regression**: card never renders MMSI/IMO; `provider_id` only
   under the existing Advanced section.

Verification gate before any future implementation lands: `npm test` and
`npm run build` green; no Phase 8/9 test changed.

---

## 9. Truth / explainability boundaries (restated)

- Every field is provenance-labeled; unavailable ⇒ `unknown`, never invented.
- Behavior is **in-session derived** unless a real historical baseline exists;
  the absence of a baseline is stated, not papered over.
- Review reasons are evidence-backed, cite their numbers, and use
  decision-support language only. No threat/suspicion/normal-abnormal wording.
- The card ends in "Human review required"; it never classifies or decides.
- No MMSI/IMO exposure; the Phase 8 privacy boundary is preserved.

This specification is design-only. No code is written until it is approved.

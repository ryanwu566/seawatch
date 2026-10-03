# Maritime Context Intelligence Layer — design specification

**Status:** Design only. No implementation. Awaiting approval before any code.

**Date:** 2026-10-02 (Asia/Taipei)

**Builds on (completed):** Vessel Intelligence Card MVP, Route Deviation
Evidence, Phase 8 Edge Resilience, Phase 9 Resilience Logistics.

**Challenge framing:** TDTH 2026 #07 Maritime Track Anomaly & Grey-Zone
Behavior Alerting. This layer deepens **SENSE** — the explainable review support
inside the Vessel Intelligence Card — without crossing into classification or
judgement.

> This document is design and planning only. It defines no application code, no
> dependency change, and no deployment. It must not disturb the Phase 8 Edge
> Resilience, Phase 9 Resilience Logistics, or Vessel Intelligence Card surfaces.
> Implementation is a later, separate phase, gated on approval.

---

## 1. Purpose

The Vessel Intelligence Card answers *"How do you know this vessel deserves
attention?"* today only from **in-session derived behavior** — the short rolling
trajectory the live path retains. Every richer question (*Is this near a
shipping lane? Is it in a restricted/anchorage area? Was it seen before? Is this
course consistent with the weather?*) currently resolves to `unknown`, which is
honest but thin.

The **Maritime Context Intelligence Layer** gives the card the surrounding
context it needs to answer one precise question:

> **"Why does this vessel deserve human review?"**

The answer is assembled from four context sources — historical AIS, maritime
GIS, satellite observation, and weather/ocean state — each contributing
**provenance-labeled context facts**, never a verdict. The card composes these
facts into evidence-backed review notes. A reviewer, not the system, draws the
conclusion.

### 1.1 What this layer is

A **context-enrichment layer**: a set of bounded, read-only context providers
plus a composition step that attaches provenance-labeled context facts to a
vessel for the existing Vessel Intelligence Card. Each provider answers "what is
true around / behind this observation", with an explicit provenance and an
explicit `unknown` when it cannot answer.

### 1.2 What this layer is NOT (hard constraints)

- **Not** a dangerous-vessel classifier.
- **Not** a threat-detection system.
- **Not** an autonomous judgement or decision engine.
- **Not** an intent, identity, owner, or sanctions database.
- **Not** a risk score, ML verdict, or "normal/abnormal" label.
- **Not** a new persistence/analytics product bolted onto the live path beyond
  the bounded historical store defined here.
- **No invented data.** Any fact a provider cannot supply is `unknown`, never
  guessed, interpolated into meaning, or back-filled with an illustrative value.

### 1.3 Language discipline (inherited from #07 and the card)

- **Allowed:** `context`, `observed`, `derived`, `near / within`, `distance to`,
  `consistent with`, `no baseline available`, `for human review`, `evidence`.
- **Forbidden:** `dangerous`, `suspicious`, `threat`, `hostile`, `illegal`,
  `normal / abnormal`, `target`, any military framing, and any phrasing that
  turns a context fact into a conclusion about the vessel.

A context fact states *what is around or behind* the vessel. It never states
*what the vessel is* or *what it intends*.

---

## 2. Scope boundaries vs completed work

This layer must remain **additive and isolated**.

- **Phase 8 Edge Resilience** (`live/`, `edge/`, `resilience/`, `MapCanvas`
  generic seam, API-base contract, offline map, Cloud/Edge/replay semantics):
  **not modified.** This layer consumes Phase 8 only through existing read-only
  public contracts (`/live/vessels`, `/live/vessels/{id}/track`) and the stable
  `/resilience/status` contract, exactly as Phase 9 does.
- **Phase 9 Resilience Logistics** (`logistics/` backend, `features/logistics/`
  frontend): **not modified.**
- **Vessel Intelligence Card** (`features/intelligence/`): **extended
  additively.** New context sections and context facts are added to the existing
  `VesselIntelligence` composition; no existing field or rule is changed. The
  card continues to default to `unknown` and continues to end in "Human review
  required".
- **Privacy boundary (Phase 8):** MMSI/IMO remain internal-only and are never
  surfaced. Historical-AIS linkage (§3) is keyed on the opaque `provider_id`
  only; it must not reintroduce raw identifiers into any public payload.

Each of the four context sources is an independent provider behind a small, uniform
seam, so sources can land one at a time and degrade independently to `unknown`
without affecting the card or each other.

---

## 3. Layer 1 — Historical AIS integration

**Question it helps answer:** *"Has this vessel, or this area, been observed
before, and does the current track differ from that history?"* This is the layer
that finally lets the card replace the Vessel Intelligence Card's `unknown`
"typical route" and "route-baseline deviation" placeholders with a real,
provenance-labeled baseline — the single highest-value gap identified in the
card MVP.

### 3.1 Available data

- **Offline NOAA MarineCadastre AIS cohorts** already ingested (Phase 1–3):
  multi-day GeoParquet, segmented trajectories, geodesic movement features, and
  the Phase 3B statistical baseline comparison. These are keyed to **offline
  `track_id`**, not to live `provider_id`.
- **Bounded live rolling trajectory** (Phase 8): per-vessel last ~30 min,
  ≤ 720 points, in-session only.

**Key constraint (restated from the card MVP):** there is **no persistent
per-vessel lifetime history in the live path**, and offline NOAA tracks are
U.S.-waters historical data not linkable to live Taiwan `provider_id`. A real
per-vessel historical baseline therefore requires a **new bounded historical
store**, explicitly scoped and opt-in, defined here as this layer's core
engineering work. Until that store exists and has data for a vessel/area, this
layer returns `unknown` — it never borrows an offline NOAA route as a stand-in
for a live vessel.

### 3.2 Fields

| Field | Source | Provenance | Notes |
|---|---|---|---|
| `historicalObservationCount` | historical store (per `provider_id`) | `derived` | Count across retained prior sessions; `unknown` if store empty for this vessel. |
| `firstSeen` / `lastSeen` | historical store | `derived` | Earliest/latest retained observation times; `unknown` if none. |
| `typicalRouteBaseline` | historical store (aggregated corridor) | `derived` | A corridor geometry aggregated from prior tracks; `unknown` until enough history exists. **Never** fabricated (no illustrative "Kaohsiung ↔ Japan"). |
| `usualOperatingArea` | historical store (aggregated hull/area) | `derived` | Convex/bbox area of prior observations; `unknown` if insufficient. |
| `routeDeviationDistanceKm` | current track vs `typicalRouteBaseline` | `derived` | Geodesic distance from baseline corridor; emitted **only** when a real baseline exists; otherwise `unknown`. This is the honest version of the card's deferred "42 km deviation" reason. |
| `areaHistoricalDensity` | historical store (spatial bin) | `derived` | How frequently *any* vessel was observed in this cell historically; context, not a per-vessel claim. `unknown` if no coverage. |

Provenance for every field above is `derived` **when backed by stored
observations**, and `unknown` otherwise. No field is `official`.

### 3.3 Provenance

- Store contents are `observed` AIS re-expressed as `derived` aggregates
  (counts, corridors, densities).
- Store is explicitly labeled **"SeaWatch-retained observations"**, scoped to a
  retention window and bbox, with provenance that it is **not** an authoritative
  vessel-history register.
- Linkage uses `provider_id` only. The store must never persist or expose raw
  MMSI/IMO.
- Retention, bbox, and opt-in flag are documented operator-facing settings;
  `unknown` is the default state for any vessel/area outside the retained set.

### 3.4 MVP priority

**P0 (highest).** This is the context source that most directly answers *"why
review?"* by supplying the baseline the card already has a labeled hole for. MVP
scope is deliberately minimal: per-`provider_id` observation count, first/last
seen, and area density — the cheapest aggregates. `typicalRouteBaseline`,
`usualOperatingArea`, and `routeDeviationDistanceKm` are **P1**, gated on
sufficient retained history and a documented minimum-observation threshold;
until met, they stay `unknown`.

### 3.5 UI presentation

Extends the card's existing **Behavior Summary** and **Review Notes** sections:

```
行為摘要  Behavior Summary
  歷史觀測點數 Historical observations:  3,120        (derived · retained)
  首次/最後觀測 First / last seen:  09-24 – 10-01       (derived · retained)
  慣常航線 Typical route baseline:  No baseline yet     (unknown)
  慣常活動範圍 Usual operating area:   No baseline yet   (unknown)

複審註記  Review Notes
  ✓ 目前航跡偏離歷史航線基準約 42 公里
    Current track deviates ~42 km from retained route baseline
    (derived · evidence: baseline corridor n=18 tracks, min-dist 42 km)
  ⓘ 歷史觀測不足，尚無航線基準          (unknown)   ← shown instead, when no baseline
```

### 3.6 Unknown handling

If the store has no observations for the `provider_id` (or the feature is not
opted-in / outside bbox): all fields render `unknown` with the literal label
"No baseline yet" / "尚無基準", and the route-deviation note falls back to the
card's existing "No historical baseline available for route-deviation review".
Never a fabricated distance, corridor, or count.

---

## 4. Layer 2 — Maritime GIS context

**Question it helps answer:** *"Where is this vessel relative to known maritime
geography — lanes, anchorages, port approaches, restricted/traffic-separation
zones, coastline?"* Spatial context is often the strongest, most explainable
reason a human would look twice (e.g., *loitering inside a port approach* vs
*loitering mid-ocean*).

### 4.1 Available data

- **Static, bundled GIS reference layers** (offline-first, consistent with Phase
  8 bundled offline map):
  - Coastline / land polygons (e.g., Natural Earth, public domain).
  - Port locations and approach areas (e.g., public port gazetteers).
  - Anchorage areas, traffic separation schemes, fairways where published as
    open data (e.g., ENC-derived open layers / OpenSeaMap-style sources).
  - Administrative / EEZ boundary polygons (public datasets) — **context only**,
    never a jurisdiction verdict.
- These are **place facts**, not vessel facts, and must be bundled with explicit
  source + license provenance (mirroring `docs/offline-map.md` discipline).

### 4.2 Fields

| Field | Source | Provenance | Notes |
|---|---|---|---|
| `distanceToCoastKm` | coastline layer vs position | `derived` | Geodesic distance to nearest coast. |
| `nearestPort` + `distanceToPortKm` | port gazetteer | `official` (name/location) + `derived` (distance) | Port identity is official reference data; the distance is derived. |
| `withinNamedArea[]` | anchorage / TSS / fairway polygons | `official` (area definition) + `derived` (containment test) | e.g., "within anchorage A", "within traffic-separation lane B". Context, not permission/violation. |
| `withinAdministrativeArea` | boundary polygons | `official` + `derived` | Named area only; **no** jurisdiction/legality claim. |
| `distanceToNearestLaneKm` | fairway/TSS layer | `derived` | Context for "off usual corridors" without asserting a rule. |

### 4.3 Provenance

- Area and port **definitions** are `official` reference data with cited source,
  version, and license per layer.
- Containment tests and distances are `derived` (computed via Shapely/PyProj,
  WGS84), labeled as geometric facts.
- No GIS fact is ever rendered as a rule being obeyed or broken (no
  "trespassing", "violation", "restricted-area breach"). The card states only
  *"within <named area>"* / *"~N km from <feature>"*.

### 4.4 MVP priority

**P0 (tied).** Coastline distance, nearest port + distance, and
within-named-area are high-value, fully offline, and dependency-light (reuses
existing Shapely/PyProj). MVP ships these three. TSS/fairway/EEZ layers are
**P1**, added as licensed open layers become bundled.

### 4.5 UI presentation

A new card section:

```
地理情境  Geographic Context
  離岸距離 Distance to coast:    2.3 km            (derived)
  最近港口 Nearest port:  Kaohsiung (~5.1 km)       (official · derived)
  所在區域 Within area:  Anchorage Zone A           (official · derived)
```

And it strengthens an existing Review Note **as context, not verdict**:

```
複審註記  Review Notes
  ✓ 本次低速滯留發生於港口進場區內
    Low-speed dwell this session occurred within a port-approach area
    (derived · evidence: SOG≤1kn 18m + within "Approach A")
```

### 4.6 Unknown handling

If position is null, outside bundled layer coverage, or a layer is not loaded:
each field is `unknown` ("Outside reference coverage" / "超出參考範圍"). The
GIS-conditioned Review Note is simply **not emitted** rather than guessed — an
absent context fact never becomes a weaker claim.

---

## 5. Layer 3 — Satellite observation context

**Question it helps answer:** *"Is there independent observation context for
this location/time — e.g., optical/SAR imagery availability or recent
cloud/pass coverage — that a human could pull to corroborate the AIS track?"*
This layer is deliberately the most conservative: it provides **availability and
pointers**, not detections.

### 5.1 Available data

- **Open satellite catalog / tiling metadata** (e.g., Sentinel-1 SAR,
  Sentinel-2 optical via open STAC catalogs; public pass/coverage metadata).
- **Imagery availability facts:** does a recent scene cover this lat/lon? what is
  its acquisition time, sensor, cloud cover, and a provenance link?
- **Explicitly excluded:** any vessel-detection-from-imagery, dark-vessel
  inference, or AIS-vs-imagery correlation that would constitute a detection or
  a "spoofing/dark-ship" claim. Those are classification/judgement and are out
  of scope by §1.2.

### 5.2 Fields

| Field | Source | Provenance | Notes |
|---|---|---|---|
| `recentSceneAvailable` | open STAC catalog | `official` (catalog) | Whether a scene covers position within a time window. |
| `sceneAcquiredAt` | catalog metadata | `official` | Acquisition timestamp (UTC). |
| `sceneSensor` | catalog metadata | `official` | e.g., Sentinel-1 / Sentinel-2. |
| `sceneCloudCoverPct` | catalog metadata | `official` | For optical scenes. |
| `scenePreviewLink` | catalog | `official` | Provenance link for a human to open imagery themselves. |
| `aisImageryAgreement` | — | **not computed** | **Intentionally omitted.** Correlating AIS with imagery is a detection claim and is out of scope. |

### 5.3 Provenance

- All fields are `official` catalog metadata with cited catalog + scene id, or
  `unknown`. SeaWatch never derives a vessel claim from imagery.
- The section is framed as *"independent imagery a human may review"*, never as
  *"satellite confirms/contradicts the vessel"*.
- If the deployment is offline (Phase 8 Edge mode), the catalog is unreachable;
  the entire section is `unknown` with an explicit "Imagery catalog unavailable
  offline" note — consistent with honest Cloud/Edge mode behavior.

### 5.4 MVP priority

**P2 (lowest).** It is the most network-dependent (breaks the offline-first
posture), adds the most external-contract surface, and contributes availability
pointers rather than direct review evidence. MVP for this layer is **a
read-only "imagery availability" lookup only**, behind a feature flag, defaulting
off and `unknown` in Edge/offline mode. No detection, ever.

### 5.5 UI presentation

A compact, link-forward card subsection (collapsed, under Advanced):

```
衛星觀測情境  Satellite Observation Context
  近期影像 Recent scene:  Yes — Sentinel-2, 09-30 10:12 UTC, cloud 12%   (official)
  影像連結 Open imagery:  [catalog link]                                 (official)
  （SeaWatch 不從影像判定船舶；僅提供人工查閱連結）
  (SeaWatch does not detect vessels from imagery; link is for human review only)
```

### 5.6 Unknown handling

Offline, flag-off, no covering scene, or catalog error → `unknown` ("No recent
imagery context" / "無近期影像情境"). No placeholder scene, no fabricated cloud
%, no implied "nothing there".

---

## 6. Layer 4 — Weather / ocean context

**Question it helps answer:** *"Is the observed behavior consistent with the
environment — could weather or current explain a speed drop or course change
before a human reads anything more into it?"* This layer's primary value is
**reducing false review load** by making benign environmental explanations
visible.

### 6.1 Available data

- **Open meteocean APIs / gridded products** (e.g., Open-Meteo Marine, NOAA/NWS,
  Copernicus Marine where openly available): wind, sea state / wave height,
  current, visibility, at a lat/lon/time.
- For Edge/offline mode: optionally a **bundled coarse climatology** (seasonal
  averages) as a clearly-labeled fallback, or `unknown`.

### 6.2 Fields

| Field | Source | Provenance | Notes |
|---|---|---|---|
| `windSpeedMs` / `windDirDeg` | meteocean API | `official` | At position/time. |
| `waveHeightM` | meteocean API | `official` | Sea state. |
| `currentSpeedMs` / `currentDirDeg` | meteocean API | `official` | Surface current. |
| `visibilityKm` | meteocean API | `official` | Where provided. |
| `envConsistencyNote` | derived from env + motion | `derived` | e.g., "speed drop coincides with wave height 3.2 m" — a **consistency context**, never a conclusion. Emitted only when both env data and a motion change exist. |

### 6.3 Provenance

- Raw meteocean values are `official` API data with cited provider, model run,
  and valid time.
- `envConsistencyNote` is `derived` and must be phrased as *"consistent with /
  coincides with"*, never *"explained by"* or *"therefore benign"*. It informs
  the reviewer; it does not clear the vessel.
- Climatology fallback (if used) is a distinct provenance label
  (`derived · climatology`) and must not be presented as a live observation.

### 6.4 MVP priority

**P1.** Lower than historical AIS and GIS (which answer *why review* most
directly), higher than satellite (which is offline-hostile). MVP: wind + wave +
one `envConsistencyNote` tied to an existing in-session speed/course change
reason, online only, `unknown` offline unless a bundled climatology is approved.

### 6.5 UI presentation

A new card subsection, and an enriching clause on an existing motion Review Note:

```
氣象海況情境  Weather / Ocean Context
  風速 Wind:   14 m/s @ 070°            (official · Open-Meteo 10:00 UTC)
  浪高 Waves:  3.2 m                     (official)
  能見度 Visibility:  6 km               (official)

複審註記  Review Notes
  ✓ 本次航速由 ~12 降至 ~2 節，與浪高 3.2 m 同時發生
    Speed changed ~12→2 kn this session, coincident with 3.2 m waves
    (derived · evidence: 12→2 kn; waves 3.2 m @10:00 UTC)
```

### 6.6 Unknown handling

API unreachable (incl. Edge/offline with no climatology), position/time null, or
provider error → each field `unknown` ("Weather context unavailable" /
"無氣象情境"). The consistency note is **not emitted** when env data is absent;
a motion change then stands alone exactly as in the current card.

---

## 7. Composition into the Vessel Intelligence Card

The layer adds a **context-composition step** that attaches provenance-labeled
context facts to the existing `VesselIntelligence` structure, extending — not
replacing — the card MVP's `Provenanced<T>` model.

```ts
// additive, sibling to the existing features/intelligence/ types
export type Provenance =
  | "official" | "observed" | "derived" | "unknown";

export interface ContextFact<T> {
  value: T | null;          // null ⇒ unavailable
  provenance: Provenance;   // "unknown" whenever value is null
  source?: string;          // cited dataset / API / catalog id
  validAt?: string;         // ISO time the fact is valid for, if applicable
  evidence?: string;        // for "derived": the numbers/geometry it came from
}

export interface MaritimeContext {
  historical?: HistoricalContext;   // Layer 1
  geographic?: GeographicContext;   // Layer 2
  satellite?: SatelliteContext;     // Layer 3
  weather?: WeatherContext;         // Layer 4
}
```

Rules the composition must encode (same spirit as the card MVP §9):

- Each provider is **independent** and may resolve wholly to `unknown` without
  affecting the others or the card.
- A context fact may **enrich** an existing Review Note (adding an evidence
  clause) but may **never** create a Review Note on its own that reads as a
  verdict. Review Notes remain evidence-backed, decision-support-worded, and
  end-to-end owned by the card.
- The card still **always ends in "Human review required"** and never emits a
  score, class, or threat word.
- Every new section/field carries a provenance tag and shows `unknown`
  explicitly when a provider cannot answer.

Suggested provider seam (for a later, separate implementation phase):

```ts
interface ContextProvider<C> {
  readonly id: string;                 // "historical" | "geographic" | ...
  readonly offlineCapable: boolean;    // true for GIS/historical/climatology
  resolve(input: ContextInput): Promise<C | null>;  // null ⇒ unknown
}
```

Providers would live in a new isolated `apps/api/seawatch/context/` package
(backend-derived facts: historical store, GIS containment, meteocean/satellite
proxies) exposed through **one additive read-only route**
(e.g., `GET /context/vessels/{id}`), consumed by the card via a new
`apps/web/src/features/intelligence/` context client. No Phase 8/9 file changes.

---

## 8. Cross-cutting: offline / Edge behavior

Consistent with Phase 8 honesty:

| Layer | Cloud (online) | Edge / offline |
|---|---|---|
| 1 Historical AIS | available (if store has data) | available (local store) |
| 2 Maritime GIS | available (bundled) | available (bundled) |
| 3 Satellite | available (flag-on) | **`unknown`** (catalog unreachable) |
| 4 Weather/Ocean | available | `unknown` unless bundled climatology approved |

The card must label the operating mode so a reviewer understands *why* a layer
is `unknown` (unavailable offline) versus *empty* (online but no data). This
reuses the existing Phase 8 `operating_mode` / `coverage` provenance surfaced
through `/resilience/status`; the context layer reads it, never changes it.

---

## 9. MVP priority summary

| Priority | Scope |
|---|---|
| **P0** | Layer 1 historical observation count / first-last seen / area density; Layer 2 coast distance / nearest port / within-named-area. These directly answer *"why review?"* and are fully offline-capable. |
| **P1** | Layer 1 route baseline + route-deviation distance (gated on min-observation threshold); Layer 4 wind/wave + one env-consistency note (online). |
| **P2** | Layer 3 satellite imagery availability lookup (flag-off by default, `unknown` offline), link-only, no detection ever. |

Everything not met in a given deployment resolves to `unknown` — the layer's
default and safest state.

---

## 10. Truth / explainability boundaries (restated)

- Every context fact is provenance-labeled (`official` / `observed` / `derived`
  / `unknown`); unavailable ⇒ `unknown`, never invented, interpolated, or
  stood-in by an illustrative value.
- Context sources state *what is around or behind* the vessel; they never state
  *what the vessel is* or *what it intends*.
- No source produces a classification, score, risk level, or "normal/abnormal"
  label. Satellite produces availability pointers only, never detections.
- Context may enrich evidence-backed Review Notes but never authors a verdict;
  the card still ends in "Human review required".
- The Phase 8 privacy boundary holds: historical linkage is on `provider_id`
  only; MMSI/IMO are never persisted to the context store or surfaced.
- Phase 8 Edge/offline honesty holds: layers that need the network degrade to a
  clearly-labeled `unknown`, distinct from an empty-but-online result.

This specification is design-only. No code is written until it is approved.

# Maritime GIS Context MVP — design specification

**Status:** Design only. No implementation. Awaiting approval before any code.

**Date:** 2026-10-02 (Asia/Taipei)

**Builds on (completed):** Vessel Intelligence Card MVP, Route Deviation
Evidence, Phase 8 Edge Resilience, Phase 9 Resilience Logistics; and the parent
`2026-10-02-maritime-context-intelligence-design.md` (this is its **Layer 2,
scoped to a shippable MVP**).

**Challenge framing:** TDTH 2026 #07 (SENSE). Deepens the Vessel Intelligence
Card with geographic context only.

> Design and planning only. No application code, no dependency change, no
> deployment. Must not disturb Phase 8 Edge Resilience, Phase 9 Resilience
> Logistics, or the existing Vessel Intelligence Card. Implementation is a
> later, separate, approval-gated phase.

---

## 1. Purpose

The Vessel Intelligence Card can describe a vessel's **in-session motion** but
currently says nothing about **where** that motion happens. A low-speed dwell
mid-strait and a low-speed dwell inside a port approach read identically to the
card today. Geographic context is often the single most explainable reason a
human looks twice — and the most honest, because it is pure geometry over public
reference data.

This MVP adds a **Geographic Context** section to the card that answers exactly
one question:

> **"What is around this vessel?"**

It answers with provenance-labeled geometric facts: distance to coast, nearest
port and distance, and which named maritime area (if any) the position falls
within. It explicitly does **not** answer *"what is this vessel doing
illegally?"* — there is no violation test, no restricted-area judgement, no
conclusion.

### 1.1 What this MVP is

A **read-only geographic-context provider**: pure geometry (point-in-polygon and
geodesic distance) over bundled, public, civilian reference layers, composed into
the existing card as provenance-labeled context facts.

### 1.2 What this MVP is NOT (hard constraints)

- **Not** a restricted-area / exclusion-zone **violation** detector.
- **Not** a jurisdiction, legality, permission, or trespass judgement.
- **Not** a classifier, score, threat/anomaly label, or autonomous conclusion.
- **Not** satellite detection, dark-vessel inference, or imagery correlation
  (explicitly out of scope — unchanged from the parent spec).
- **Not** a new live persistence layer; this is stateless geometry per request.
- **No invented data.** Outside layer coverage, or with a null position, every
  field is `unknown` — never a guessed distance, port, or area.

### 1.3 Language discipline

- **Allowed:** `near`, `within <named area>`, `distance to coast`,
  `nearest port`, `~N km from`, `for human review`, `context`.
- **Forbidden:** `violation`, `breach`, `trespass`, `illegal`, `unauthorized`,
  `restricted` **used as a verdict**, `incursion`, `prohibited`,
  `dangerous`, `suspicious`, `threat`, `normal/abnormal`, and any phrasing that
  turns a geometric fact into a statement about legality or intent.

A geographic fact states *what is around* the vessel. It never states that the
vessel is *allowed* or *not allowed* to be there.

---

## 2. Existing-asset inspection (grounding)

The MVP reuses what already exists; it introduces **no new runtime dependency**.

### 2.1 Geometry libraries (already present)

- **Backend:** `shapely==2.1.2`, `pyproj==3.8.0` are already in
  `requirements.txt` and in active use.
  - `apps/api/seawatch/trajectories/geodesy.py` wraps
    `pyproj.Geod(ellps="WGS84")` and exposes `geodesic_distance_m(lon1, lat1,
    lon2, lat2) -> float` (non-negative metres). **Reused directly** for coast
    and port distances — no new geodesy code.
  - Shapely 2.x provides `Point`, `Polygon`, `MultiPolygon`,
    `shortest_line` / `distance`, and `contains` for point-in-polygon and
    distance-to-geometry tests.
- **Frontend:** `apps/web/package.json` has `maplibre-gl` and `pmtiles` only —
  **no** JS geometry library. **Design consequence:** the geometric computation
  is done **backend-side** (where Shapely/PyProj already live) and delivered to
  the card as finished facts, matching the parent spec's "backend-derived facts
  through one additive read-only route" seam. The frontend renders strings and
  provenance tags only; it performs no geometry.

### 2.2 Reference assets (already present)

- **Ports:** `apps/web/src/config/taiwanMap.ts` → `COMMERCIAL_PORTS` — six
  public civilian Taiwan ports with `{id, nameZh, nameEn, lon, lat}` (Keelung,
  Taipei, Taichung, Kaohsiung, Hualien, Anping) and a `portsGeoJson()` builder.
  The comment banner already states "Only public, civilian, non-operational
  information … No military positions". This is the port source of truth. The
  MVP mirrors this list **once** on the backend (see §5) rather than importing
  frontend config into the API, keeping the privacy/layering clean.
- **Coastline:** `apps/web/src/assets/taiwan-emergency.geojson` — a simplified
  Taiwan/Penghu outline derived from **Natural Earth public-domain** geography
  (`apps/web/src/assets/README.md`), bundled, "no live, military, or sensitive
  location data". This is the coastline/land polygon source for distance-to-coast.
- **Named-area polygon pattern:** `taiwanMap.ts` → `AIRSPACE_AREAS` already
  demonstrates the exact shape the MVP needs for named maritime areas:
  `{id, nameZh, nameEn, kind, ring: [lon,lat][]}` + an `airspaceGeoJson()`
  builder, with an explicit "contextual civilian references, NOT operational
  military data" banner. The MVP adds a **maritime** sibling (anchorage /
  approach / fairway) following this precedent.
- **Bbox:** `TAIWAN_BBOX = {minLat:21.5, minLon:118.0, maxLat:26.5, maxLon:123.5}`
  defines reference coverage; positions outside it resolve to `unknown`
  ("outside reference coverage").

### 2.3 Provenance precedent (already present)

`apps/api/seawatch/trajectories/route_deviation.py` establishes the exact
pattern to mirror:

- `Provenance = Literal["official","observed","derived","unknown"]`.
- `Provenanced(value, provenance, note)` where `value is None ⇒ "unknown"`.
- Documented deterministic threshold constants surfaced in output.
- Explicit guarantee: "never emits 'suspicious','threat','dangerous','illegal'";
  insufficient data ⇒ `unknown`, never fabricated.

The GIS context provider adopts this provenance object and language guarantee
verbatim in spirit.

### 2.4 Phase 8/9 boundaries confirmed

- Live path exposes position via `GET /live/vessels` /
  `GET /live/vessels/{id}/track` keyed on opaque `provider_id`; MMSI/IMO never
  surfaced. The GIS context consumes position only — it adds **no** identity.
- Phase 8 offline map machinery (`config/offlineMap.ts`, `MapCanvas`,
  `/offline/taiwan.pmtiles`, emergency geojson) is **not** modified. The MVP
  reads the Natural Earth outline as reference data; it does not touch map
  rendering, style transitions, or overlays.

---

## 3. Scope: the four context facts (MVP)

Per the user request, exactly four geographic context inputs, producing the
"what is around this vessel?" answer.

### 3.1 Coastline → distance to coast

| Item | Detail |
|---|---|
| Field | `distanceToCoastKm` |
| Source | bundled Natural Earth Taiwan/Penghu land polygons |
| Provenance | `derived` (geodesic distance) |
| Method | nearest-point distance from vessel position to coastline geometry, via Shapely nearest point + `geodesic_distance_m` for the final metres→km value |
| Fact phrasing | "~2.3 km from coast" / "離岸約 2.3 公里" |
| Unknown when | position null, or outside `TAIWAN_BBOX` reference coverage |

### 3.2 Nearest port → identity + distance

| Item | Detail |
|---|---|
| Fields | `nearestPort` (name), `distanceToPortKm` |
| Source | backend mirror of `COMMERCIAL_PORTS` (public civilian ports) |
| Provenance | port **name/location** = `official` (public reference); **distance** = `derived` |
| Method | min `geodesic_distance_m` over the port list; report the closest port's bilingual name + distance |
| Fact phrasing | "Nearest port: Kaohsiung (~5.1 km)" / "最近港口：高雄港（約 5.1 公里）" |
| Unknown when | position null, or outside coverage |

### 3.3 Anchorage → within / near

| Item | Detail |
|---|---|
| Field | part of `withinNamedAreas[]` with `kind:"anchorage"` |
| Source | bundled maritime-area polygons (new civilian reference, §5), seeded from public anchorage/approach references for the six ports |
| Provenance | area **definition** = `official`; **containment test** = `derived` |
| Method | Shapely `contains` (point-in-polygon); if not inside, optionally the nearest-area distance as context |
| Fact phrasing | "Within anchorage area: Kaohsiung Anchorage A" / "位於錨地範圍：高雄錨地 A" |
| Unknown when | position null, outside coverage, or no anchorage layer loaded |

### 3.4 Named maritime areas → within

| Item | Detail |
|---|---|
| Field | `withinNamedAreas[]` with `kind:"approach" \| "fairway" \| "port_area"` |
| Source | bundled maritime-area polygons (§5), civilian, illustrative-but-labeled, mirroring the `AIRSPACE_AREAS` precedent |
| Provenance | definition = `official`; containment = `derived` |
| Method | point-in-polygon over the named-area set; a position may be within zero, one, or several areas (all reported) |
| Fact phrasing | "Within: Kaohsiung port approach" / "位於：高雄港進場區" |
| Unknown when | position null, outside coverage, or no area layer loaded |

**Hard rule for 3.3 / 3.4:** a named area carries **no permission semantics**.
The card states containment as a place fact ("within <named area>"). It never
derives, implies, or renders "allowed", "not allowed", "restricted", "violation",
or any legality from containment. `kind` is a descriptive label for the human,
not a rule classification.

---

## 4. Provenance model (official / derived / unknown)

The user constrained provenance to **three** values for this layer. Mapping onto
the project's four-value vocabulary:

| This MVP | Project vocabulary | Used for |
|---|---|---|
| `official` | `official` | Reference-data **definitions**: port name/location, named-area name/geometry, coastline source. These are curated public facts, not vessel observations. |
| `derived` | `derived` | Computed geometry: distances (coast, port), containment-test results. |
| `unknown` | `unknown` | Any fact unavailable: null position, outside coverage, layer not loaded, or degenerate geometry. |

`observed` is intentionally **not** produced by this layer — the vessel's
position itself is already labeled `observed` elsewhere in the card; the GIS
layer only turns that position into `official`-referenced and `derived` facts.
Every field defaults to `unknown`; `official`/`derived` are assigned only when a
real reference layer and a successful computation back them.

---

## 5. Data model and provider (design only, no code)

### 5.1 Backend provider

A new isolated package `apps/api/seawatch/context/gis/` (sibling to
`trajectories/`, `logistics/`; touches no `live/`/`edge/`/`resilience/`), with:

- A small, versioned, bundled civilian reference dataset
  (`context/gis/data/`): coastline reference pointer (reuse the Natural Earth
  outline), a backend `PORTS` mirror of the six public ports, and a
  `MARITIME_AREAS` list of named-area polygons following the `AIRSPACE_AREAS`
  ring shape, each with `{id, nameZh, nameEn, kind, provenanceSource}`.
- A pure, deterministic resolver (I/O-free given loaded layers), reusing
  `geodesy.geodesic_distance_m` and Shapely point-in-polygon:

```python
# illustrative shapes only — NOT an implementation
Provenance = Literal["official", "derived", "unknown"]

@dataclass(frozen=True)
class Provenanced:
    value: object          # None ⇒ provenance must be "unknown"
    provenance: Provenance
    source: str | None = None   # cited reference dataset
    note: str | None = None

@dataclass(frozen=True)
class NamedAreaHit:
    id: str
    name_zh: str
    name_en: str
    kind: Literal["anchorage", "approach", "fairway", "port_area"]
    provenance: Provenance      # "official" definition + "derived" containment

@dataclass(frozen=True)
class GeographicContext:
    schema_version: str                      # "gis-context-1"
    distance_to_coast_km: Provenanced        # derived | unknown
    nearest_port: Provenanced                # {name_zh,name_en,distance_km}; official+derived | unknown
    within_named_areas: tuple[NamedAreaHit, ...]  # may be empty; empty ≠ unknown
    coverage: Provenanced                    # "in_coverage" | unknown (outside bbox / null pos)
    disclaimer: str = (
        "Geographic context for human review only; geometric facts about the "
        "area around the vessel, not a judgement about the vessel or its "
        "permission to be there."
    )
```

Key design rules the resolver encodes:

- `coverage` is resolved first; a null position or an out-of-bbox position
  short-circuits **every** field to `unknown` (no partial guessing).
- `within_named_areas` **empty tuple** means "computed, inside none" (a real
  `derived` result), which is distinct from `unknown` ("could not compute"). The
  card must render these two states differently (see §6.4).
- Distances are rounded for display; the raw geometry is never exposed as a
  precise claim beyond its reference-data accuracy.
- Deterministic: same position + same bundled layers ⇒ identical output.

### 5.2 Delivery seam

One additive, read-only backend route (parent spec's seam), e.g.
`GET /context/vessels/{id}/geographic` returning `GeographicContext`, consumed by
a new `apps/web/src/features/intelligence/` geographic-context client. No Phase
8/9 route changed; the card gains one optional data input and degrades to
`unknown` if the route is absent/unreachable.

Alternative (lighter) seam, decided at implementation: fold the geographic facts
into the parent spec's single `GET /context/vessels/{id}` envelope under a
`geographic` key. Either way, **frontend performs no geometry**.

---

## 6. Card UI integration

### 6.1 Placement

A new collapsed-friendly **Geographic Context / 地理情境** block inside the
existing Vessel Intelligence Card section of `VesselPanel`, using the same
provenance-tag and expand pattern already specified for the card MVP. No existing
card block, drawer header, metrics, track, or Advanced section is changed.

### 6.2 Layout (bilingual, zh-Hant first)

```
地理情境  Geographic Context

  離岸距離 Distance to coast:   ~2.3 km                 (derived)
  最近港口 Nearest port:        高雄港 Kaohsiung (~5.1 km) (official · derived)
  所在區域 Within area(s):      高雄港進場區 Kaohsiung approach   (official · derived)
                                高雄錨地 A  Kaohsiung Anchorage A (official · derived)

  （以上為該位置周遭的地理事實，非對船舶行為或合法性的判斷）
  (Geographic facts about the area around this position — not a judgement
   about the vessel's behavior or legality)

  需人工複審  Human review required
```

### 6.3 Enriching an existing Review Note (context, not verdict)

Geographic context may add an **evidence clause** to a motion Review Note the
card already emits, but never authors a standalone verdict:

```
複審註記  Review Notes
  ✓ 本次低速滯留約 18 分鐘，發生於高雄港進場區內
    Low-speed dwell of ~18 min this session, within the Kaohsiung approach area
    (derived · evidence: SOG≤1kn 18m + within "Kaohsiung approach")
```

The note still describes **observed motion + where it occurred**. It does not say
the dwell is improper, restricted, or notable *because of* the area — only that
a human reviewing the dwell may want the location context.

### 6.4 Unknown vs empty (must be visually distinct)

| State | Meaning | Rendering |
|---|---|---|
| `unknown` | could not compute (null position / outside coverage / layer absent) | "Outside reference coverage" / "超出參考範圍" + `unknown` tag |
| empty `within_named_areas` | computed; inside no named area | "Not within a named area" / "不在任何命名區域內" + `derived` tag |
| populated | inside ≥1 named area | list each area + `official · derived` tags |

Every value carries a provenance tag; `unknown` literally says so; nothing is
guessed.

---

## 7. Files to add / modify (design only)

Additive-only; no Phase 8/9 file modified.

| Path | Change |
|---|---|
| `apps/api/seawatch/context/gis/__init__.py` | **New.** Package marker. |
| `apps/api/seawatch/context/gis/reference.py` | **New.** Backend `PORTS` mirror + `MARITIME_AREAS` named-area polygons + coastline reference pointer, each with `official` provenance + cited source. |
| `apps/api/seawatch/context/gis/resolver.py` | **New.** Pure deterministic resolver (coast distance, nearest port, point-in-polygon) reusing `geodesy` + Shapely. |
| `apps/api/seawatch/context/gis/schema.py` | **New.** `GeographicContext` / `Provenanced` / `NamedAreaHit` (mirrors route_deviation provenance). |
| `apps/api/seawatch/api/...` (one route) | **Modify (additive).** Register `GET /context/vessels/{id}/geographic`; no existing route changed. |
| `apps/web/src/features/intelligence/geographicContextClient.ts` | **New.** Typed read-only client. |
| `apps/web/src/features/intelligence/GeographicContextSection.tsx` | **New.** The card block (§6). |
| `apps/web/src/features/intelligence/geographicTypes.ts` | **New.** Mirror of the backend schema. |
| `apps/web/src/components/VesselPanel.tsx` | **Modify (additive).** Render the new block inside the existing Intelligence section only. |
| `apps/web/src/i18n/dictionaries.ts` | **Modify (additive).** New geographic-context keys (zh-Hant + en) only. |
| `apps/web/src/styles.css` | **Modify (additive).** New `.geographic-context` classes only. |

No new dependency (`requirements.txt` / `package.json` unchanged). No
`live/`/`edge/`/`resilience/`/`logistics/` file, no `MapCanvas`, no offline-map
code.

---

## 8. Tests needed (design only)

Backend (pytest), mirroring `test_geodesy.py` / route-deviation tests:

1. **Distance correctness:** known position ⇒ coast/port distances within
   tolerance of an independent `geodesic_distance_m` computation; determinism
   (same input ⇒ identical output).
2. **Nearest-port selection:** position near each of the six ports selects the
   correct port; ties resolved deterministically.
3. **Point-in-polygon:** a position inside a named-area ring reports that area;
   just outside does not; multiple-containment reports all.
4. **Provenance correctness:** port name/area definition ⇒ `official`; distances
   / containment ⇒ `derived`; null position / out-of-bbox ⇒ **all** `unknown`.
5. **Unknown vs empty:** out-of-coverage ⇒ `unknown`; in-coverage inside no area
   ⇒ **empty** `within_named_areas`, not `unknown`.
6. **Language guard:** rendered/returned text contains **no** forbidden term
   (`violation`, `breach`, `trespass`, `illegal`, `restricted`-as-verdict,
   `dangerous`, `suspicious`, `threat`, `normal/abnormal`). Machine-enforced.

Frontend (Vitest + Testing Library):

7. **Section render:** each field shows a provenance tag; `unknown` shows the
   coverage note; empty areas show "Not within a named area" (distinct from
   `unknown`); bilingual labels render.
8. **"Human review required"** always present when the block renders.
9. **Non-regression:** existing VesselPanel + card blocks unchanged; privacy
   boundary intact (no MMSI/IMO, `provider_id` only under Advanced).

Verification gate before any future implementation lands: `pytest` and
`npm test` / `npm run build` green; no Phase 8/9 test changed.

---

## 9. Truth / explainability boundaries (restated)

- Three provenance states: reference **definitions** are `official`, computed
  geometry is `derived`, anything unavailable is `unknown` — never invented.
- The layer answers **"what is around this vessel?"** with geometric facts, and
  nothing more. It never answers "what is this vessel doing illegally?".
- Named-area containment is a **place fact with no permission semantics**: no
  violation, trespass, restricted-area, or legality wording or logic.
- `unknown` (could not compute) and empty (computed, inside nothing) are
  distinct and rendered distinctly.
- Geographic context may enrich an evidence-backed motion Review Note but never
  authors a verdict; the card still ends in "Human review required".
- Reuses existing Shapely/PyProj and existing public, civilian reference assets;
  adds no dependency and no satellite/detection capability.
- Phase 8 privacy and offline-map behavior and Phase 9 logistics are untouched.

This specification is design-only. No code is written until it is approved.

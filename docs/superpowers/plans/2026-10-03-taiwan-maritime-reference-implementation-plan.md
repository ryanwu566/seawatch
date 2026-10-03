# Taiwan Maritime Reference Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, document, and validate deterministic Taiwan-area maritime reference GeoJSON from Marine Regions World EEZ v12 and official MOI 12/24 NM source lines.

**Architecture:** A single script separates cached network acquisition from pure local transformation. It validates and clips source features independently, strictly polygonizes the closed MOI lines for derived references, writes canonical GeoJSON, and emits complete per-output provenance metadata.

**Tech Stack:** Python 3, Shapely 2.1.2, PyProj 3.8.0, pyshp 2.4.2, pytest 9.1.1

**Spec:** `docs/superpowers/specs/2026-10-03-taiwan-maritime-reference-design.md`

## Global Constraints

- Remain on `feat/eez-reference-data`; do not switch or create branches.
- Do not run `git add`, `git commit`, `git push`, or `git merge`.
- Do not modify runtime APIs, live AIS, detection, auth, frontend maps/UI, historical GFW, ML, or deployment files.
- AOI is `[115, 20, 126, 27]`; output is EPSG:4326.
- Preserve overlapping claims as separate features; never dissolve them or choose a preferred claimant.
- Official MOI outputs remain lines. All polygonization/difference output is labeled `derived_reference`.
- Every relevant artifact states the exact legal caveat and that it is not for navigation.

## Review Focus

- A WFS bbox may return a feature whose envelope intersects but whose geometry does not; the transformer must remove empty AOI intersections.
- A future MOI archive may contain an open/self-intersecting line or ambiguous polygonization; derived output must fail rather than fabricate geometry.
- A 24 NM polygon may cease to cover its paired 12 NM polygon; band construction must reject that pair.
- Polygon normalization/rounding may invalidate a narrow ring; final serialized geometry must be reconstructed and revalidated.
- A source may contain a GeometryCollection after clipping/repair; only the layer-appropriate components may be retained and empties rejected.

---

### Task 1: Focused transformation contract tests

**Files:**
- Create: `tests/fixtures/gis/marine_regions_eez_aoi.geojson`
- Create: `tests/unit/test_taiwan_maritime_reference.py`

**Interfaces:**
- Consumes: planned `build_from_sources(...)` local transformation API.
- Produces: executable output, provenance, determinism, overlap, clipping, and derivation contracts.

- [ ] Write small local Marine Regions and MOI-schema fixtures with overlapping claims, one outside-AOI feature, closed 12/24 NM lines, a MultiLineString case, and hand-derived expected counts.
- [ ] Write tests covering all 17 required invariants plus strict rejection of ambiguous line polygonization and non-covering band inputs.
- [ ] Run `python -m pytest tests/unit/test_taiwan_maritime_reference.py -q` and verify collection fails because the build module/API is absent.

### Task 2: Deterministic local transformer and CLI acquisition

**Files:**
- Create: `scripts/build_taiwan_maritime_reference.py`
- Create: `scripts/requirements-taiwan-maritime-reference.txt`

**Interfaces:**
- Produces: `build_from_sources(eez_path, territorial_zip_path, contiguous_zip_path, output_dir, retrieval_date) -> dict[str, OutputSummary]` and CLI `--output-dir`, `--cache-dir`, `--retrieval-date`, `--refresh` options.

- [ ] Implement validated source loading, CRS checks/reprojection hook, geometry repair bookkeeping, AOI clipping, component filtering, geometry normalization, fixed-precision serialization, atomic writes, and stable feature ordering.
- [ ] Implement strict MOI polygonization and region-matched band derivation with fail-closed topology checks.
- [ ] Implement source acquisition using exact WFS/MOI URLs and a temp-directory cache, with raw MOI SHA-256 capture plus canonical WFS semantic hashing and a fail-closed reviewed snapshot pin.
- [ ] Emit all five GeoJSON files and complete `source_metadata.json` records.
- [ ] Run the focused tests until green, refactor only while they stay green, then rerun the focused file.

### Task 3: Production data build and human documentation

**Files:**
- Create: `data/gis/taiwan_maritime_reference/eez_reference_areas.geojson`
- Create: `data/gis/taiwan_maritime_reference/territorial_sea_12nm_official_line.geojson`
- Create: `data/gis/taiwan_maritime_reference/contiguous_zone_24nm_official_line.geojson`
- Create: `data/gis/taiwan_maritime_reference/territorial_sea_12nm_reference_polygon.geojson`
- Create: `data/gis/taiwan_maritime_reference/contiguous_zone_12_24nm_reference_band.geojson`
- Create: `data/gis/taiwan_maritime_reference/source_metadata.json`
- Create: `data/gis/taiwan_maritime_reference/README.md`

**Interfaces:**
- Consumes: Task 2 CLI and authoritative cached downloads.
- Produces: checked-in reviewable reference artifacts and rebuild/integration guidance.

- [ ] Run the CLI against authoritative sources with retrieval date `2026-10-03` and the target output directory.
- [ ] Write the README with exact sources/URLs/releases/licenses, layer meanings, derivation details, AOI/CRS, caveats, rebuild steps, and future-only integration guidance.
- [ ] Add a read-only production-artifact contract test and validate production feature counts, geometry validity/types, AOI bounds, overlap retention, checksums, and metadata coverage.

### Task 4: Verification and handoff

**Files:**
- Inspect only: all task files and repository state.

**Interfaces:**
- Consumes: completed artifacts/tests.
- Produces: evidence for the requested 20-point final report.

- [ ] Run the focused GIS tests.
- [ ] Run the repository pytest command and report unrelated collection/runtime failures by name without claiming a full pass if dependencies/environment prevent it.
- [ ] Inspect generated artifact sizes, feature counts, and hashes.
- [ ] Run `git diff --check`, `git diff --stat`, and `git status --short`; confirm protected areas are untouched and stop before commit/push.

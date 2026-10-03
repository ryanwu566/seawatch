# Datalastic Area Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit MapLibre-native polygon/rectangle workflow that scans Datalastic through the SeaWatch backend, returns privacy-safe real vessels, and reuses the existing Vessel Intelligence flow.

**Architecture:** Preserve the WebSocket `OpenWatersProvider`/`AisIngestConsumer` unchanged and add a request-driven Datalastic client, deterministic polygon-cover provider, and isolated Area Scan result/track state to `LiveRuntime`. The frontend holds ordinary live vessels and Area Scan vessels separately and calls the new endpoint only from an explicit Scan Area action.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, httpx, Shapely 2.1, PyProj 3.8, pytest; React 18, TypeScript 5.6, MapLibre GL JS 4.7, Vitest/Testing Library, Vite.

**Spec:** `docs/superpowers/specs/2026-10-03-datalastic-area-scan-design.md`

## Global Constraints

- Do not force Datalastic into `LiveAisProvider` or `AisIngestConsumer`.
- `DATALASTIC_API_KEY` is backend-only, header-only, never logged/serialized/committed, and blank in `.env.example`.
- Only valid MMSI may join Datalastic live observations to GFW history through the existing registry and stable `SEAWATCH_IDENTITY_KEY`.
- GeoJSON coordinate order is `[longitude, latitude]`; final filtering uses Shapely `covers` and respects holes.
- Datalastic circles use radius `<=45 NM`, never exceed `50 NM`, and a scan is rejected before provider traffic when it requires more than 16 circles.
- Provider concurrency is at most two and one `429` retry budget is shared by the whole scan.
- Area Scan state is separate from the ordinary polled live list; no implicit scans occur.
- Cache TTL is 45 seconds over canonical geometry and exposes only `cached`.
- `/stat` startup probing is non-blocking; `/live/health` and `/health` never trigger Datalastic traffic.
- Optional `/vessel` enrichment is out of scope.
- Normal tests are offline and use mocked HTTP. A real smoke is two calls maximum and happens only after all mocked/full checks pass.
- Do not commit, push, or merge. Do not stage generated output, secrets, or unrelated files.

## File Structure

| Path | Responsibility |
|---|---|
| `apps/api/seawatch/live/datalastic.py` | Typed Datalastic client, safe errors, status cache, and provider response normalization. |
| `apps/api/seawatch/live/area_scan.py` | Request models, geometry validation/canonicalization, deterministic cover, cache, orchestration, isolated result/track state. |
| `apps/api/seawatch/live/runtime.py` | Own the optional Datalastic client/service without changing the Open Waters consumer contract. |
| `apps/api/seawatch/api/live.py` | Expose sanitized provider health, Area Scan POST, and Area Scan track fallback. |
| `apps/api/seawatch/main.py` | Permit POST and schedule/cancel non-blocking Datalastic status probing. |
| `apps/api/seawatch/live/config.py` | Parse non-secret Datalastic configuration and provider-selection state. |
| `apps/api/seawatch/live/store.py` | Retain only privacy-safe normalized scan observations/tracks when used by Area Scan. |
| `apps/web/src/api/live.ts` | Typed same-origin Area Scan request/response client. |
| `apps/web/src/components/AreaScanPanel.tsx` | Explicit draw/scan/clear state and honest results/errors. |
| `apps/web/src/components/MapCanvas.tsx` | Polygon/rectangle event capture and separate scan geometry/vessel sources. |
| `apps/web/src/pages/LiveDashboard.tsx` | Keep ordinary and Area Scan vessels separate and route selection to existing panel. |
| `apps/web/src/i18n/dictionaries.ts` / `apps/web/src/styles.css` | Bilingual copy and existing-theme presentation. |
| `tests/unit/test_datalastic.py` | Offline client/status/security tests. |
| `tests/unit/test_area_scan.py` | Covering, filtering, cache, identity, and route tests. |
| `apps/web/src/components/AreaScanPanel.test.tsx` | Explicit-submit panel tests. |
| `apps/web/src/components/MapCanvas.test.tsx` | Draw modes and separate overlay tests. |
| `apps/web/src/pages/LiveDashboard.test.tsx` | Result persistence and Vessel Panel integration tests. |

## Review Focus

1. **Equivalent and adversarial polygons:** reversed/rotated rings hit one cache entry, while holes, boundary points, malformed closure, excessive vertices, and antimeridian input behave safely (Task 2 tests).
2. **Concurrent/rate-limited scans:** only two requests run at once, one shared retry is possible, long `Retry-After` values never freeze the UI, and identical scans coalesce (Tasks 1 and 3 tests).
3. **Identity ambiguity:** valid MMSI joins history; missing/invalid MMSI, UUID, and IMO never create a historical match or leak publicly (Task 3 tests).
4. **Lifecycle races:** non-blocking status probing cannot fail startup, mutate after shutdown, or make health endpoints contact the provider (Task 4 tests).
5. **Map event interference:** drawing suppresses vessel/empty-map selection as appropriate, never scans implicitly, restores drag/double-click behavior, and survives style reloads (Task 6 tests).

---

### Task 1: Typed Datalastic client and sanitized status

**Files:**
- Create: `apps/api/seawatch/live/datalastic.py`
- Create: `tests/unit/test_datalastic.py`

**Interfaces:**
- Produces: `DatalasticConfig.from_env(values: Mapping[str, str] | None = None)`, `DatalasticClient.stat() -> DatalasticStatus`, `DatalasticClient.vessels_in_radius(query: RadiusQuery, retry_budget: ScanRetryBudget) -> tuple[DatalasticVessel, ...]`, `ProviderError(category, retry_after_seconds=None)`, and thread-safe `DatalasticStatusCache.snapshot()/record_*()`.
- `RadiusQuery.radius_nm` rejects values above `45.0`; the request layer also asserts the provider maximum `50.0`.

- [ ] **Step 1: Write failing client tests** for header authentication, configurable base URL, typed successful `/stat` and `/vessel_inradius` parsing, unsuccessful `meta`, malformed JSON/schema, timeout, connection error, `401/403`, `5xx`, and key/user_id/body non-disclosure.
- [ ] **Step 2: Run** `& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider tests/unit/test_datalastic.py` and confirm failures are missing interfaces.
- [ ] **Step 3: Implement the typed client and fixed-category exceptions** with `httpx.AsyncClient`, explicit connect/read timeouts, `x-api-key`, and no raw provider text in errors/logs.
- [ ] **Step 4: Add failing shared-budget tests** proving max concurrency two, only one retry across multiple circles, short numeric `Retry-After` wait, and immediate sanitized failure for long/invalid values.
- [ ] **Step 5: Implement `ScanRetryBudget`** with one async shared retry token and a five-second maximum interactive wait.
- [ ] **Step 6: Rerun the focused file** and require all tests to pass.

### Task 2: Polygon validation, canonicalization, and deterministic cover

**Files:**
- Create: `apps/api/seawatch/live/area_scan.py`
- Create: `tests/unit/test_area_scan.py`

**Interfaces:**
- Produces: `validate_scan_geometry(payload: AreaScanRequest) -> ValidatedPolygon`, `canonical_geometry_key(polygon: Polygon) -> str`, `cover_polygon(polygon: Polygon) -> tuple[RadiusQuery, ...]`.
- Constants: `SCAN_RADIUS_NM = 45.0`, `MAX_PROVIDER_CIRCLES = 16`, `SCAN_CACHE_TTL_SECONDS = 45.0`.

- [ ] **Step 1: Write failing validation tests** for `[lon, lat]`, closed valid polygon, holes, boundary coordinates, invalid/self-intersecting/zero-area input, non-finite/out-of-range values, antimeridian crossing, excessive vertices, and Polygon-only enforcement.
- [ ] **Step 2: Run the validation subset** and confirm expected missing behavior.
- [ ] **Step 3: Implement Pydantic request parsing plus Shapely validation** without repairing invalid shapes silently.
- [ ] **Step 4: Write failing canonicalization tests** proving reversed ring orientation and rotated start vertices share a key while materially different shapes do not.
- [ ] **Step 5: Implement canonical ring orientation/start normalization**, fixed coordinate rounding, algorithm-version salt, and SHA-256 hashing.
- [ ] **Step 6: Write failing cover tests** for one-circle small shape, deterministic multi-circle shape, every radius `<=45`, complete cell coverage, 16-circle acceptance, 17-circle rejection before provider traffic, and exact oversized error text.
- [ ] **Step 7: Implement local AEQD projection and origin-anchored square-cell covering** whose half-diagonal is within 45 NM; compute all centers before returning.
- [ ] **Step 8: Rerun geometry tests** and require all to pass.

### Task 3: Area Scan service, isolated state, cache, privacy, and API

**Files:**
- Modify: `apps/api/seawatch/live/area_scan.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/api/live.py`
- Modify: `apps/api/seawatch/live/store.py` only if a narrow atomic normalized-observation helper is required
- Modify: `tests/unit/test_area_scan.py`
- Modify: `tests/unit/test_live_identity.py`

**Interfaces:**
- Produces: `AreaScanService.scan(request: AreaScanRequest) -> AreaScanResult`, `AreaScanService.track(public_id: str) -> ActiveTrack | None`, and `POST /live/area-scan`.
- `AreaScanResult` contains only `source`, `scanned_at`, `cached`, `scan.geometry_type`, `scan.provider_queries`, `total`, and existing privacy-safe vessel features.

- [ ] **Step 1: Write failing service tests** for overlapping-circle deduplication, latest-position choice, `covers` boundary inclusion, hole exclusion, deterministic output, normalization, and no provider call after preflight rejection.
- [ ] **Step 2: Run the service subset** and verify failures.
- [ ] **Step 3: Implement candidate merge/filter/normalization** using MMSI/UUID/IMO only for internal provider deduplication and existing `LiveVesselObservation` for retained data.
- [ ] **Step 4: Write failing identity/privacy tests** proving valid MMSI matches `public_id_for_mmsi`, invalid/missing MMSI is non-joinable, IMO/UUID never join history, and no raw identifier or key appears in response/error/log capture.
- [ ] **Step 5: Implement public serialization through the process-wide registry** and isolated bounded Area Scan track state.
- [ ] **Step 6: Write failing cache tests** for 45-second hit/expiry, equivalent-geometry hit, no duplicate provider calls, identical concurrent request coalescing, and public `cached` only.
- [ ] **Step 7: Implement the async TTL cache and in-flight coalescing** over privacy-safe normalized results.
- [ ] **Step 8: Write failing route tests** for success, `422`, unconfigured/timeout/auth/429/5xx `503`, safe Retry-After, CORS POST, and Area Scan track fallback.
- [ ] **Step 9: Implement the route and exception mapping**, factoring existing live-feature serialization rather than duplicating privacy logic.
- [ ] **Step 10: Run** `& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider tests/unit/test_area_scan.py tests/unit/test_live_identity.py tests/unit/test_live_ais.py` and require pass.

### Task 4: Runtime selection, non-blocking status probe, and health

**Files:**
- Modify: `apps/api/seawatch/live/config.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/main.py`
- Modify: `apps/api/seawatch/api/live.py`
- Modify: `tests/unit/test_live_config.py`
- Modify: `tests/unit/test_live_runtime.py`
- Modify: `tests/unit/test_live_failover_api.py`

**Interfaces:**
- `LiveRuntime` owns optional `datalastic_client`, `area_scan_service`, and cached provider status while retaining the existing `cloud.consumer` compatibility object.
- `/live/health` adds a safe `provider_status`; `/health` remains local-only.

- [ ] **Step 1: Write failing config/startup-selection tests** for explicit true/false preservation, Datalastic-with-unset-ingest disabling Open Waters, and neither-configured retaining anonymous fallback behavior.
- [ ] **Step 2: Run the focused runtime/config tests** and confirm failures.
- [ ] **Step 3: Implement optional Datalastic runtime ownership and selection** without changing the provider ABC or Open Waters consumer internals.
- [ ] **Step 4: Write failing lifecycle tests** proving `/stat` probe scheduling is non-blocking, probe failure leaves `/health` 200, shutdown is clean, and neither health route triggers an HTTP call.
- [ ] **Step 5: Implement lifespan task start/cancel and cached status updates** with warning-only failure.
- [ ] **Step 6: Write failing sanitization tests** for valid/invalid/unknown key status, add-ons, safe limits, and absence of user_id/key/raw errors.
- [ ] **Step 7: Extend `/live/health` additively** and preserve current fallback health tests.
- [ ] **Step 8: Run** `& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider tests/unit/test_datalastic.py tests/unit/test_area_scan.py tests/unit/test_live_config.py tests/unit/test_live_runtime.py tests/unit/test_live_failover_api.py tests/unit/test_live_ais.py`.

### Task 5: Frontend Area Scan client and explicit panel state

**Files:**
- Modify: `apps/web/src/api/live.ts`
- Create: `apps/web/src/components/AreaScanPanel.tsx`
- Create: `apps/web/src/components/AreaScanPanel.test.tsx`
- Modify: `apps/web/src/i18n/dictionaries.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Produces: `scanLiveArea(geometry: GeoJSON.Polygon, signal?: AbortSignal): Promise<AreaScanResponse>` using `getBaseUrl()` and `AreaScanPanel` callbacks `onDrawMode`, `onScan`, and `onClear`.
- Panel state is `idle | drawing | ready | scanning | success | unavailable`.

- [ ] **Step 1: Write failing API tests** proving POST goes only to `${getBaseUrl()}/live/area-scan`, sends GeoJSON, handles safe errors, and contains no key or Datalastic origin.
- [ ] **Step 2: Write failing panel tests** for control visibility, Polygon/Rectangle selection, no request while drawing, explicit submit, loading, result count/query/time/cache, unavailable state, and clear.
- [ ] **Step 3: Run** `npm.cmd test -- AreaScanPanel` from `apps/web` and verify failures.
- [ ] **Step 4: Implement typed API and presentational panel** with bilingual, human-review-safe copy.
- [ ] **Step 5: Rerun the focused panel/client tests** and require pass.

### Task 6: MapLibre drawing, separate layers, and dashboard integration

**Files:**
- Modify: `apps/web/src/components/MapCanvas.tsx`
- Modify: `apps/web/src/components/MapCanvas.test.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.test.tsx`

**Interfaces:**
- Extend `MapCanvasProps` with `areaDrawMode`, `areaGeometry`, `areaVessels`, and `onAreaGeometryChange`.
- Ordinary vessels retain the existing source/layers; scan vessels use dedicated emphasized source/layers and share `onSelectVessel`.

- [ ] **Step 1: Write failing MapCanvas tests** for polygon click/double-click finish, rectangle drag finish, no network behavior, visible fill/line, emphasized scan vessels, selection, Clear data removal, style-reload restoration, and draw-mode interaction cleanup.
- [ ] **Step 2: Run the MapCanvas test file** and confirm expected failures.
- [ ] **Step 3: Implement minimal MapLibre-native drawing and dedicated sources/layers** without adding dependencies or changing existing vessel layers.
- [ ] **Step 4: Write failing dashboard tests** proving ordinary polling cannot overwrite active results, scan happens only on button press, returned vessel opens the existing panel/intelligence flow, clear restores ordinary state, and provider errors never inject demo vessels.
- [ ] **Step 5: Integrate separate `liveVessels`/`areaVessels` state** and retain selected scan vessel/track behavior.
- [ ] **Step 6: Run** `npm.cmd test -- MapCanvas LiveDashboard AreaScanPanel` and require pass.

### Task 7: Startup, runbook, security audit, and compatibility

**Files:**
- Modify: `start_demo.ps1`
- Modify: `.env.example` if present
- Modify: `docs/demo-readiness-runbook.md`
- Modify/add focused startup tests under `tests/unit/`

**Interfaces:**
- Startup prints only `Datalastic API key: configured` or `Datalastic API key: not configured`.

- [ ] **Step 1: Write/extend failing startup tests** for hidden key, explicit live-ingest preservation, Datalastic default-off, anonymous fallback default-on, stable identity requirement, and non-blocking provider wording.
- [ ] **Step 2: Implement the minimal script/environment documentation changes** without generating keys or embedding a real value.
- [ ] **Step 3: Update the runbook** with environment, startup/browser commands, explicit illustrative demo URL, Area Scan steps, and separate Datalastic/GFW provenance.
- [ ] **Step 4: Run focused startup/docs/security checks**, including `rg` scans for `DATALASTIC_API_KEY`, Datalastic origins in frontend code, URL query authentication, and generated/secret files.
- [ ] **Step 5: Run relevant Open Waters, resilience, historical, Vessel Panel, and Intelligence regression suites** before the full gate.

### Task 8: Full verification, optional two-call smoke, and staging

**Files:**
- Modify only files required by failed verification; do not weaken tests.

**Interfaces:**
- Produces final evidence and a staged, uncommitted Datalastic Area Scan change set.

- [ ] **Step 1: Run full backend tests:** `& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp`.
- [ ] **Step 2: Run full frontend tests:** `npm.cmd test` from `apps/web`.
- [ ] **Step 3: Run production typecheck/build:** `npm.cmd run build` from `apps/web`.
- [ ] **Step 4: Run hygiene checks:** `git diff --check`, privacy/secret searches, and confirm no generated build output is staged.
- [ ] **Step 5: If and only if `DATALASTIC_API_KEY` exists, run one sanitized `/stat` call and one 1-NM Taiwan `vessel_inradius` call** through the implemented client; otherwise record an exact safe operator command.
- [ ] **Step 6: Review the complete diff against the spec**, fix only verified gaps, and rerun every affected focused/full gate.
- [ ] **Step 7: Stage only Area Scan design/plan/code/tests/docs**, then report staged status and stop before commit/push/merge.

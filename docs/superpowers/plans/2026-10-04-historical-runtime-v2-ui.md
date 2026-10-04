# Historical Runtime v2 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional, privacy-safe Historical Runtime v2 status to the current SeaWatch backend and Watch Floor without affecting live or scenario detection.

**Architecture:** A dedicated cached backend adapter reads only the compact runtime artifacts and a small service function converts any unavailable/unreadable state into a safe aggregate response. A separate typed frontend client feeds a self-contained card mounted in the stable Watch Floor sidebar shell; the card fetches once per mount and owns failures without touching Detection state.

**Tech Stack:** Python 3, pandas, PyArrow, joblib, FastAPI, pytest, React 18, TypeScript, Vitest, Testing Library, Vite.

**Spec:** `docs/superpowers/specs/2026-10-04-historical-runtime-v2-ui-design.md`

## Global Constraints

- Remain on `feat/historical-runtime-v2-ui`; do not switch, reset, rebase, commit, push, or force-push.
- Preserve Datalastic, Area Scan, provider recovery, Detection thresholds/models, the Live Detection Hook, live source routes, and EEZ/12 NM/24 NM geometry.
- Historical Runtime is optional: absent configuration, missing SSD files, corrupt compact artifacts, or endpoint failure must not block startup or any Detection/Area Scan flow.
- Resolve `SEAWATCH_HISTORICAL_RUNTIME` first; otherwise resolve under `SEAWATCH_DATA_ROOT`; never hardcode a drive or copy runtime artifacts into Git.
- Load only the six compact Runtime v2 artifacts, lazily and once per process cache; never scan raw historical observations.
- Expose no local path, raw MMSI, GFW `vesselId`, credentials, or raw records through `GET /detection/historical`.
- Only `unique_9digit_candidate` is eligible for conservative cross-source matching; reject shared, malformed, non-nine-digit, and missing identities without normalization or inference.
- Keep Runtime v2 separate from `/historical/vessels/{public_id}/baseline`.
- Visible copy must contain `standardized hourly vessel presence` and `not raw/message-level AIS`; counts are historical presence observations, not AIS messages.
- Mount `HistoricalRuntimeCard` outside source/alert-specific keyed subtrees and fetch once per mount; source changes, alert refreshes, and selection changes must not refetch it.
- Do not add the traffic heatmap, map layers, per-alert context, or per-live-vessel historical joins.
- Preserve all requirement pins; ensure `joblib==1.6.0` and retain `uvicorn`.

## Review Focus

- An explicit runtime variable containing only whitespace must not override a valid `SEAWATCH_DATA_ROOT` fallback; Task 1 tests trimmed environment resolution.
- A directory with all six filenames but malformed metadata/context must degrade to the unavailable aggregate instead of returning 500 or leaking an exception/path; Task 2 tests corrupt-bundle handling.
- Unexpected raw identifiers and filesystem-looking strings present in fixture records must never appear in the serialized summary; Tasks 1 and 2 test response serialization, not only dictionary keys.
- React rerenders caused by source switching and alert selection must preserve the mounted card and one request; Task 4 asserts the client call count through both transitions.
- A rejected/failed historical request racing with successful live loading must render the calm unavailable card while live controls and alerts remain usable; Task 4 exercises both outcomes in one integration test.

---

### Task 1: Compact Historical Runtime Adapter

**Files:**
- Create: `apps/api/seawatch/detection/historical_runtime.py`
- Create: `tests/unit/test_historical_runtime_v2.py`
- Modify: `requirements.txt`
- Modify: `.env.example`

**Interfaces:**
- Consumes: the six compact artifacts named by `REQUIRED_FILES` and environment variables `SEAWATCH_HISTORICAL_RUNTIME` / `SEAWATCH_DATA_ROOT`.
- Produces: `bundle_dir() -> Path | None`, `available() -> bool`, `summary() -> dict[str, Any]`, `lookup_mmsi(mmsi: str) -> dict[str, Any] | None`, `traffic_at(lat: float, lon: float) -> dict[str, Any] | None`, `context_bundle() -> dict[str, Any]`, and `clear_cache() -> None`.

- [ ] **Step 1: Write failing resolution and availability tests**

Add tests named `test_explicit_runtime_path_wins`, `test_data_root_fallback_is_used`, `test_blank_explicit_path_uses_data_root`, and `test_missing_configuration_or_bundle_is_unavailable`. Assert the exact bundle path without any drive default.

- [ ] **Step 2: Run the resolution tests and verify RED**

Run: `python -m pytest tests/unit/test_historical_runtime_v2.py -k "runtime_path or data_root or missing_configuration" -v`

Expected: collection/import failure because `historical_runtime` does not exist.

- [ ] **Step 3: Implement resolution, required-file checks, and configuration documentation**

Implement `bundle_dir() -> Path | None` and `available() -> bool`; add path-neutral examples to `.env.example`; add `joblib==1.6.0` and retain/add the current `uvicorn` pin without changing other versions.

- [ ] **Step 4: Run the resolution tests and verify GREEN**

Run the Step 2 command.

Expected: all selected tests pass.

- [ ] **Step 5: Write failing compact-loader, summary, privacy, identity, traffic, and cache tests**

Build a temporary six-artifact bundle with deliberately sensitive fixture values. Add tests named `test_valid_compact_bundle_returns_expected_summary`, `test_summary_omits_paths_and_raw_identifiers`, `test_only_unique_nine_digit_candidates_are_indexed`, `test_shared_and_invalid_mmsi_are_rejected`, `test_traffic_lookup_rounds_to_coarse_tenth_degree_cell`, `test_loader_reads_only_compact_artifacts`, and `test_loader_is_cached_across_summary_calls`. Assert all verified aggregate values and that no filename resembling a raw dataset is opened.

- [ ] **Step 6: Run the new adapter tests and verify RED**

Run: `python -m pytest tests/unit/test_historical_runtime_v2.py -v`

Expected: failures for missing loader/summary/lookup behavior.

- [ ] **Step 7: Implement the cached compact loader and internal lookup APIs**

Port the verified adapter semantics, filtering the MMSI index before `set_index`, enforcing one-to-one safe candidates, rounding traffic coordinates to one decimal degree, converting pandas/NumPy values to API-safe scalars, and returning only aggregate allowlisted summary fields.

- [ ] **Step 8: Run all adapter tests and verify GREEN**

Run the Step 6 command.

Expected: all adapter tests pass and reader-call assertions show one cached load.

### Task 2: Privacy-Safe Detection Historical Endpoint

**Files:**
- Modify: `apps/api/seawatch/detection/service.py`
- Modify: `apps/api/seawatch/api/detection.py`
- Create: `tests/unit/test_detection_historical_api.py`

**Interfaces:**
- Consumes: `historical_runtime.available()` and `historical_runtime.summary()` from Task 1.
- Produces: `get_historical_summary() -> dict[str, Any]` and `GET /detection/historical` returning HTTP 200 for both aggregate available and unavailable states.

- [ ] **Step 1: Write failing service and endpoint tests**

Add tests named `test_historical_endpoint_returns_safe_available_summary`, `test_historical_endpoint_returns_200_when_bundle_absent`, `test_corrupt_bundle_degrades_without_path_or_exception_leak`, and `test_historical_endpoint_never_initializes_live_or_scenario_runtime`. Serialize each response and assert forbidden fixture MMSI, GFW ID, local path, and credential strings are absent.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `python -m pytest tests/unit/test_detection_historical_api.py -v`

Expected: 404 or import failure because the route/service function is absent.

- [ ] **Step 3: Implement the optional service boundary and route**

Add `get_historical_summary() -> dict[str, Any]` as a module-level optional-context boundary that returns a stable unavailable payload for missing or unreadable bundles without exception text. Add `/historical` before `/{alert_id}`-style routes and leave every current live branch byte-for-byte semantically intact.

- [ ] **Step 4: Run endpoint and current Detection route tests and verify GREEN**

Run: `python -m pytest tests/unit/test_detection_historical_api.py tests/unit/test_detection_stack.py tests/unit/test_area_scan_detection_hook.py -v`

Expected: all tests pass, including existing `source=live` route coverage.

### Task 3: Typed Client and Self-Contained Card

**Files:**
- Create: `apps/web/src/api/historicalRuntime.ts`
- Create: `apps/web/src/api/historicalRuntime.test.ts`
- Create: `apps/web/src/features/watch/HistoricalRuntimeCard.tsx`
- Create: `apps/web/src/features/watch/HistoricalRuntimeCard.test.tsx`
- Modify: `apps/web/src/features/watch/watch.css`

**Interfaces:**
- Consumes: `getJson<T>(path, signal)` from `apps/web/src/api/client.ts` and the aggregate endpoint fields from Task 2.
- Produces: `HistoricalRuntimeSummary`, `getHistoricalRuntimeSummary(signal?: AbortSignal)`, `formatHistoricalCount(value, style)`, and `<HistoricalRuntimeCard />` with an effect whose dependency list is empty.

- [ ] **Step 1: Write the failing typed-client test**

Assert one GET to `/detection/historical`, forwarding the abort signal and returning the typed aggregate unchanged.

- [ ] **Step 2: Run the client test and verify RED**

Run: `npm test -- --run src/api/historicalRuntime.test.ts` from `apps/web`.

Expected: module-not-found failure.

- [ ] **Step 3: Implement the typed client**

Define the distinct aggregate interfaces using backend snake_case fields and delegate to shared `getJson` without adding host/base logic.

- [ ] **Step 4: Run the client test and verify GREEN**

Run the Step 2 command.

Expected: client test passes.

- [ ] **Step 5: Write failing card rendering and lifecycle tests**

Add tests for the loading label; available formatted values `33.2M`, `400.8K`, `2,457`, `6,528`, and `66,043`; exact contract phrases; conservative-candidate tooltip/note; unavailable payload; rejected request; absence of path/MMSI/GFW values; and one fetch across ordinary parent rerenders. Include null/missing optional aggregate fields so incomplete safe responses do not crash.

- [ ] **Step 6: Run card tests and verify RED**

Run: `npm test -- --run src/features/watch/HistoricalRuntimeCard.test.tsx` from `apps/web`.

Expected: module-not-found or missing-render failures.

- [ ] **Step 7: Implement the card and scoped styles**

Use one mount effect with `AbortController`, local `loading | available | unavailable` state, aggregate-only rendering, neutral unavailable styling, and no dependencies on Watch Floor state. Do not add a query library, heatmap, map data, alert join, or retry loop.

- [ ] **Step 8: Run client and card tests and verify GREEN**

Run: `npm test -- --run src/api/historicalRuntime.test.ts src/features/watch/HistoricalRuntimeCard.test.tsx` from `apps/web`.

Expected: all focused frontend unit tests pass.

### Task 4: Stable Watch Floor Integration

**Files:**
- Modify: `apps/web/src/features/watch/WatchFloor.tsx`
- Modify: `apps/web/src/features/watch/watch.css`
- Modify: `apps/web/src/features/watch/WatchFloor.test.tsx`

**Interfaces:**
- Consumes: `<HistoricalRuntimeCard />` from Task 3.
- Produces: a stable left-sidebar shell containing the card and existing `<AlertQueue />`, with no key or source/selection conditional around the card.

- [ ] **Step 1: Write failing stable-mount and failure-isolation integration tests**

Add `renders_historical_card_once_across_source_and_selection_changes` and `historical_failure_does_not_break_live_watch_floor`. Assert the historical client is called exactly once after scenario load, Live switch, and alert selection; assert rejected history renders unavailable while live scenario, source control, and live alert remain usable.

- [ ] **Step 2: Run Watch Floor tests and verify RED**

Run: `npm test -- --run src/features/watch/WatchFloor.test.tsx` from `apps/web`.

Expected: card/call-count assertions fail because the card is not integrated.

- [ ] **Step 3: Mount the card in the stable sidebar shell**

Place the card as a direct child of a non-keyed left-column wrapper beside the always-mounted Alert Queue. Update desktop and existing responsive CSS so the wrapper owns the first grid column without changing map/detail behavior.

- [ ] **Step 4: Run all focused Watch Floor tests and verify GREEN**

Run: `npm test -- --run src/features/watch/WatchFloor.test.tsx src/features/watch/api.live.test.ts` from `apps/web`.

Expected: all tests pass and the historical client remains at one call.

### Task 5: Verification, Profiling, and Final Privacy Review

**Files:**
- Modify only if a verification failure exposes a requirement defect; apply TDD before any fix.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: fresh verification evidence and the requested 26-item final report; no commits or pushes.

- [ ] **Step 1: Run focused backend suites**

Run: `python -m pytest tests/unit/test_historical_runtime_v2.py tests/unit/test_detection_historical_api.py tests/unit/test_detection_stack.py tests/unit/test_area_scan_detection_hook.py -v`

Expected: all pass.

- [ ] **Step 2: Run focused frontend suites**

Run: `npm test -- --run src/api/historicalRuntime.test.ts src/features/watch/HistoricalRuntimeCard.test.tsx src/features/watch/WatchFloor.test.tsx src/features/watch/api.live.test.ts` from `apps/web`.

Expected: all pass.

- [ ] **Step 3: Run broader backend and frontend suites**

Run: `python -m pytest` from the repository root, then `npm test -- --run` from `apps/web`.

Expected: all pass, or report exact pre-existing/environmental failures without masking them.

- [ ] **Step 4: Run static and build verification**

Run from `apps/web`: `npx tsc --noEmit`, then `npm run build`.

Expected: both exit zero.

- [ ] **Step 5: Exercise the real SSD endpoint and measure cache behavior**

Set `SEAWATCH_HISTORICAL_RUNTIME` only for the local verification process, call `GET /detection/historical` twice, record first/cached latency and a rough process-memory observation when available, and confirm verified aggregate values. Do not persist the SSD path.

Expected: both calls return 200 and `available: true`; the second call performs no artifact reload. If the bundle is unavailable in this environment, report manual E2E as not ready rather than fabricating results.

- [ ] **Step 6: Run final diff, status, and forbidden-output review**

Run `git diff --check`, `git status --short`, inspect `git diff`, and search changed frontend/API response code for `D:\`, raw fixture MMSI/GFW identifiers, heatmap additions, live-route changes, and wording that presents observations as AIS messages.

Expected: no whitespace errors; only intended uncommitted files; no Critical or Important privacy, availability, identity, live-regression, or data-model findings.

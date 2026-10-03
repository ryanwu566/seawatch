# Area Scan Detection Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed each successful real Datalastic Area Scan batch exactly once into the existing SeaWatch Detection stack, retain live tracks across scans, and expose privacy-safe live results through the existing Watch Floor.

**Architecture:** `LiveRuntime` will own one `LiveDetectionRuntime` for the process. `AreaScanService` will invoke one failure-isolated observation callback after provider normalization, deduplication, and exact polygon filtering; the live runtime will reuse one `DetectionContext`, one canonical `LiveDetectionAnalyzer`, the existing alert fusion, and the existing optional ML scoring path. Existing scenario/replay routes remain the default, while `source=live` selects cached live metadata, tracks, alerts, and details using the same response shapes with opaque public vessel IDs.

**Tech Stack:** Python 3, FastAPI, dataclasses, NumPy/pandas/scikit-learn through the existing Detection stack, React 18, TypeScript, Vitest, pytest.

**Spec:** `C:/Users/吳奕陽/.codex/attachments/52001c10-3f13-4127-b9b4-032e15bb8eb3/Pasted text.txt`

## Global Constraints

- Do not change detector thresholds, rules, fusion, Datalastic billing/authentication, Area Scan geometry, vessel markers, EEZ geometry, or historical SSD integration.
- One explicit uncached Scan Area provider workflow produces one normalized observation batch and at most one Detection update; Detection never calls Datalastic.
- Preserve the canonical live adapter's deduplication, retention, expiry, historical-read, capacity, and fleet-analysis semantics.
- Keep deterministic Detection functional without ML or an LLM; never train or fabricate a model or result.
- Browser-facing live Detection payloads contain opaque `public_id` values and no raw MMSI, IMO, provider UUID, or secret.
- A successful provider scan remains successful if Detection is unavailable or raises; a failed provider scan never updates Detection.
- Do not commit, push, reset, rebase, switch branches, deploy, or make real provider calls.

## Review Focus

- Concurrent scans of different polygons must serialize runtime mutation without corrupting the latest successful result; covered by the runtime concurrency/failure-isolation test in Task 1.
- Cached or coalesced Area Scan responses must not re-ingest an already processed provider batch; covered by the callback-count test in Task 2.
- Unknown provider observation times must not become fresh motion merely because the server received a scan; covered by the freshness test in Task 2.
- Redaction must replace raw MMSI even when Detection used it as a fallback vessel name inside titles or evidence; covered by the deep payload redaction test in Task 3.
- Switching Watch Floor sources must not mutate the selected scenario/region or enable replay controls for live data; covered by the frontend source-switch test in Task 4.

---

### Task 1: Process-owned live Detection runtime

**Files:**
- Create: `apps/api/seawatch/detection/live_runtime.py`
- Modify: `apps/api/seawatch/detection/service.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Test: `tests/unit/test_area_scan_detection_hook.py`

**Interfaces:**
- Consumes: `LiveDetectionAnalyzer`, `RollingTrackBuffer`, `DetectionService` context/model/feedback state, and the shared `VesselIdentityRegistry`.
- Produces: `LiveDetectionRuntime.update(observations, *, scanned_at)`, `snapshot()`, `public_meta()`, `public_tracks()`, `public_alerts()`, `public_alert(alert_id)`, `set_alert_status(...)`, and `add_alert_note(...)`.

- [ ] **Step 1: Write failing runtime tests**

Add tests proving process ownership/reset, repeated-scan accumulation, exact-repoll deduplication, one fleet-wide engine call, context reuse, latest-result caching, first-scan `insufficient_history`, bounded state, failure isolation, and concurrent update safety.

- [ ] **Step 2: Run the focused runtime tests and verify they fail**

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py -q`

Expected: FAIL because the live runtime and ownership field do not exist.

- [ ] **Step 3: Implement the minimal runtime and Detection dependency seam**

Create one lock-protected runtime with a lazily built, reused context/analyzer; use `density="sparse_live"`, Area Scan freshness for vessel staleness, the current feedback/watch objects, real learned context when available, and static canonical Taiwan context with an explicit degraded context state otherwise.

- [ ] **Step 4: Add existing ML second-opinion reuse**

Only after deterministic alert candidates exist, compute existing window features for the accumulated fleet and call the existing loaded models plus `score_alert`; leave `Alert.ml` as `None` when no applicable model exists and isolate optional scoring errors.

- [ ] **Step 5: Run focused runtime tests**

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py -q`

Expected: PASS.

### Task 2: Single Area Scan hook and failure boundary

**Files:**
- Modify: `apps/api/seawatch/live/area_scan.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/api/live.py`
- Test: `tests/unit/test_area_scan_detection_hook.py`
- Test: `tests/unit/test_area_scan.py`

**Interfaces:**
- Consumes: `LiveDetectionRuntime.update(...)` from Task 1.
- Produces: one optional async/sync normalized-observation sink on `AreaScanService` and an additive `detection` status object on Area Scan responses.

- [ ] **Step 1: Write failing Area Scan integration tests**

Cover one callback per uncached provider workflow, zero callback on provider failure, no callback replay on cache hits/coalesced requests, zero extra provider calls, unknown observation-time exclusion, distinct observed/scanned/analysis timestamps, and scan success when the callback raises.

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py tests/unit/test_area_scan.py -q`

Expected: FAIL on missing callback/status behavior.

- [ ] **Step 3: Implement the post-normalization callback**

Invoke it once after provider validation, reconciliation, exact polygon filtering, and batch-size validation; pass only observations with real provider timestamps; await async callbacks; catch and log only a sanitized Detection failure.

- [ ] **Step 4: Wire process ownership and response status**

Have `_build_runtime()` construct one live Detection runtime and pass an `asyncio.to_thread` callback into `AreaScanService`; add the runtime snapshot to the successful `/live/area-scan` response without changing provider error handling.

- [ ] **Step 5: Run Area Scan integration and security tests**

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py tests/unit/test_area_scan.py tests/unit/test_area_scan_access.py tests/unit/test_live_failover_api.py -q`

Expected: PASS with no network traffic.

### Task 3: Privacy-safe live Detection API

**Files:**
- Modify: `apps/api/seawatch/api/detection.py`
- Modify: `apps/api/seawatch/detection/live_runtime.py`
- Test: `tests/unit/test_area_scan_detection_hook.py`
- Test: `tests/unit/test_detection_stack.py`

**Interfaces:**
- Consumes: cached public methods from Task 1 and the existing `source`-default scenario service.
- Produces: `source=live` support on scenario, tracks, alerts, alert detail, status, and note routes; omitted `source` retains current scenario/replay behavior.

- [ ] **Step 1: Write failing API/redaction tests**

Assert the Watch Floor response shapes, status and timestamps, alert-to-track `public_id` equality, recursive removal of raw MMSI/provider IDs, live feedback mutations, empty/path-agent-free live detail, and unchanged default scenario endpoints.

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py tests/unit/test_detection_stack.py -q`

Expected: FAIL because `source=live` is not handled.

- [ ] **Step 3: Implement additive source routing and safe serialization**

Use the shared identity registry for every live Track/Alert/Event vessel reference, include `public_id`, retain compatible response keys with opaque values, replace mapped raw identifiers embedded in strings, and never invoke path analysis for live detail.

- [ ] **Step 4: Run API and Detection regression tests**

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py tests/unit/test_detection_stack.py -q`

Expected: PASS.

### Task 4: Existing Watch Floor live source mode

**Files:**
- Modify: `apps/web/src/features/watch/api.ts`
- Modify: `apps/web/src/features/watch/useWatch.ts`
- Modify: `apps/web/src/features/watch/WatchFloor.tsx`
- Modify: `apps/web/src/features/watch/AlertPanel.tsx`
- Test: `apps/web/src/features/watch/WatchFloor.test.tsx` or the nearest existing Watch Floor test file

**Interfaces:**
- Consumes: Task 3's `source=live` response-compatible endpoints.
- Produces: an explicit Scenario/Live selector that reloads the existing AlertQueue, AlertPanel, FactorCards, and WatchMap without replay/tuning controls in live mode.

- [ ] **Step 1: Write failing frontend source-mode tests**

Assert source-specific request URLs, live status rendering, public vessel ID display/linkage, hidden replay/tuning controls in live mode, and restoration of scenario mode without a backend region mutation.

- [ ] **Step 2: Run the focused frontend tests and verify they fail**

Run: `npm test -- --run apps/web/src/features/watch/WatchFloor.test.tsx`

Working directory: `apps/web`

Expected: FAIL because no live source selector exists.

- [ ] **Step 3: Implement the smallest source selector**

Thread `source` through existing client/read calls and mutations, reset selected alert state on source change, show live status/analysis time, and reuse all existing queue/detail/map components.

- [ ] **Step 4: Run focused tests, TypeScript, and build**

Run: `npm test -- --run src/features/watch/WatchFloor.test.tsx`

Run: `npx tsc --noEmit`

Run: `npm run build`

Working directory: `apps/web`

Expected: PASS.

### Task 5: Documentation, regressions, and final review

**Files:**
- Create: `docs/area-scan-detection-hook.md`
- Modify: only files needed to resolve verified Critical/Important findings.

**Interfaces:**
- Consumes: completed backend and frontend integration.
- Produces: practical architecture/manual-E2E documentation and verification evidence.

- [ ] **Step 1: Document operation and limitations**

Cover runtime ownership, hook location, track/context/ML lifecycle, identity, Watch Floor source selection, insufficient-history and degraded behavior, no-LLM behavior, and manual real-Datalastic steps without executing them.

- [ ] **Step 2: Run canonical and focused backend regressions**

Run: `python -m pytest tests/unit/test_live_detection_adapter.py -q`

Run: `python -m pytest tests/unit/test_area_scan_detection_hook.py tests/unit/test_detection_stack.py tests/unit/test_area_scan.py tests/unit/test_area_scan_access.py tests/unit/test_live_runtime.py tests/unit/test_live_failover_api.py -q`

Expected: PASS.

- [ ] **Step 3: Run full backend if feasible**

Run: `python -m pytest -q`

Expected: PASS, or report exact unrelated/pre-existing failures.

- [ ] **Step 4: Run full frontend suite and production build**

Run: `npm test`

Run: `npm run build`

Working directory: `apps/web`

Expected: PASS.

- [ ] **Step 5: Perform read-only Critical/Important review**

Inspect provider call count, identity/secret redaction, callback failure isolation, shared-state locking, context/analyzer reuse, fleet-wide analysis, first-scan eligibility, optional ML/LLM behavior, and scenario/source separation; fix every Critical/Important finding.

- [ ] **Step 6: Verify the worktree**

Run: `git diff --check`

Run: `git status --short`

Run: `git diff --stat`

Expected: no whitespace errors, only task-related uncommitted changes, and no commits or pushes.

# Datalastic Area Scan Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the independent-review blockers in Datalastic Area Scan while completing the approved backend/frontend workflow without exposing provider or identity secrets.

**Architecture:** Put a fail-closed, short-lived signed capability and process-wide admission budget in front of the paid endpoint; keep provider concurrency and retry control process-wide; reconcile Datalastic identities conservatively before normalization; and retain only bounded privacy-safe cache/track state. Keep ordinary live polling and Area Scan state, sources, selection provenance, requests, and tracks independent in the frontend.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, httpx, Shapely/PyProj, pytest; React 18, TypeScript, MapLibre, Vitest/Testing Library, Vite.

**Spec:** `docs/superpowers/specs/2026-10-03-datalastic-area-scan-design.md`, amended by the 2026-10-03 independent-review remediation request.

## Global Constraints

- Work only in `C:\Projects\seawatch` on existing branch `feat/datalastic-area-scan`; do not switch branches.
- Do not commit, push, merge, stage, print credentials, or perform paid smoke calls before all mocked/full gates pass.
- Every production behavior change starts with a focused failing test and ends with the affected focused suite passing.
- Reject unauthenticated, malformed, oversized, over-circle, or over-budget scans before any Datalastic call.
- Keep `DATALASTIC_API_KEY`, operator credential, capability-signing material, and the signed capability out of frontend JavaScript and the Vite bundle. The browser receives the capability only as a short-lived HttpOnly cookie.
- Only unambiguous structurally valid MMSI can join Datalastic to historical identity; UUID/IMO remain provider-local.
- Preserve ordinary live polling, tracks, Open Waters ingestion, and historical behavior.

## Review Focus

1. A signed capability is scoped, expiring, constant-time verified, and disabled when its signing key is absent; CORS never grants access.
2. Admission reserves the whole worst-case provider-request cost (circles plus one shared retry) atomically, so rejection starts zero upstream calls.
3. Identity reconciliation is order-independent across missing/conflicting MMSI/UUID combinations and never upgrades ambiguous rows to historical identity.
4. Cache publication/removal is atomic under owner cancellation or provider failure, and bounded state deterministically sweeps expired entries.
5. Frontend request generations, aborts, style reloads, same-public-ID source selection, and live polling cannot overwrite the Area Scan overlay or track provenance.

---

### Task 1: Capability authentication, request limits, and admission budget

**Files:**
- Create: `apps/api/seawatch/live/area_scan_access.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/api/live.py`
- Test: `tests/unit/test_area_scan_access.py`
- Test: `tests/unit/test_area_scan.py`

**Interfaces:**
- Produces `AreaScanAccessConfig.from_env`, `mint_area_scan_capability`, `verify_area_scan_capability`, and `AreaScanAdmissionController.authorize(provider_requests)`.
- `POST /live/area-scan/session` authenticates a server-configured operator credential under a bounded body and issues a 15-minute capability in a Secure-by-default HttpOnly/SameSite cookie.
- `POST /live/area-scan` requires JSON and a non-simple confirmation header for cookie auth, reads at most a hard 64 KiB only after capability verification, validates before admission, and atomically reserves `circle_count + 1` provider requests.

- [ ] Add route/unit tests for missing/invalid/expired capability, disabled configuration, oversized/malformed bodies, scan/request budget exhaustion, and zero provider calls.
- [ ] Run the focused tests and confirm the new assertions fail for missing enforcement.
- [ ] Implement signed scoped capabilities, capped streaming body parsing, and fixed-window process-wide admission.
- [ ] Rerun the focused tests and require pass.

### Task 2: Strict provider parsing, error taxonomy, shared concurrency, and early stop

**Files:**
- Modify: `apps/api/seawatch/live/datalastic.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Test: `tests/unit/test_datalastic.py`

**Interfaces:**
- Integral numeric strings/integers parse; booleans, fractional values, non-finite values, and malformed identifiers fail closed.
- The runtime-owned client request governor enforces global concurrency two across `/stat` and every scan.
- HTTP 402 maps to `quota_exhausted`; unsafe `Retry-After` values are neither slept nor reflected.

- [ ] Add failing tests for strict MMSI parsing, 402, negative/huge retry values, cross-scan concurrency, and terminal-failure queue cancellation.
- [ ] Implement the minimal client/provider changes.
- [ ] Run the focused provider suite and require pass.

### Task 3: Tight geometry cover and exact canonicalization

**Files:**
- Modify: `apps/api/seawatch/live/area_scan.py`
- Test: `tests/unit/test_area_scan.py`
- Modify: `docs/superpowers/specs/2026-10-03-datalastic-area-scan-design.md`

**Interfaces:**
- Single-circle polygons use the smallest conservative radius rounded up with a fixed geodesic/numerical margin; grid circles remain at 45 NM and all radii remain `<=45`.
- Canonical keys normalize topology without lossy coordinate rounding.

- [ ] Add failing tiny/medium radius and sub-1e-6/equivalent-ring/hole canonicalization tests.
- [ ] Implement tight geodesic radius selection and exact normalized-WKB keys.
- [ ] Correct the rectangle example to a closed four-corner ring.
- [ ] Run geometry tests and require pass.

### Task 4: Provenance-safe identity reconciliation and bounded state

**Files:**
- Modify: `apps/api/seawatch/live/identity.py`
- Modify: `apps/api/seawatch/live/area_scan.py`
- Test: `tests/unit/test_area_scan.py`
- Test: `tests/unit/test_live_identity.py`

**Interfaces:**
- Reconciliation groups provider UUID first, admits a valid MMSI only when UUID/MMSI evidence is unambiguous, and applies no historical identity to conflicts/placeholders.
- Cache is TTL-swept and entry-bounded; tracks retain only normalized points under vessel/point/TTL caps with deterministic eviction.

- [ ] Add failing order-independent mixed/conflicting identity tests, placeholder tests, cache sweep/cap tests, and track cleanup/cap tests.
- [ ] Implement conservative reconciliation, source-specific identity expiry, and bounded cache/track storage.
- [ ] Add and pass explicit observation freshness-state tests without changing provider timestamps.

### Task 5: Atomic in-flight coalescing and source-qualified tracks

**Files:**
- Modify: `apps/api/seawatch/live/area_scan.py`
- Modify: `apps/api/seawatch/api/live.py`
- Modify: `apps/web/src/api/live.ts`
- Test: `tests/unit/test_area_scan.py`
- Test: `apps/web/src/api/liveAreaScan.test.ts`

**Interfaces:**
- Shared work publishes cache before removing its in-flight entry and survives any waiter cancellation.
- `GET /live/vessels/{public_id}/track?source=datalastic` resolves only Area Scan; omitted source retains ordinary behavior; invalid/unknown IDs return generic errors.

- [ ] Add failing owner/follower cancellation, provider-exception cleanup, immediate-third-request, same-ID source, validation, and generic-error tests.
- [ ] Implement atomic task publication/cleanup and source-qualified track routing/client calls.
- [ ] Run affected backend/frontend API tests and require pass.

### Task 6: Operator-session panel and race-safe dashboard state

**Files:**
- Modify: `apps/web/src/api/live.ts`
- Modify: `apps/web/src/components/AreaScanPanel.tsx`
- Modify: `apps/web/src/components/AreaScanPanel.test.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.test.tsx`
- Modify: `apps/web/src/i18n/dictionaries.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Operator submits the out-of-band credential once; the backend issues an HttpOnly capability cookie. React immediately clears the credential and never receives or stores the signed capability.
- Dashboard owns distinct `liveVessels`, `areaVessels`, selected source, abort controller, and monotonically increasing scan generation.

- [ ] Add failing A/B out-of-order, clear-pending, live-poll isolation, same-ID selection, source-qualified track, and error/no-demo-fallback tests.
- [ ] Implement request generations/abort, operator session state, independent result state, and provenance-aware selection.
- [ ] Run focused panel/dashboard/API tests and require pass.

### Task 7: MapLibre drawing and separate overlay lifecycle

**Files:**
- Modify: `apps/web/src/components/MapCanvas.tsx`
- Modify: `apps/web/src/components/MapCanvas.test.tsx`

**Interfaces:**
- Props add draw mode, selected geometry, Area Scan vessels, selected source, and geometry callback.
- Dedicated geometry and vessel sources/layers restore on style reload and never replace `live-vessels`.

- [ ] Add failing polygon/rectangle completion, Escape/pointer cleanup, clear, source isolation, marker selection, fly/follow, and style-reload tests.
- [ ] Implement MapLibre-native drawing and dedicated sources/layers with cleanup.
- [ ] Run MapCanvas and dashboard tests and require pass.

### Task 8: Runbook, full verification, and optional bounded smoke

**Files:**
- Modify: `.env.example`
- Modify: `start_demo.ps1`
- Modify: `docs/demo-readiness-runbook.md`
- Modify only files required by verified failures.

**Interfaces:**
- Documents operator login/capability expiry, server-only secrets, Secure-cookie default and explicit loopback HTTP exception, process budgets, limits, source-qualified tracks, provider-cost behavior, and safe operator workflow.
- `start_demo.ps1` strips backend-only environment values from the npm/Vite child and restores them before starting FastAPI.

- [ ] Add/extend startup/security tests before changing scripts or environment examples.
- [ ] Update runbook/config examples without real values or browser-bundled secrets.
- [ ] Run focused backend suites, geometry/identity/history/live regressions, full backend suite, focused/full frontend suites, TypeScript/Vite build, diff/secret scans.
- [ ] Only if a real key exists after every mocked/full gate passes, run exactly one sanitized `/stat` and one 1-NM Taiwan query; otherwise report skipped.
- [ ] Review complete unstaged diff and report without committing, pushing, or staging.

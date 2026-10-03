# Live Detection Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded provider-independent seam from normalized live observations to the existing fleet-level detection engine.

**Architecture:** Add one detection-owned module containing an identity-aware rolling buffer, a `DetectionTrackAdapter`, and a reusable `LiveDetectionAnalyzer`. Reuse `engine.REQUIREMENTS`, `engine.eligibility`, `engine.analyze`, `Track`, `AnalysisResult`, `Event`, and `Alert`; do not modify shared provider/runtime/API/UI files.

**Tech Stack:** Python 3, dataclasses, NumPy, existing SeaWatch live and detection models, Pytest.

**Spec:** `docs/live-detection-adapter.md` and the user-provided 2026-10-03 implementation brief.

## Global Constraints

- Stay on `feat/detection-live-adapter`; do not merge, commit, or push.
- Do not call Datalastic or any provider network API.
- Do not modify shared live runtime/API/UI files.
- Never fabricate/interpolate positions, speed, course, heading, MMSI, or identity.
- Reuse the existing fleet-level engine, result types, fusion, optional ML behavior, and advisory path-agent placement.
- Context is injected once and reused; simulated context is never an implicit fallback.
- Memory is bounded by vessel count, points per vessel, retention time, and stale eviction.

## Review Focus

- Fractional/invalid MMSI must remain source-scoped and never be truncated into a Detection identity.
- Conflicting same-timestamp observations must adapt deterministically without duplicate engine timestamps.
- Non-finite optional movement values must become explicit missing values rather than poison NumPy/detector calculations.
- Vessel-cap eviction must be deterministic when latest timestamps tie.
- A multi-source MMSI track must retain provenance while producing one cross-source Detection track.

---

### Task 1: Bounded rolling live-track buffer

**Files:**
- Create: `apps/api/seawatch/detection/live_adapter.py`
- Create: `tests/unit/test_live_detection_adapter.py`

**Interfaces:**
- Consumes: `LiveVesselObservation`; injected `Callable[[], datetime]` clock.
- Produces: `LiveTrackIdentity`, `BufferedLiveTrack`, and `RollingTrackBuffer.update`, `update_many`, `evict_stale`, `snapshot`, `vessel_count`, `point_count`.

- [x] Write failing tests for invalid/non-finite coordinates, exact duplicates, out-of-order order, chronological snapshots, valid-MMSI cross-source grouping, fractional-MMSI isolation, point/vessel caps, retention, stale eviction, and aggregate memory bounds.
- [x] Run `python -m pytest tests/unit/test_live_detection_adapter.py -q`; expect import failure because the module does not exist.
- [x] Implement validation, stable identity, deterministic ordering, duplicate suppression, retention trimming, deterministic eviction, and thread-safe snapshots.
- [x] Re-run the focused file; expect buffer tests to pass.
- [x] Do not commit; record evidence in the execution ledger.

### Task 2: Detection Track adapter and eligibility

**Files:**
- Modify: `apps/api/seawatch/detection/live_adapter.py`
- Modify: `tests/unit/test_live_detection_adapter.py`

**Interfaces:**
- Consumes: `BufferedLiveTrack` from Task 1; `history.ship_category`; `engine.eligibility`/`REQUIREMENTS`.
- Produces: `DetectionTrackAdapter.to_track`, `to_tracks`, and `eligibility`; existing `Track` objects with backend-only provenance in `extra`.

- [x] Add failing tests for valid conversion, missing SOG/COG/heading, nav status, ship type, destination, source/synthesized provenance, no fabricated MMSI, deterministic same-time selection, and the actual eligibility matrix.
- [x] Run the adapter tests; expect missing `DetectionTrackAdapter` failures.
- [x] Implement array mapping with `NaN`/`None`/`-1` unknown representations, static-field selection, timestamp deduplication, and eligibility delegation.
- [x] Re-run the focused file; expect buffer and adapter tests to pass.
- [x] Do not commit; record evidence in the execution ledger.

### Task 3: Reusable fleet-level live analyzer

**Files:**
- Modify: `apps/api/seawatch/detection/live_adapter.py`
- Modify: `tests/unit/test_live_detection_adapter.py`

**Interfaces:**
- Consumes: buffer/adapter from Tasks 1-2 and one caller-supplied `DetectionContext`.
- Produces: `LiveDetectionAnalyzer.ingest`, `tracks`, `eligibility`, `analyze`, and `update`, returning existing `AnalysisResult`.

- [x] Add failing tests for one-point/short-history safety, a real qualifying position-jump event and fused alert, multi-vessel rendezvous in one call, context reuse, `Alert.ml is None` without a model, and operation while network connection functions are disabled.
- [x] Run the service tests; expect missing `LiveDetectionAnalyzer` failures.
- [x] Implement the narrow orchestration service using `engine.analyze` exactly once per analysis over all eligible current tracks.
- [x] Re-run the focused file; expect all live-adapter tests to pass.
- [x] Do not commit; record evidence in the execution ledger.

### Task 4: Documentation, performance, and regression verification

**Files:**
- Modify: `docs/live-detection-adapter.md`
- Verify: `apps/api/seawatch/detection/live_adapter.py`
- Verify: `tests/unit/test_live_detection_adapter.py`

**Interfaces:**
- Consumes: completed adapter API and synthetic observations.
- Produces: measured 100/500/1,000-vessel timing/memory evidence and final integration guidance.

- [x] Review the documentation against the implemented signatures, field mapping, identity, eligibility, multi-vessel behavior, context lifecycle, analysis modes, ML/agent behavior, privacy boundary, and future hook.
- [x] Benchmark buffer update, adapter conversion, and detection invocation for 100, 500, and 1,000 synthetic vessels; capture measured timings and peak traced memory without adding provider calls.
- [x] Run the new focused tests and the four required existing detection suites.
- [x] Run the broader backend suite if the environment permits.
- [x] Run `git diff --check`, inspect `git diff --stat`, and confirm no prohibited shared files changed.
- [x] Do not commit or push.

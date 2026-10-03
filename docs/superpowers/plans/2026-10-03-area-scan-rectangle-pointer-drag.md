# Area Scan Rectangle Pointer Drag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rectangle mode consume a native left-button pointer drag on the MapLibre canvas, preview and commit one normalized GeoJSON rectangle, and enable the existing Area Scan submission flow.

**Architecture:** Replace the mixed MapLibre-mouse/global-pointer lifecycle with one native canvas pointer lifecycle using pointer capture and `map.unproject`. Disable drag pan and show a drawing cursor on Rectangle-mode entry; use one rectangle builder/finalizer for preview/commit, reject zero-area drags, and preserve the existing polygon handlers unchanged.

**Tech Stack:** React 18, TypeScript 5.6, MapLibre GL JS 4.7, Vitest 2.1, Testing Library.

**Spec:** Current user request dated 2026-10-03.

## Global Constraints

- Stay on `feat/datalastic-area-scan`; do not switch or create branches.
- Do not commit or push.
- Do not make a real Datalastic request.
- Preserve unrelated worktree changes and the completed polygon finalization behavior.
- Rectangle output uses actual start/end coordinates normalized to min/max longitude and latitude.
- Escape and zero-area drags never commit geometry.

## Review Focus

1. Browser `pointerup` must finalize rather than clear state before a later compatibility `mouseup`.
2. Drag pan must be disabled before pointer-down and restored exactly once after completion/cancellation.
3. Pointer capture must keep move/up events attached to the drawing canvas.
4. Reverse-direction and zero-area drags must respectively normalize or reject geometry.
5. Polygon click/start-vertex/double-click/Escape behavior must remain unchanged.

---

### Task 1: Reproduce the native pointer failure

**Files:**
- Modify: `apps/web/src/components/MapCanvas.test.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.areaScanFlow.test.tsx`

**Interfaces:**
- Consumes: the real `MapCanvas`, `LiveDashboard`, `AreaScanPanel`, MapLibre canvas boundary, and browser `fetch` boundary.
- Produces: tests for native pointer preview/commit, pointer capture, drag-pan suppression, zero-area rejection, Escape cancellation, Clear, and one backend scan request.

- [x] Extend only the MapLibre test double so it exposes a real canvas element, `unproject`, pointer capture state, and preview payloads.
- [x] Replace direct MapLibre rectangle callback tests with native canvas pointer events and literal normalized geometry assertions.
- [x] Upgrade the real-component rectangle test to submit once and assert the exact same-origin `/live/area-scan` body; add zero-area and Escape cases.
- [x] Run the focused rectangle tests and confirm they fail because no native pointer lifecycle is installed.

### Task 2: Implement one rectangle pointer lifecycle

**Files:**
- Modify: `apps/web/src/components/MapCanvas.tsx`

**Interfaces:**
- Produces: `rectangleFromCorners(start, end) -> GeoJSON.Polygon | null`, one canvas pointer-down/move/up lifecycle, and one rectangle finalizer.
- Consumes: `map.unproject`, `map.dragPan`, `map.getCanvas`, `rectangleStartRef`, `areaGeometryRef`, and `onAreaGeometryChangeRef`.

- [x] Disable drag pan and set a crosshair cursor when Rectangle mode becomes active.
- [x] On primary left pointer-down, capture the pointer and record the unprojected start coordinate.
- [x] On matching pointer-move, update the local normalized rectangle preview without committing.
- [x] On matching pointer-up, release capture and finalize exactly once when the rectangle has non-zero area.
- [x] On Escape/mode exit/unmount, clear transient rectangle state, release capture, remove preview as appropriate, and restore interactions without committing.
- [x] Run focused tests and require all pointer, rectangle, and polygon cases to pass.

### Task 3: Verification

**Files:**
- Verify only; do not expand scope for unrelated warnings.

**Interfaces:**
- Consumes: final implementation and tests.
- Produces: fresh evidence for the requested report.

- [x] Run focused MapCanvas, LiveDashboard Area Scan, and AreaScanPanel tests.
- [x] Run the complete frontend Vitest suite.
- [x] Run `tsc --noEmit` and a Vite production build.
- [x] Run `git diff --check`, inspect branch/status/staging, and review the bounded diff for polygon/security regressions.

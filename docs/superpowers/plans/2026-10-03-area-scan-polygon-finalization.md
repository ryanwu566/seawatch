# Area Scan Polygon Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MapCanvas commit a completed Area Scan polygon through the existing LiveDashboard callback when the user double-clicks or clicks the starting vertex.

**Architecture:** Keep draft rendering local to MapCanvas, but route both completion gestures through one finalizer that validates the draft, closes the GeoJSON ring once, updates the overlay, propagates geometry to LiveDashboard, clears transient state, and restores MapLibre interaction. Add a real-component LiveDashboard regression with only API/MapLibre environment boundaries mocked so the MapCanvas → LiveDashboard → AreaScanPanel → backend-client state flow is exercised.

**Tech Stack:** React 18, TypeScript 5.6, MapLibre GL JS 4.7, Vitest 2.1, Testing Library.

**Spec:** `Current user request dated 2026-10-03`

## Global Constraints

- Stay on `feat/datalastic-area-scan`; do not switch or create branches.
- Do not commit or push.
- Do not change backend provider, authentication, limits, identity, freshness, EEZ/detection, deployment, or basemap behavior.
- Do not make a real Datalastic request; tests mock frontend network boundaries.
- Preserve all unrelated existing worktree changes.
- Escape cancels only; it never commits geometry.
- Rectangle finalization remains unchanged and functional.

## Review Focus

1. A click within the starting vertex tolerance finalizes only after at least three draft vertices.
2. A click near a non-start vertex remains an ordinary draft click.
3. Ring closure contains one closing copy of the first coordinate.
4. Double-click zoom is disabled during polygon drawing and restored after finalization/cancellation.
5. One explicit Scan Area click produces one same-origin `/live/area-scan` request with the completed geometry.

---

### Task 1: Reproduce the state-flow regression

**Files:**
- Modify: `apps/web/src/components/MapCanvas.test.tsx`
- Create: `apps/web/src/pages/LiveDashboard.areaScanFlow.test.tsx`

**Interfaces:**
- Consumes: existing `MapCanvas.onAreaGeometryChange(geometry)` and `LiveDashboard` Area Scan state flow.
- Produces: regression coverage for preview-only, starting-vertex completion, double-click completion, Escape cancellation, Clear, Rectangle, and exactly-one scan submission.

- [x] Add MapCanvas tests proving a near-start click finalizes, a near-non-start click does not, and Escape does not commit.
- [x] Add a real-component dashboard test that renders LiveDashboard with real MapCanvas and AreaScanPanel, completes loopback auth, draws/finalizes a polygon via both supported gestures, enables Scan Area, submits once, and checks the literal completed geometry.
- [x] Run the new/focused tests and confirm the starting-vertex cases fail for the missing finalization behavior while existing completion paths remain green.

### Task 2: Centralize polygon finalization

**Files:**
- Modify: `apps/web/src/components/MapCanvas.tsx`

**Interfaces:**
- Produces: one local polygon finalizer shared by starting-vertex click and double-click; a screen-space first-vertex hit check using MapLibre projection; a structurally valid once-closed GeoJSON Polygon.
- Consumes: `onAreaGeometryChangeRef`, `polygonDraftRef`, `areaDrawModeRef`, and MapLibre interaction handlers.

- [x] Add a pixel-distance helper with a fixed, sensible first-vertex tolerance.
- [x] Implement one shared finalizer that rejects fewer than three points, creates a once-closed ring, clears draft state, exits local drawing mode, restores double-click zoom, updates the overlay, and invokes the existing parent callback.
- [x] Route both polygon double-click and first-vertex click through that finalizer; ordinary clicks continue extending/previewing the draft.
- [x] Run focused MapCanvas and dashboard flow tests and require them to pass.

### Task 3: Verification

**Files:**
- Verify only; no additional scope unless a failing required check traces directly to this change.

**Interfaces:**
- Consumes: completed Task 1/2 implementation.
- Produces: evidence for all verification commands and final report items.

- [x] Run focused MapCanvas, AreaScanPanel, LiveDashboard, and new component-flow tests.
- [x] Run the complete frontend Vitest suite.
- [x] Run `tsc --noEmit` and the Vite production build.
- [x] Run `git diff --check` and inspect `git status --short`.
- [x] Review the final diff for scope, direct-provider calls, interaction restoration, and preservation of unrelated changes.

# Phase 9 Resilience Logistics verification report

Date: 2026-10-02 (Asia/Taipei)

## Scope

Phase 9 adds the SeaWatch **RESPOND** layer: given an explicitly selected
civilian port-disruption scenario, it computes affected demand, feasible
alternative ports/routes, a priority-aware capacity-constrained allocation,
explainable per-port trade-offs, and a bilingual Resilience Decision Brief — as
**decision support for human review only**. It is not an instruction, a
prediction, an autonomous command, or a classification of a real event.

Phase 9 is additive and isolated. It adds **no** runtime or dev dependency,
confines code to `apps/api/seawatch/logistics/`, `apps/web/src/features/logistics/`,
`tests/`, and `docs/`, plus three sanctioned additive shared-file touchpoints:
the API app factory (`/logistics` router registration), the web app shell
(a `RESILIENCE LOGISTICS` navigation entry), and additive i18n keys.

## Delivered behavior

- **Deterministic engine.** `POST /logistics/simulate` is pure: the same request
  and dataset produce a byte-identical `DecisionBrief`. No randomness, no
  database, no LLM, no external/provider call, and no live-AIS dependency. The
  only I/O is reading the curated dataset file once at import.
- **Scoring with exposed decomposition.** Each candidate exposes
  `time/cost/risk/capacity` component scores plus the normalization basis and
  weights (`time 0.35 / cost 0.25 / risk 0.20 / capacity 0.20`, normalized to
  sum 1, overridable per request). Priority is expressed by **allocation
  ordering**, not a hidden weight. `total_score` is a planning preference
  ordering for the scenario only — not a probability, threat level, or legality
  judgement.
- **Priority-ordered, capacity-aware, split allocation.** Higher-priority demand
  is allocated first; port capacity is decremented as demand consumes it; a
  single demand may be split across ports and each split is shown as its own
  row; residual is reported explicitly as unmet demand.
- **Decision Brief.** Deterministic, template-assembled bilingual summaries,
  structured alternatives and trade-offs, assumptions, a provenance note, and a
  provenance summary. Every generated text field passes a shared language guard.
- **Frontend results UI.** Allocation table (ETA / distance / scenario cost /
  capacity / risk, with split rows), Decision Brief, trade-offs, unmet-demand
  display, and an always-visible TruthBadge derived from `provenance_summary`
  and `provenance_note`.
- **Read-only Phase 8 context.** An optional operating-context banner reflects
  the Phase 8 operating mode (`CLOUD_LIVE` / `EDGE_LIVE` / `EDGE_REPLAY` /
  `NO_LIVE_SOURCE`) read from the stable `/resilience/status` contract. It is
  display-only, degrades silently when the endpoint is absent, and never
  auto-triggers a scenario.

## Architecture

```text
Browser (RESILIENCE LOGISTICS view)
  │  shared getBaseUrl() API client (single API-base policy)
  ▼
FastAPI  /logistics router  (additive; isolated from /live, /edge, /resilience)
  ▼
logistics service.simulate()  — pure
  ├─ dataset.load()      curated civilian scenarios.json (ports/demand/supply/routes)
  ├─ scoring             min–max normalization + weighted component decomposition
  ├─ optimizer           GreedyPriorityOptimizer (priority, capacity, split, tie-break)
  └─ brief               deterministic Decision Brief + provenance + language guard
```

Backend package `apps/api/seawatch/logistics/`: `models.py` (frozen domain
dataclasses + `SourceType`/`Commodity` enums), `provenance.py`, `dataset.py`
(+ `data/scenarios.json`), `scoring.py`, `optimizer.py`, `brief.py`,
`service.py`, `schemas.py` (Pydantic schemas inside the package), and the
`api/logistics.py` router.

Frontend feature `apps/web/src/features/logistics/`: `LogisticsView.tsx`
(workflow + optional context banner), `LogisticsPanel.tsx` + `TruthBadge.tsx`
(results UI), `logisticsApi.ts` (built on the shared `getBaseUrl` client),
`logisticsTypes.ts`, `logisticsLayers.ts` (pure overlay builders fed into the
reused Phase 8 map seam), `useOperatingMode.ts` (read-only Phase 8 mode),
`forbiddenTerms.ts` (frontend language guard mirroring the backend list).

### Isolation guarantees

- No import of `live/`, `edge/`, or `resilience/` internals; no mutable-store
  coupling; no circular dependency.
- No change to `requirements.txt`, `package.json`, or `package-lock.json`.
- The map reuses the Phase 8 NLSC → PMTiles → emergency machinery; `MapCanvas`
  is unmodified (logistics uses its generic overlay seam).
- The frontend uses the one shared `getBaseUrl` API-base policy for both
  logistics requests and the operating-mode read: public Cloud (explicit
  `VITE_API_BASE_URL`) → Render; Edge production build without an override →
  exact same-origin `http://127.0.0.1:8000`. No deployment host is hardcoded.

## Truth / provenance boundaries

- A field is `official` **only** when its record carries adequate official-source
  metadata; public civilian port names/coordinates are not auto-upgraded.
- Distances are `derived` and name their method (great-circle, WGS84).
- Capacity, cost, risk, and demand quantities are `scenario`/`synthetic` planning
  values and are **never** presented as real operational data.
- Provenance survives every transformation into the Decision Brief; the brief
  always carries a `provenance_note` and a `provenance_summary` whose counts
  equal the dataset's contributing fields. No transformation upgrades a
  `scenario`/`synthetic` figure, and no official citation is fabricated.
- Routes without authoritative geometry are labeled
  `SCHEMATIC CONNECTOR / 示意連線`, never as measured road or shipping routes.
- Generated output uses decision-support language only; prohibited
  autonomous-command wording never appears (shared `FORBIDDEN_TERMS` guard on
  the backend and mirrored on the frontend).

### Kaohsiung demo truth summary

The locked Kaohsiung Port Disruption result (default weights) routes 120 units
to alternative civilian ports with 0 unmet: medical → Taichung (30); food split
Taichung (30) + Keelung (20); fuel → Keelung (40). Provenance summary:
`official 3`, `derived 2`, `scenario 7`, `synthetic 0`. The full request/response
and reading guide are in `docs/phase9-resilience-logistics-runbook.md`.

## Final automated verification observed

All commands were run from the implementation worktree on 2026-10-02.

- **Backend** (`python -m pytest -q -p no:cacheprovider`): **348 passed**, 1
  warning (the pre-existing Starlette TestClient `BlockingPortal` deprecation).
  Includes the Phase 9 unit suites and the integration tests
  `tests/integration/test_logistics_api.py` and
  `tests/integration/test_logistics_kaohsiung_demo.py`, and confirms the
  existing `/live/*`, `/health`, and `/resilience/status` routes are
  unregressed.
- **Frontend** (`npm test`): **180 passed across 24 files**, including
  `features/logistics/*` and `features/logistics/demo.test.tsx`. Pre-existing
  React `act(...)` warnings remain and are non-failing.
- **Build** (`npm run build` = `tsc --noEmit && vite build`): **passed**, 77
  modules transformed, with the pre-existing large-chunk advisory only.

### Deterministic demo lock

`tests/integration/test_logistics_kaohsiung_demo.py` (15 tests) locks the exact
golden allocations, split, alternatives metrics, provenance counts, medical-first
ordering, byte-identical output across repeated runs and a fresh app instance,
language safety, no outbound socket during simulation, and identical results
regardless of the Phase 8 live/resilience endpoints. `features/logistics/demo.test.tsx`
(6 tests) verifies the rendered demo allocations, deterministic identical
rendered output, the always-visible TruthBadge with exact counts, absence of
prohibited wording, read-only Phase 8 integration (no banner when absent, no
auto-trigger), and correct Cloud/Edge/Replay/No-source mode labels.

## Hardware validation status — PENDING (not complete)

The RESPOND simulation requires no radio hardware and is fully exercised by the
automated suite. The Phase 8 live-RF Edge path still requires a real-hardware
field exercise and is **not yet validated**. SeaWatch makes **no claim** that
live RTL-SDR / AIS-catcher Edge reception has been validated. The pending
acceptance items (receiver recognition, decodable live NMEA on
`127.0.0.1:10110`, measured local RF range, a controlled disconnect/recovery
exercise, laptop/UPS runtime, and a licensed Taiwan PMTiles archive) are listed
in `docs/phase9-resilience-logistics-runbook.md` and
`docs/phase8-edge-resilience-report.md`.

## Phase 9 commit history

```text
feat(logistics): add domain contracts and provenance model
feat(logistics): add curated civilian scenario dataset
feat(logistics): add deterministic scoring with exposed decomposition
feat(logistics): add priority-ordered capacity-aware allocation
feat(logistics): add deterministic decision brief with provenance and language gates
feat(logistics): add pure read-and-simulate logistics API
feat(logistics): add resilience logistics view and navigation
feat(logistics): add civilian logistics map overlay on the shared map seam
feat(logistics): add results table, decision brief, and truth badge
feat(logistics): integrate resilience operating context
test(logistics): verify resilience demo scenario
docs(logistics): document resilience demo workflow
```

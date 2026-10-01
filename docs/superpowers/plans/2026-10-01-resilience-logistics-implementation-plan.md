# SeaWatch Phase 9 Resilience Logistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This document is a plan only. Do not implement in this worktree.** Implementation starts later, from the final Phase 8 HEAD, per the Merge Strategy section.

**Goal:** Add the SeaWatch **RESPOND** layer: given an explicitly selected civilian port-disruption scenario, compute affected demand, feasible alternative ports and routes, capacity/ETA/distance/cost/risk impact, a priority-aware allocation, explainable trade-offs, and a Resilience Decision Brief — as decision support for human review only.

**Architecture:** A small, deterministic, dependency-free, explainable module isolated from Phase 8. New backend package `apps/api/seawatch/logistics/` behind a new `/logistics` router; new frontend feature `apps/web/src/features/logistics/` reusing the existing MapLibre `MapCanvas` and i18n provider. Weighted deterministic scoring + priority-ordered, capacity-aware greedy allocation behind an optimizer interface seam.

**Tech Stack:** Python 3.12, FastAPI/Starlette (existing), stdlib only for logistics compute (no solver, no new backend dependency), pytest (existing). React 18, TypeScript, Vite, MapLibre GL JS, Vitest (all existing). **No new runtime or dev dependency is added by this phase.**

**Spec:** `docs/superpowers/specs/2026-10-01-resilience-logistics-design.md` (approved at `9f95d489d243608b5a36c2cb94cd30dad12e265d`).

## Global Constraints

- Design base is `feat/resilience-logistics-design` at `9f95d48`, an **older SeaWatch HEAD used for design/planning only**. Actual implementation starts from the final Phase 8 HEAD (see Merge Strategy). The plan therefore references Phase 8 only through **stable contracts**, never line numbers or internal implementation details.
- Phase 9 is **additive and isolated**. Implementation may create files only under `apps/api/seawatch/logistics/`, `apps/web/src/features/logistics/`, `tests/`, and `docs/`, plus exactly two one-line registrations: `include_router(logistics.router)` in the API app factory and a view-toggle entry in the web app shell.
- Do **not** modify `live/`, `edge/`, `resilience/`, or any Phase 8 module. Do not import Phase 8 internals. Do not create circular dependencies.
- Do **not** add any dependency to `requirements.txt`, `package.json`, or `package-lock.json`. Logistics compute is stdlib-only; the frontend reuses existing packages.
- `POST /logistics/simulate` is **pure**: same request + same dataset ⇒ byte-identical result. No database, no persistence, no LLM, no external API, no network call, no live-AIS dependency.
- All non-official figures (capacity, cost, risk, inventory, demand quantities) are labeled `scenario` or `synthetic` and are never presented as real operational data. Provenance survives every transformation into the Decision Brief.
- Output uses decision-support language only. Prohibited wording (command, dispatch immediately, military recommendation, confirmed disruption, real capacity, verified inventory, etc.) must never appear in generated output.
- Phase 8 operating mode is consumed, if at all, only as a stable read-only string from `/live/health` (or `/resilience/status` if present), tolerant of absence. Logistics works fully even if that endpoint is missing. No scenario is auto-triggered from AIS/anomaly in V1.
- Only public civilian ports and generic logistics context appear on the map. No military/sensitive locations.
- Follow red/green/refactor for every behavior: write the failing test, observe the expected failure, implement minimally, rerun focused + relevant regression suites.
- Stop immediately at a failed hard gate. Do not start the next slice until the gate is green.
- Backend full-suite command (adjust `--basetemp` to the implementation worktree root): `python -m pytest -q -p no:cacheprovider`.
- Frontend commands: `cd apps/web`, `npm test`, `npm run build` (use `npm.cmd` under restrictive Windows PowerShell execution policy).

## Dependency Review

| Package | Decision | Rationale |
|---|---|---|
| (none) | **No dependency is added by Phase 9.** | Weighted deterministic scoring and greedy allocation require only Python stdlib arithmetic and `dataclasses`/`enum`. The frontend reuses React, MapLibre, i18n, and Vitest already present. Avoiding dependency changes is a deliberate design decision and also prevents file-level conflicts with the Phase 8 worktree, which owns `requirements.txt`/`package.json`. If a future, larger, contested-capacity dataset ever justifies LP or min-cost flow, that is a separate phase with its own dependency review. |

## Target File Structure (created during later implementation)

| Path | Responsibility |
|---|---|
| `apps/api/seawatch/logistics/__init__.py` | Package marker and public exports. |
| `apps/api/seawatch/logistics/models.py` | Frozen domain dataclasses + `SourceType` enum + `Commodity` enum. |
| `apps/api/seawatch/logistics/provenance.py` | `SourceType` rules and `provenance_summary` aggregation. |
| `apps/api/seawatch/logistics/dataset.py` | Load/validate the curated scenario dataset JSON into typed records. |
| `apps/api/seawatch/logistics/data/scenarios.json` | Curated civilian scenario dataset (ports/demand/supply/routes/scenarios). |
| `apps/api/seawatch/logistics/scoring.py` | Normalization + per-term score decomposition. |
| `apps/api/seawatch/logistics/optimizer.py` | `Optimizer` interface + greedy priority-capacity allocator. |
| `apps/api/seawatch/logistics/brief.py` | Deterministic Decision Brief generator + language guard. |
| `apps/api/seawatch/logistics/service.py` | Compose dataset + scoring + optimizer + brief into pure simulate. |
| `apps/api/seawatch/schemas/logistics.py` | Pydantic response/request schemas for the API. |
| `apps/api/seawatch/api/logistics.py` | `/logistics/scenarios`, `/logistics/scenarios/{id}`, `/logistics/simulate`. |
| `apps/web/src/features/logistics/LogisticsView.tsx` | Scenario → context → run → result workflow. |
| `apps/web/src/features/logistics/LogisticsPanel.tsx` | Scenario selector, demand list, alternatives, Run button, results. |
| `apps/web/src/features/logistics/logisticsApi.ts` | Typed client for the three endpoints. |
| `apps/web/src/features/logistics/logisticsTypes.ts` | TS mirrors of the API schemas. |
| `apps/web/src/features/logistics/logisticsLayers.ts` | MapLibre overlay sources/layers for ports/demand/routes. |
| `apps/web/src/features/logistics/TruthBadge.tsx` | Visible provenance/truth note component. |
| `tests/unit/test_logistics_*.py` | Backend unit tests per slice. |
| `tests/integration/test_logistics_api.py` | API behavior + existing-route non-regression. |
| `apps/web/src/features/logistics/*.test.tsx` | Frontend component tests. |

Files **modified** during later implementation are limited to:

| Path | One-line change |
|---|---|
| `apps/api/seawatch/main.py` (app factory) | `app.include_router(logistics.router)`. |
| `apps/web/src/App.tsx` (or shell) | Add a `RESILIENCE LOGISTICS` view toggle alongside the live map. |
| `apps/web/src/i18n/dictionaries.ts` | Add new keys (no existing keys changed). |

## Review Focus

1. **Provenance integrity:** no transformation upgrades a `scenario`/`synthetic` figure to `official`/`derived`; `provenance_summary` counts match the dataset; the Decision Brief always carries the provenance note (Slices A, E, and the provenance hard gate).
2. **Language discipline:** generated brief text never contains prohibited wording; alternatives/trade-offs are rendered from structured fields, not free prose that could drift (Slice E and the language hard gate).
3. **Determinism:** identical request ⇒ identical result, including stable tie-breaking and weight normalization (Slices C/D/F).
4. **Isolation from Phase 8:** no import of `live/*`; optional mode read tolerates a missing endpoint; only the two sanctioned one-line registrations touch shared files (Slice J and the frontend gate).

---

## Scoring Contract (authoritative for Slices C–F)

For each demand `d` (processed in priority order) and each candidate route `r` through a non-disrupted port `p`, the engine exposes a per-candidate decomposition and never only a hidden total:

```text
time_score     = w_time     * norm(eta_hours(r))
cost_score     = w_cost     * norm(per_unit_cost(r) + base_handling_cost(p))
risk_score     = w_risk     * route_risk(r)                      # route_risk already in [0,1]
capacity_score = w_capacity * capacity_penalty(p, d)             # [0,1], hard-excluded at zero remaining
priority_effect = (ordering only; not summed into total_score)
total_score    = time_score + cost_score + risk_score + capacity_score
```

- **Normalization strategy:** `norm(x)` is min–max over the current candidate set for that demand (if all values are equal, `norm` returns `0.0` for every candidate so the term is neutral). This keeps terms comparable on `[0,1]`; raw units never dominate. The normalization basis (min/max used) is returned per demand for transparency.
- **Weights:** documented constants (`w_time=0.35, w_cost=0.25, w_risk=0.20, w_capacity=0.20`), overridable via request `weights`. Weights are normalized to sum to 1 before use; the normalization is recorded in `assumptions`. Weights are always returned with the result; they are never hidden.
- **Priority** is expressed by **allocation ordering**, not a weight term — explicit and auditable. `priority_effect` is reported as the order index, not folded into `total_score`.
- **Deterministic tie-breaking:** when two candidates have equal `total_score`, break ties by (1) lower `eta_hours`, then (2) lower combined cost, then (3) lower `route_risk`, then (4) lexicographic `route_id`. This is total and reproducible.
- **Non-claims (tested):** `total_score` is a planning preference ordering for this scenario only. It is not a probability, threat level, legality judgement, or claim of real operational superiority. Response text and docs must state this.

## Capacity Contract (authoritative for Slice D)

- Scenario capacity is **planning/demo capacity only** unless a field is explicitly `official`. Synthetic capacity is never presented as real port capacity (tested).
- The allocator must: prevent over-allocation (never exceed a port's possibly-overridden `capacity_units`), decrement remaining capacity as demands consume it, allocate higher-priority demand first, support **split allocation** (see decision below), report `unmet_units` explicitly, and be fully deterministic.
- **Split-allocation design decision (explicit):** **V1 ALLOWS splitting a single demand across multiple ports.** Rationale: with only two alternatives and scarce capacity, forbidding splits would frequently force large `unmet_demand` and make the medical-priority story less realistic. The split is deterministic: fill the best-scoring feasible port up to its remaining capacity, then the next best, until the demand is satisfied or no feasible capacity remains. Any residual is reported as `unmet_units`. Splits are visible in the allocation table (one row per port assignment) so the human sees exactly how a demand was divided.

## Truth / Provenance Hard Gate (authoritative)

Tests must prove, as a blocking gate after Slice A/B and re-checked after Slice E:
- synthetic capacity remains `synthetic` end-to-end;
- scenario cost remains `scenario`;
- derived distance remains `derived` with the method named;
- official port identity (name/public coordinates) remains `official` where applicable;
- the `DecisionBrief` cannot erase or upgrade provenance; it always carries `provenance_note` and a `provenance_summary` whose counts equal the dataset's contributing fields.
- The frontend always displays a visible truth note (TruthBadge) with any result.

## Language Hard Gate (authoritative)

Tests must prove generated output may contain allowed phrasing (`recommended for this scenario`, `planning estimate`, `alternative`, `trade-off`, `human review required`) and must never contain prohibited phrasing (`command`, `dispatch immediately`, `military recommendation`, `confirmed disruption`, `real capacity`, `verified inventory`, and the full forbidden list from the spec). A single shared `FORBIDDEN_TERMS` constant backs both the generator guard and the test.

---

## Slice A — Domain contracts + provenance

**Dependencies:** none.

1. **Files to create:** `logistics/__init__.py`, `logistics/models.py`, `logistics/provenance.py`, `tests/unit/test_logistics_models.py`, `tests/unit/test_logistics_provenance.py`.
2. **Files to modify:** none.
3. **Contracts/interfaces:** `SourceType` enum (`official|derived|scenario|synthetic`); `Commodity` enum (`medical|food|fuel`); frozen dataclasses `Port, Demand, Supply, Route, DisruptionScenario, Allocation, DecisionBrief` per spec §5; `provenance.summarize(records) -> dict[str,int]`; `provenance.carries_note(brief) -> bool`.
4. **RED tests:** each dataclass round-trips its fields; `SourceType` rejects unknown values; a brief without a `provenance_note` fails `carries_note`; `summarize` counts each class correctly; provenance of a field cannot be upgraded by any model method (there are no setters — frozen).
5. **Minimal GREEN implementation:** frozen dataclasses + enums + pure summarize/carries_note functions. No logic beyond construction/validation.
6. **Verification:** `python -m pytest -q tests/unit/test_logistics_models.py tests/unit/test_logistics_provenance.py`.
7. **Failure/rollback risk:** low — pure data types; rollback is deleting new files.
8. **Commit message:** `feat(logistics): add domain contracts and provenance model`.
9. **Depends on:** nothing.

## Slice B — Curated civilian scenario dataset

**Dependencies:** Slice A.

1. **Files to create:** `logistics/data/scenarios.json`, `logistics/dataset.py`, `tests/unit/test_logistics_dataset.py`.
2. **Files to modify:** none.
3. **Contracts/interfaces:** `dataset.load(path=DEFAULT) -> Dataset` returning typed records; `Dataset.scenario(id)`, `.demands_for(scenario)`, `.candidate_routes(scenario)`. Dataset covers Kaohsiung/Taichung/Keelung ports and medical/food/fuel demand; Kaohsiung-disruption scenario included. Port names/coordinates reuse the public civilian list and are `official`; distances `derived`; capacities/costs/risks/demand `scenario`/`synthetic`.
4. **RED tests:** every record validates and carries a valid `source_type`; all coordinates fall within the Taiwan bbox; capacity/cost/risk fields are `scenario`/`synthetic` (never `official`); the Kaohsiung scenario marks Kaohsiung disrupted; a malformed dataset file raises a clear, catchable error (so the router can degrade to an empty list).
5. **Minimal GREEN implementation:** JSON file + a loader that maps JSON to Slice A dataclasses with validation.
6. **Verification:** `python -m pytest -q tests/unit/test_logistics_dataset.py`.
7. **Failure/rollback risk:** low — static data + loader; rollback deletes files.
8. **Commit message:** `feat(logistics): add curated civilian scenario dataset`.
9. **Depends on:** A.

### HARD GATE 1 — Domain / Provenance

Blocks Slice C until green: Slice A + B tests pass; provenance hard-gate assertions (synthetic→synthetic, scenario→scenario, derived→derived, official→official, no upgrade) pass. **A failure here stops all later slices.**

## Slice C — Deterministic scoring engine

**Dependencies:** A, B.

1. **Files to create:** `logistics/scoring.py`, `tests/unit/test_logistics_scoring.py`.
2. **Files to modify:** none.
3. **Contracts/interfaces:** `score_candidate(demand, route, port, weights, basis) -> ScoreBreakdown` exposing `time_score, cost_score, risk_score, capacity_score, priority_effect, total_score` and the normalization basis; `normalize(values) -> list[float]` (min–max, equal-values ⇒ zeros); `normalize_weights(weights) -> Weights`.
4. **RED tests:** golden score decomposition for a fixed scenario (exact expected numbers); `normalize` edge cases (single value, all equal, min==max); weight normalization sums to 1; invalid weights (negative/non-numeric) rejected; `total_score` equals the sum of the four component terms and excludes `priority_effect`; a test asserting `total_score` is documented as not-a-probability (docstring/metadata check).
5. **Minimal GREEN implementation:** pure arithmetic functions; no allocation yet.
6. **Verification:** `python -m pytest -q tests/unit/test_logistics_scoring.py`.
7. **Failure/rollback risk:** medium — golden numbers must be computed by hand and locked; risk is brittle fixtures. Mitigate by deriving expected values in the test from the formula constants, not magic literals.
8. **Commit message:** `feat(logistics): add deterministic scoring with exposed decomposition`.
9. **Depends on:** A, B.

## Slice D — Capacity-aware allocation

**Dependencies:** A, B, C.

1. **Files to create:** `logistics/optimizer.py`, `tests/unit/test_logistics_optimizer.py`.
2. **Files to modify:** none.
3. **Contracts/interfaces:** `class Optimizer(Protocol): def allocate(self, scenario, dataset, weights) -> list[Allocation]`; `GreedyPriorityOptimizer` implementing priority-ordered, capacity-aware, split-allowed greedy allocation with the Scoring Contract's deterministic tie-breaking. This is the **optimizer interface seam** for future LP/flow replacement.
4. **RED tests:** medical allocated before food before fuel; capacity decremented across demands; **split allocation** across Taichung+Keelung when one port lacks capacity; `unmet_units` reported when total capacity/supply is short; disrupted port excluded; missing route excluded; supply cap enforced; all-ports-disrupted ⇒ all demand unmet; deterministic tie-break produces a stable, documented winner; identical inputs ⇒ identical allocations.
5. **Minimal GREEN implementation:** greedy loop over priority-sorted demands; per-port remaining-capacity ledger; split fill; residual → unmet.
6. **Verification:** `python -m pytest -q tests/unit/test_logistics_optimizer.py`.
7. **Failure/rollback risk:** medium-high — the core logic; subtle capacity/split/tie bugs. Mitigate with the exhaustive case table above and a determinism test.
8. **Commit message:** `feat(logistics): add priority-ordered capacity-aware allocation`.
9. **Depends on:** A, B, C.

## Slice E — Decision Brief generator

**Dependencies:** A–D.

1. **Files to create:** `logistics/brief.py`, `tests/unit/test_logistics_brief.py`.
2. **Files to modify:** none.
3. **Contracts/interfaces:** `build_brief(scenario, allocations, dataset, weights) -> DecisionBrief` producing structured fields: `recommended_allocations`, per-port `alternatives` (eta/distance/cost/capacity/risk), `trade_offs`, `unmet_demand`, `provenance_note`, `assumptions`, `provenance_summary`, bilingual `summary_zh/summary_en`; shared `FORBIDDEN_TERMS` constant + `assert_language_safe(text)` guard.
4. **RED tests:** brief always carries `provenance_note`; `provenance_summary` counts equal the dataset's contributing fields (provenance cannot be erased); allowed phrasing permitted; **prohibited wording never present** in any generated field (language hard gate); alternatives are populated from structured values (not parsed from prose); split allocations appear as explicit rows; determinism (same inputs ⇒ identical brief).
5. **Minimal GREEN implementation:** deterministic string templates (no LLM) + structured assembly; run `assert_language_safe` on every generated text field.
6. **Verification:** `python -m pytest -q tests/unit/test_logistics_brief.py`.
7. **Failure/rollback risk:** medium — language gate and provenance assembly are the honesty-critical surface. Mitigate by generating prose only from a fixed template vocabulary.
8. **Commit message:** `feat(logistics): add deterministic decision brief with provenance and language gates`.
9. **Depends on:** A, B, C, D.

### HARD GATE 2 — Scoring / Allocation / Brief

Blocks Slice F until green: Slices C–E tests pass; determinism, split-allocation, deterministic tie-breaking, provenance-preservation, and language-safety assertions all pass. **A failure here stops all later slices.**

## Slice F — Backend service / API

**Dependencies:** A–E.

1. **Files to create:** `logistics/service.py`, `apps/api/seawatch/schemas/logistics.py`, `apps/api/seawatch/api/logistics.py`, `tests/integration/test_logistics_api.py`.
2. **Files to modify:** `apps/api/seawatch/main.py` (app factory) — add `app.include_router(logistics.router)` (one line).
3. **Contracts/interfaces:** `service.simulate(scenario_id, weights=None) -> DecisionBrief` (pure); router `GET /logistics/scenarios`, `GET /logistics/scenarios/{id}`, `POST /logistics/simulate`; Pydantic request/response schemas; dataset load failure ⇒ router starts with empty scenario list + one logged error.
4. **RED tests:** `/logistics/scenarios` lists the Kaohsiung scenario; `/logistics/scenarios/{id}` returns context incl. `provenance_summary`; unknown id ⇒ `404`; `/logistics/simulate` happy path returns a full structured brief; infeasible scenario ⇒ `200` with `unmet_demand` (not an error); malformed weights ⇒ `422`; **determinism** (two identical POSTs ⇒ identical body); **no network/DB/LLM** (asserted by construction and by a no-socket test); existing `/live/*`, `/health` remain registered and unchanged (non-regression).
5. **Minimal GREEN implementation:** thin router delegating to `service.simulate`; schemas mirror the dataclasses; GET endpoints read the loaded dataset.
6. **Verification:** `python -m pytest -q tests/integration/test_logistics_api.py` + full backend suite for non-regression.
7. **Failure/rollback risk:** medium — the one `main.py` edit touches a shared file; keep it to a single additive line and verify no existing test regresses. Rollback removes the line and new files.
8. **Commit message:** `feat(logistics): add pure read-and-simulate logistics API`.
9. **Depends on:** A–E.

### HARD GATE 3 — Backend API

Blocks Slice G until green: Slice F tests pass; full backend suite passes (no `/live/*` regression); determinism and purity assertions pass. **A failure here stops frontend work.**

## Slice G — Frontend navigation / view

**Dependencies:** F (API contract stable).

1. **Files to create:** `features/logistics/LogisticsView.tsx`, `features/logistics/logisticsApi.ts`, `features/logistics/logisticsTypes.ts`, `features/logistics/LogisticsView.test.tsx`.
2. **Files to modify:** `apps/web/src/App.tsx` (view toggle `LIVE MAP ⇄ RESILIENCE LOGISTICS`); `apps/web/src/i18n/dictionaries.ts` (new keys only).
3. **Contracts/interfaces:** typed client for the three endpoints; `LogisticsView` orchestrates scenario select → load context → Run Simulation → render result; existing `LiveDashboard` untouched.
4. **RED tests:** toggle switches views without altering LiveDashboard; scenario dropdown loads scenarios; selecting a scenario loads context; Run Simulation calls `POST /logistics/simulate` and transitions to a result state; bilingual copy switches correctly.
5. **Minimal GREEN implementation:** view + client + types; result rendering stubbed to Slice I.
6. **Verification:** `cd apps/web && npm test -- logistics`.
7. **Failure/rollback risk:** medium — `App.tsx` edit is shared; keep it a minimal additive toggle. Rollback removes the toggle and new folder.
8. **Commit message:** `feat(logistics): add resilience logistics view and navigation`.
9. **Depends on:** F.

## Slice H — Logistics MapLibre layer

**Dependencies:** G.

1. **Files to create:** `features/logistics/logisticsLayers.ts`, `features/logistics/logisticsLayers.test.ts`.
2. **Files to modify:** none beyond Slice G view wiring.
3. **Contracts/interfaces:** functions that build GeoJSON sources/layers for disrupted port, alternative ports, civilian demand nodes, and selected-solution routes, added through the existing MapCanvas/layer-control pattern (reuse existing infra where practical).
4. **RED tests:** disrupted port is visibly marked distinct; alternative ports rendered; demand nodes rendered; selected routes rendered colored by commodity; only civilian ports present (no sensitive locations); routes without geometry render as labeled connectors, not fabricated paths.
5. **Minimal GREEN implementation:** pure layer/source builders consumed by the view; no new map engine.
6. **Verification:** `cd apps/web && npm test -- logisticsLayers`.
7. **Failure/rollback risk:** low-medium — isolated overlay; rollback deletes files.
8. **Commit message:** `feat(logistics): add civilian logistics map overlay`.
9. **Depends on:** G.

## Slice I — Results UI

**Dependencies:** G, H.

1. **Files to create:** `features/logistics/LogisticsPanel.tsx`, `features/logistics/TruthBadge.tsx`, `features/logistics/LogisticsPanel.test.tsx`.
2. **Files to modify:** `LogisticsView.tsx` (wire the real result renderer).
3. **Contracts/interfaces:** allocation table (ETA / distance / scenario cost / capacity / risk, with split rows), Decision Brief text, trade-offs list, unmet-demand display, always-visible TruthBadge derived from `provenance_summary` + `provenance_note`.
4. **RED tests:** allocation table renders all metric columns and split rows; brief + trade-offs render from structured fields; unmet demand shown when present; **TruthBadge always visible with any result**; prohibited wording absent in rendered output (frontend-side guard mirrors backend list).
5. **Minimal GREEN implementation:** presentational components reading the typed response.
6. **Verification:** `cd apps/web && npm test -- LogisticsPanel && npm run build`.
7. **Failure/rollback risk:** medium — truth badge visibility is honesty-critical; test it unconditionally.
8. **Commit message:** `feat(logistics): add results table, decision brief, and truth badge`.
9. **Depends on:** G, H.

### HARD GATE 4 — Frontend Integration

Blocks Slice J until green: Slices G–I tests pass; `npm run build` succeeds; TruthBadge-always-visible and no-prohibited-wording assertions pass; LiveDashboard non-regression verified. **A failure here stops integration/demo work.**

## Slice J — Phase 8 integration seam

**Dependencies:** I; and (at implementation time) the final Phase 8 `/live/health`/`/resilience/status` contract.

1. **Files to create:** `features/logistics/useOperatingMode.ts`, `features/logistics/useOperatingMode.test.ts`.
2. **Files to modify:** `LogisticsView.tsx` (optional context banner).
3. **Contracts/interfaces:** read-only consumption of a stable operating-mode string from `/live/health` (or `/resilience/status` if present); treat it as opaque; render an optional banner (e.g. "Running in Edge mode — logistics uses the local scenario dataset"). **No import of Phase 8 internals; no mutable store coupling; no circular dependency.**
4. **RED tests:** when the mode endpoint is **absent/errors**, logistics still works and shows no banner (tolerant of absence); when a known mode string is present, the banner renders; no scenario is auto-triggered from AIS/anomaly.
5. **Minimal GREEN implementation:** a small hook with a try/catch fetch that degrades silently.
6. **Verification:** `cd apps/web && npm test -- useOperatingMode`.
7. **Failure/rollback risk:** low — purely additive, absence-tolerant; rollback deletes the hook and banner.
8. **Commit message:** `feat(logistics): add optional read-only phase 8 mode context`.
9. **Depends on:** I.

## Slice K — Demo scenario + end-to-end tests

**Dependencies:** A–J.

1. **Files to create:** `tests/integration/test_logistics_kaohsiung_demo.py`, `features/logistics/demo.test.tsx`.
2. **Files to modify:** none (dataset already contains the scenario).
3. **Contracts/interfaces:** a locked end-to-end expectation for the Kaohsiung disruption (medical/food/fuel; Taichung/Keelung) with **deterministic expected outputs** (allocation, alternatives metrics, trade-offs, provenance summary).
4. **RED tests:** full simulate for the Kaohsiung scenario yields the documented allocation and metrics exactly; medical goes first; any split is as expected; provenance summary counts are exact; language-safe; frontend renders the demo result including TruthBadge.
5. **Minimal GREEN implementation:** none beyond prior slices; this slice locks the golden end-to-end result.
6. **Verification:** `python -m pytest -q tests/integration/test_logistics_kaohsiung_demo.py` + `cd apps/web && npm test -- demo`.
7. **Failure/rollback risk:** medium — golden end-to-end values are brittle; compute them from the engine, review, then lock.
8. **Commit message:** `test(logistics): lock kaohsiung disruption demo expectations`.
9. **Depends on:** A–J.

## Slice L — Final documentation / demo verification

**Dependencies:** A–K.

1. **Files to create:** `docs/phase9-resilience-logistics-report.md`, `docs/phase9-resilience-logistics-runbook.md`.
2. **Files to modify:** `README.md` (add a Phase 9 status/links line — additive).
3. **Contracts/interfaces:** report records what was tested and measured; runbook gives the SENSE → SURVIVE → RESPOND demo steps and the exact simulate request/response for the Kaohsiung demo; both restate decision-support-only and truth-boundary limitations.
4. **RED tests:** none (docs); instead run the full backend + frontend suites and `npm run build` as the documentation's evidence, and verify the runbook's commands produce the documented output.
5. **Minimal GREEN implementation:** write docs from actual, re-run results — no result claimed before the command is run.
6. **Verification:** full backend suite + `cd apps/web && npm test && npm run build`.
7. **Failure/rollback risk:** low — docs; rollback edits text.
8. **Commit message:** `docs(logistics): add phase 9 report and demo runbook`.
9. **Depends on:** A–K.

### HARD GATE 5 — Final Demo

Phase 9 implementation is complete only when: all slice tests pass; full backend + frontend suites pass; `npm run build` succeeds; the Kaohsiung demo yields the documented deterministic result; TruthBadge/provenance note always visible; no prohibited wording anywhere; no new dependency added; `/live/*`, `/health`, and Phase 8 behavior unregressed; logistics works with the Phase 8 mode endpoint absent; and the SENSE → SURVIVE → RESPOND demo runs end to end.

---

## Merge Strategy — future implementation-start procedure

This design worktree is based on an **older SeaWatch HEAD** and is for design/planning only. **Do not implement Phase 9 from this worktree's base.** When Phase 8 is complete:

1. Obtain the **final Phase 8 HEAD** on its integrated branch (e.g. once `feat/edge-resilience` work lands on the mainline).
2. Create a **new implementation branch from that final HEAD** (e.g. `feat/resilience-logistics-impl`). Do not reuse `feat/resilience-logistics-design` as the implementation base.
3. Bring the approved Phase 9 **design** (`...specs/2026-10-01-resilience-logistics-design.md`) and this **plan** into that branch (cherry-pick the two doc commits or copy the files).
4. **Verify conflicts:** confirm the only shared-file touchpoints are the two sanctioned one-line registrations (`include_router` in the API app factory, the web view toggle) and the additive i18n keys; resolve against the *final* Phase 8 structure, not the old base. Reconfirm the Phase 8 operating-mode contract (`/live/health` / `/resilience/status`) as it actually shipped, since this plan references it only as a stable contract.
5. **Only then begin Phase 9 code**, executing Slices A→L in order, honoring each hard gate.

Because Phase 9 adds no dependency and confines itself to new paths plus two one-line edits, no conflict is expected in `apps/api/` or `apps/web/` beyond those two lines.

## Isolation / non-interference guarantees (restated)

- No import of `live/*`, `edge/*`, `resilience/*`; no mutable-store coupling; no circular dependency.
- No change to `requirements.txt`, `package.json`, `package-lock.json`.
- Phase 8 is treated as an external sibling; its operating mode is consumed only through a stable read-only contract and is tolerant of absence.
- No scenario is auto-triggered from AIS/anomaly in V1.
- Do not alter `live/`, `edge/`, `resilience/` during Phase 9 implementation unless separately approved.

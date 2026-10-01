# SeaWatch Phase 9 Resilience Logistics Decision Support Design

**Status:** Proposed for review; design and planning only

**Date:** 2026-10-01

**Base:** `feat/resilience-logistics-design` at `74b1bac`
(`docs: plan edge resilience implementation`)

**Challenge framing:** TDTH 2026 #07 Maritime Track Anomaly & Grey-Zone
Behavior Alerting (SENSE) extended with #10 Emergency Logistics / Supply-Chain
Resilience (RESPOND). This phase designs the **RESPOND** layer as a module of
SeaWatch, not a separate product.

> This document is design and planning only. It defines no application code, no
> dependency change, and no deployment. Implementation is a later, separate
> phase. It must not interfere with the Phase 8 Edge Resilience work proceeding
> in another worktree.

---

## 1. Purpose and boundaries

SeaWatch tells one story: **SENSE → SURVIVE → RESPOND.**

- **SENSE** (#07, built): live Taiwan AIS, trajectory analysis, explainable
  review ranking.
- **SURVIVE** (Phase 8, in progress elsewhere): Cloud/Edge resilience, local RF
  AIS, offline map, localhost operation.
- **RESPOND** (this Phase 9): when a port becomes temporarily unavailable, help
  a human decision-maker understand the logistics impact and compare realistic
  alternatives.

Phase 9 answers more than `PORT DISRUPTED`. For a selected disruption scenario
it answers: which logistics demand is affected, which civilian ports can absorb
it, how routes reconfigure, how ETA and cost change, whether capacity is
sufficient, which critical supplies to prioritize, and what trade-offs the
decision-maker faces. It produces a transparent, explainable **Resilience
Decision Brief**.

### 1.1 What this module is

A **small, deterministic, explainable decision-support module**: a bounded
backend package plus a frontend panel and map overlay. It computes a
recommended allocation of demand to alternative ports and routes, and explains
why, from a curated scenario dataset with explicit provenance labels.

### 1.2 What this module is not

It is **not** an autonomous command system, an automatic tasking engine, an ERP,
a warehouse-management system, enterprise procurement, fleet management, a
nationwide digital twin, or a black-box optimizer. It issues no orders and makes
no automatic judgement. Every output is a recommendation for human review.

### 1.3 Language discipline (inherited from #07)

Consistent with the existing review-ranking vocabulary, the module and its
output must use **decision-support** language:

- allowed: `recommended allocation`, `alternative port`, `estimated ETA
  impact`, `estimated cost change`, `capacity utilization`, `trade-off`,
  `scenario`, `for human review`;
- forbidden: `order`, `command`, `tasking`, `dispatch directive`, any military
  framing, and any phrasing that presents an estimate as an executed action or a
  confirmed real-world operation.

---

## 2. Scope boundaries vs Phase 8

Phase 8 (SURVIVE) is being implemented concurrently in `C:\Projects\seawatch`
on its own branch. This design must not disturb it.

**This phase, this round, is DESIGN ONLY.** It introduces no code and changes no
`apps/api/`, `apps/web/`, `requirements.txt`, `package.json`, or
`package-lock.json`. The sections below describe a *future* implementation so
the integration seam is clear, but implementation is explicitly deferred.

When Phase 9 is later implemented, it must remain **additive and isolated**:

- new backend package `apps/api/seawatch/logistics/` only;
- new frontend feature folder `apps/web/src/features/logistics/` only;
- new router mounted under a new `/logistics` prefix only;
- it reads nothing from the Edge/Cloud stores and writes nothing to them;
- it does not import Phase 8 modules (`live/edge_ais.py`, `live/resilience.py`,
  `live/active_view.py`, etc.);
- it shares only stable, already-public surfaces (the existing MapLibre
  `MapCanvas`, the i18n provider, the layer control pattern, the `/live/health`
  read-only contract).

The two phases meet at a **read-only seam** (Section 15), never at shared
mutable state.

---

## 3. Product scope (MVP)

The MVP is intentionally minimal. It consists of exactly six domain concepts and
one decision computation:

```text
Port  +  Demand  +  Supply  +  Route  +  DisruptionScenario
                        |
                        v
             deterministic scoring + allocation
                        |
                        v
            Allocation  +  DecisionBrief
```

### 3.1 In scope

- A curated scenario dataset (ports, demand nodes, supply nodes, candidate
  routes, disruption scenarios) with explicit provenance labels.
- A deterministic simulation that, given a selected scenario, computes per-route
  metrics (ETA, distance, cost, capacity utilization, risk) and a recommended
  allocation of each demand to one or more alternative ports.
- A generated Decision Brief: a short, ranked, human-readable rationale with
  trade-offs and an explicit uncertainty/provenance disclaimer.
- A frontend Logistics panel and map overlay reusing the existing MapLibre map.

### 3.2 Out of scope (non-goals)

- Real-time coupling to live AIS or Phase 8 (deferred to Section 16).
- Automatic disruption detection / automatic scenario triggering (v1 uses manual
  scenario selection).
- Multi-modal inland logistics optimization, trucking fleets, rail, warehouse
  inventory optimization.
- Stochastic / time-dynamic simulation, queueing models, or congestion
  propagation modeling.
- Any military logistics, weapons transport, military routing, base supply, or
  sensitive deployment content.
- Persisted databases, user accounts, or editing of the scenario dataset through
  the UI (dataset is read-only curated JSON in v1).

---

## 4. Demo scenario

### 4.1 Scenario A — Kaohsiung Port disruption (primary)

Kaohsiung (高雄港), Taiwan's largest commercial port, becomes temporarily
unavailable in the scenario (hazard, incident, congestion, or other
non-attributed cause — the scenario does not assert a real event or a cause). A
set of **critical civilian demand** must be rerouted:

- medical supplies (highest priority);
- food;
- fuel.

Candidate alternative civilian ports:

- **Taichung (臺中港)** — Alternative A;
- **Keelung (基隆港)** — Alternative B.

For each alternative, the module reports ETA increase, distance increase,
estimated cost change, capacity utilization, and a composite risk indicator, and
produces a Decision Brief, e.g.:

> Prioritize critical medical cargo via Taichung (nearest with available
> capacity). Route food to Taichung up to its remaining capacity; defer or split
> lower-priority cargo. Keep Keelung as secondary contingency for overflow.
> Estimates are scenario-based planning figures for human review, not an
> instruction and not a prediction of a real event.

This remains **decision support only** — never automatic command or tasking.

### 4.2 Additional scenario slots (dataset-driven, optional)

The dataset format supports more scenarios (e.g. a Taichung disruption) without
code change, but only Scenario A is required for the MVP demo.

---

## 5. Domain model

All entities are plain, serializable records. Coordinates are WGS84
(EPSG:4326), consistent with the rest of SeaWatch. Every record carries a
`source_type` provenance label (Section 6).

### 5.1 `Port`

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable key, e.g. `kaohsiung`. |
| `name_zh` / `name_en` | string | Bilingual label. |
| `lon` / `lat` | float | WGS84; aligned with existing `COMMERCIAL_PORTS`. |
| `capacity_units` | float | Throughput capacity in abstract **cargo units/day**. |
| `base_handling_cost` | float | Relative per-unit handling cost (unitless index). |
| `source_type` | enum | See Section 6. |

### 5.2 `Demand`

| Field | Type | Notes |
|---|---|---|
| `id` | string | e.g. `medical-south`. |
| `commodity` | enum | `medical` \| `food` \| `fuel`. |
| `priority` | int | 1 = highest. Drives allocation ordering. |
| `quantity_units` | float | Required cargo units. |
| `origin_demand_node` | string | Civilian destination/demand node id. |
| `normally_served_by` | string | Port id normally used (e.g. `kaohsiung`). |
| `source_type` | enum | Typically `scenario` or `synthetic`. |

### 5.3 `Supply`

| Field | Type | Notes |
|---|---|---|
| `id` | string | Supply source id. |
| `commodity` | enum | `medical` \| `food` \| `fuel`. |
| `available_units` | float | Units available to ship. |
| `entry_port_options` | string[] | Ports that can receive this supply. |
| `source_type` | enum | Typically `scenario` or `synthetic`. |

### 5.4 `Route`

A candidate way to satisfy a demand through a given port. Precomputed in the
dataset (v1 does not do live road/sea routing).

| Field | Type | Notes |
|---|---|---|
| `id` | string | e.g. `taichung->medical-south`. |
| `from_port` | string | Port id. |
| `to_demand_node` | string | Demand node id. |
| `distance_km` | float | Planning distance. |
| `baseline_eta_hours` | float | Planning ETA under normal conditions. |
| `per_unit_cost` | float | Relative transport cost index per unit. |
| `route_risk` | float | 0–1 planning risk index (e.g. weather/exposure). |
| `path_geometry` | GeoJSON LineString \| null | Optional display polyline. |
| `source_type` | enum | See Section 6. |

### 5.5 `DisruptionScenario`

| Field | Type | Notes |
|---|---|---|
| `id` | string | e.g. `kaohsiung-disruption`. |
| `name_zh` / `name_en` | string | Bilingual label. |
| `disrupted_ports` | string[] | Ports marked unavailable. |
| `capacity_overrides` | map | Optional per-port capacity reductions. |
| `description_zh` / `description_en` | string | Neutral, non-attributed text. |
| `source_type` | enum | Always `scenario`. |

### 5.6 `Allocation` (output)

| Field | Type | Notes |
|---|---|---|
| `demand_id` | string | Which demand this allocation satisfies. |
| `assignments` | list | Each: `{ port_id, route_id, units, eta_hours, cost, risk }`. |
| `satisfied_units` / `unmet_units` | float | Fulfillment accounting. |
| `score` | float | Composite objective value (lower = better). |

### 5.7 `DecisionBrief` (output)

| Field | Type | Notes |
|---|---|---|
| `scenario_id` | string | Scenario evaluated. |
| `summary_zh` / `summary_en` | string | 1–3 sentence human-readable recommendation. |
| `recommended_allocations` | Allocation[] | Chosen plan. |
| `alternatives` | list | Per-port comparison table (ETA/dist/cost/capacity/risk). |
| `trade_offs` | string[] | Explicit trade-offs for human review. |
| `unmet_demand` | list | Any demand that could not be satisfied. |
| `provenance_note` | string | Truth-boundary disclaimer (Section 6). |
| `assumptions` | string[] | Named assumptions behind the figures. |

---

## 6. Truth / provenance model

Nothing synthetic may masquerade as official operational data. Every record and
every brief carries a provenance label drawn from a four-level enum:

| `source_type` | Meaning | Example in this module |
|---|---|---|
| `official` | Published, citable public fact. | Port name and approximate public coordinates. |
| `derived` | Computed from an official/public value by a stated method. | Great-circle distance between two public port coordinates. |
| `scenario` | A deliberate planning assumption for the demo scenario. | "Kaohsiung is unavailable"; demand quantities. |
| `synthetic` | Fabricated placeholder with no real-world claim. | Relative cost indices, abstract capacity units, route risk. |

Rules:

- Capacity, cost, inventory, fuel, and medical-demand figures in v1 are
  `scenario` or `synthetic` and must be visibly labeled as such in the API
  response and in the UI. The module must never present them as real government
  or operational data.
- Port coordinates reuse the existing public civilian `COMMERCIAL_PORTS` list
  and are labeled `official` (public) for the coordinate/name only.
- Distances computed from public coordinates are `derived` with the method
  named (great-circle / geodesic).
- Every `DecisionBrief` carries a `provenance_note` stating the figures are
  scenario-based planning estimates for human review, not real operational data
  and not a prediction of a real event.
- A machine-readable `provenance_summary` in the API lists how many fields of
  each `source_type` contributed, so the UI can render an honest truth badge.

---

## 7. Optimization method

### 7.1 Candidates compared

| Method | Pros | Cons for a hackathon MVP |
|---|---|---|
| **Weighted deterministic scoring + greedy priority allocation** | Fully transparent, trivially explainable, no solver dependency, instant, easy to test, maps directly to a Decision Brief. | Not globally optimal for coupled capacity contention. |
| **Linear programming (LP)** | Globally optimal for the linear objective; handles capacity elegantly. | Adds a solver dependency; harder to explain; overkill at this scale. |
| **Min-cost flow** | Natural fit for supply→port→demand with capacities. | Needs graph/solver tooling; explanation and risk/priority weighting are awkward; more moving parts. |

### 7.2 Decision

**Select weighted deterministic scoring with greedy priority-ordered,
capacity-aware allocation** for the MVP.

Rationale: the overriding product requirements are **explainability** and
**reliability within hackathon time**, not mathematical optimality on a tiny,
hand-curated dataset (3 ports, 3 commodities). Deterministic scoring is:

- transparent — every number in the brief traces to named inputs and weights;
- dependency-free — no LP/flow solver, no new package (important while Phase 8
  owns the dependency files);
- stable and instant — pure Python arithmetic, easy to unit test exactly;
- directly explainable — the score decomposition *is* the Decision Brief.

The design keeps the solver behind a `scoring`/`optimizer` seam so a future
phase could swap in LP or min-cost flow without changing the API contract, if a
larger, contested-capacity dataset ever justifies it. The MVP does not do this —
avoiding complexity we do not need is itself a design decision.

---

## 8. Objective function

For each demand `d` (processed in ascending `priority`, then descending
`quantity`), each candidate route `r` through a non-disrupted port `p` receives
a **cost score** (lower is better):

```text
score(d, r) =
      w_time     * norm(eta_hours(r))
    + w_cost     * norm(per_unit_cost(r) + base_handling_cost(p))
    + w_risk     * route_risk(r)
    + w_capacity * capacity_penalty(p, d)
```

Where:

- `norm(x)` is min–max normalization of that term across the current candidate
  set, so all terms are comparable on `[0, 1]` and no single raw unit dominates;
- `capacity_penalty(p, d)` rises as the port's remaining capacity falls below
  the demand's required units (0 when ample, approaching 1 when the port cannot
  absorb the demand, and a hard exclusion when remaining capacity is zero);
- `route_risk(r)` is the dataset's `[0,1]` planning risk index.

**Priority** is handled by *ordering*, not inside the score: higher-priority
demand (medical before food before fuel) is allocated first and claims capacity
first. This makes the priority logic explicit and auditable rather than buried
in a weight.

Default weights (configuration, surfaced in the response for transparency):

```text
w_time     = 0.35
w_cost     = 0.25
w_risk     = 0.20
w_capacity = 0.20
```

Weights are a named assumption and are returned with the brief. The brief shows
the per-term contribution for each chosen assignment, so a human can see *why*
one port beat another (e.g. "Taichung chosen: lower ETA term 0.10 vs Keelung
0.42; comparable cost; both within capacity").

---

## 9. Constraints

The greedy allocation enforces:

1. **Port availability** — a port in `disrupted_ports` is excluded from all
   candidate routes.
2. **Route availability** — only routes present in the dataset for
   `(port, demand_node)` are eligible; a missing route means that port cannot
   serve that demand.
3. **Capacity** — the sum of units assigned to a port across all demands must
   not exceed its (possibly overridden) `capacity_units`. Remaining capacity is
   decremented as demands are allocated in priority order.
4. **Demand satisfaction** — each demand is satisfied up to available
   capacity/supply; any shortfall is reported as `unmet_units` (never hidden).
   A demand may be **split** across multiple ports when a single port lacks
   capacity.
5. **Supply availability** — assigned units for a commodity cannot exceed total
   `available_units` of matching supply via `entry_port_options`.
6. **Priority** — demands are allocated in ascending `priority` so critical
   (medical) demand claims scarce capacity first.

All constraints are deterministic and individually testable. Violations surface
as explicit `unmet_demand`, never as silent dropping.

---

## 10. API contract (future implementation)

New router mounted under `/logistics` (additive; no change to existing routes).
Read + one compute endpoint. No persistence.

### 10.1 `GET /logistics/scenarios`

Returns the available disruption scenarios (id, bilingual name, disrupted ports,
description, `source_type`).

```json
{
  "count": 1,
  "scenarios": [
    {
      "id": "kaohsiung-disruption",
      "name_zh": "高雄港中斷情境",
      "name_en": "Kaohsiung Port Disruption",
      "disrupted_ports": ["kaohsiung"],
      "source_type": "scenario"
    }
  ]
}
```

### 10.2 `GET /logistics/scenarios/{id}`

Returns the full scenario context: scenario record, affected demands, candidate
ports, candidate routes, and the `provenance_summary`. This lets the UI render
the scenario before running a simulation.

### 10.3 `POST /logistics/simulate`

Request body:

```json
{
  "scenario_id": "kaohsiung-disruption",
  "weights": { "time": 0.35, "cost": 0.25, "risk": 0.20, "capacity": 0.20 }
}
```

`weights` is optional; defaults from Section 8 apply. Response is a
`DecisionBrief` (Section 5.7) plus the per-port alternatives comparison and the
provenance summary:

```json
{
  "scenario_id": "kaohsiung-disruption",
  "summary_zh": "...",
  "summary_en": "...",
  "recommended_allocations": [ ... ],
  "alternatives": [
    {
      "port_id": "taichung",
      "eta_increase_hours": 9.5,
      "distance_increase_km": 180.0,
      "cost_change_pct": 14.0,
      "capacity_utilization": 0.82,
      "risk": 0.21
    },
    {
      "port_id": "keelung",
      "eta_increase_hours": 15.0,
      "distance_increase_km": 320.0,
      "cost_change_pct": 23.0,
      "capacity_utilization": 0.40,
      "risk": 0.28
    }
  ],
  "trade_offs": ["..."],
  "unmet_demand": [],
  "provenance_note": "Scenario-based planning estimates for human review; not real operational data and not a prediction of a real event.",
  "assumptions": ["Weights: time 0.35 / cost 0.25 / risk 0.20 / capacity 0.20", "Capacity in abstract units/day"],
  "provenance_summary": { "official": 6, "derived": 6, "scenario": 7, "synthetic": 12 }
}
```

The simulate endpoint is **pure**: same input dataset + request ⇒ same output.
It opens no socket, reads no live store, and persists nothing.

### 10.4 Error contract

- Unknown `scenario_id` → `404`.
- Malformed weights (negative, non-numeric) → `422` with a clear message;
  weights are normalized to sum to 1 before use, and the normalization is noted
  in `assumptions`.
- A scenario that leaves no feasible route for some demand returns `200` with
  that demand in `unmet_demand` — infeasibility is a valid, reported outcome,
  not an error.

---

## 11. Frontend workflow (future implementation)

Add a top-level view toggle alongside the existing live map, e.g.
`即時地圖 LIVE MAP` ⇄ `韌性物流 RESILIENCE LOGISTICS`. The existing
`LiveDashboard` is untouched; a new `features/logistics/` folder hosts the
Logistics view, which **reuses the existing `MapCanvas`**.

Logistics panel layout:

```text
Scenario            [ 高雄港中斷情境  Kaohsiung Port Disruption ▼ ]

Critical Demand     ● 醫療 Medical  (priority 1)
                    ● 食品 Food     (priority 2)
                    ● 燃料 Fuel     (priority 3)

Alternatives        臺中港 Taichung | 基隆港 Keelung
                    ETA | Distance | Cost | Capacity | Risk

                    [ 執行模擬  Run Simulation ]

Result              Recommended allocation (table)
                    Decision brief (text + trade-offs)
                    Truth badge: scenario / synthetic figures
```

Workflow:

1. User selects a scenario from a dropdown (`GET /logistics/scenarios`).
2. UI loads scenario context (`GET /logistics/scenarios/{id}`) and shows the
   disrupted port, affected demand, and candidate ports on the map.
3. User clicks **Run Simulation** (`POST /logistics/simulate`).
4. UI renders the recommended allocation table, the Decision Brief with
   trade-offs, and a visible **truth badge** derived from `provenance_summary`.
5. Map updates to show the selected solution's routes (Section 12).

All copy is bilingual (zh-Hant / English) via the existing i18n provider. The
truth badge and the `provenance_note` are always visible with any result.

---

## 12. Map visualization (future implementation)

Reuse the existing MapLibre `MapCanvas` and the public civilian
`COMMERCIAL_PORTS`. Add a logistics overlay layer group, controlled through the
existing layer-control pattern:

- **Ports** — reuse existing port markers; a disrupted port is restyled (muted
  / struck-through) and clearly labeled `中斷 / Disrupted`.
- **Demand nodes** — civilian destination markers, sized by priority.
- **Supply nodes** — civilian source markers.
- **Candidate routes** — thin neutral polylines for all eligible routes.
- **Selected solution** — the chosen allocation's routes highlighted, colored by
  commodity (medical / food / fuel), with units annotated.

Only **public civilian** ports, generic logistics context, and public roads/sea
lanes are shown. **No military bases, no deployments, no sensitive facilities.**
Route geometries are either public/`derived` great-circle lines or
dataset-provided display polylines, each labeled with its `source_type`. If a
route has no geometry, it is shown as a labeled port-to-node connector, never
fabricated as a precise operational path.

---

## 13. Failure states

| Failure | Required behavior |
|---|---|
| Unknown scenario id | `404`; UI shows a clear not-found message. |
| Dataset file missing/invalid at startup | Router loads with an empty scenario list and logs one actionable error; existing SeaWatch APIs are unaffected. |
| No feasible route for a demand | `200` with the demand in `unmet_demand`; UI shows unmet demand explicitly. |
| All candidate ports disrupted | `200`, every demand unmet, brief states no alternative within the scenario dataset. |
| Capacity insufficient for total demand | Partial allocation + reported `unmet_units`; brief states the shortfall and the trade-off. |
| Malformed weights | `422`; UI falls back to default weights with a note. |
| Map tiles unavailable | Inherit existing MapCanvas behavior (NLSC → fallback); logistics overlay still renders on whatever base map is available. |

No failure fabricates capacity, cost, or satisfied demand to look successful.

---

## 14. Tests (future implementation)

All tests are offline, deterministic, and need no network, solver, or live
store. Backend uses `pytest` (already configured); frontend uses the existing
Vitest setup.

Backend:

- **Dataset contract** — every record validates against its schema and carries a
  valid `source_type`; coordinates are within the Taiwan bbox.
- **Scoring** — exact score decomposition for a fixed scenario (golden values).
- **Allocation** — priority ordering (medical before food before fuel); capacity
  decrement; demand splitting across ports; `unmet_units` accounting.
- **Constraints** — disrupted port excluded; missing route excluded; supply cap
  enforced; all-ports-disrupted ⇒ all demand unmet.
- **Determinism** — identical input ⇒ byte-identical brief.
- **Weights** — normalization; invalid weights ⇒ `422`.
- **Provenance** — `provenance_summary` counts match the dataset; brief always
  carries the `provenance_note`.
- **Language discipline** — generated brief text contains none of the forbidden
  terms (order/command/tasking/military/etc.).
- **API** — `/logistics/scenarios`, `/logistics/scenarios/{id}` (incl. `404`),
  `/logistics/simulate` happy path + infeasible path; existing `/live/*` and
  `/health` remain registered and unchanged.

Frontend:

- Scenario dropdown renders and loads context.
- Run Simulation renders allocation table + brief + truth badge.
- Disrupted port is visibly marked; selected routes render.
- Bilingual copy switches correctly.
- Unmet demand is shown when present.

---

## 15. Integration seam with Phase 8

Phase 8 (SURVIVE) and Phase 9 (RESPOND) are **independent modules that meet at a
read-only seam**. Phase 9 never imports, mutates, or depends on Phase 8 internal
state.

Shared, stable surfaces only:

- **MapLibre `MapCanvas`** — Phase 9 reuses the existing map component and the
  public civilian `COMMERCIAL_PORTS` config; it adds its own overlay layers
  through the existing layer-control pattern.
- **i18n provider** — Phase 9 adds its own dictionary keys; it does not change
  existing keys.
- **`/live/health` (read-only)** — Phase 9 may *optionally* read the operating
  mode string (`CLOUD_LIVE` / `EDGE_LIVE` / ...) that Phase 8 adds to
  `/live/health`, purely to display a context banner such as
  "Running in Edge mode — logistics uses the local scenario dataset." It treats
  this as an opaque read-only string and never fails if the field is absent.
- **Routing isolation** — Phase 9 mounts a new `/logistics` router; it does not
  touch `/live/*`, `/resilience/*`, or `/edge/*`.

Explicit non-interference guarantees:

- No shared mutable store; no cross-import of `live/*` modules.
- No dependency added to `requirements.txt` / `package.json` by this module
  (deterministic scoring needs none), avoiding file-level conflicts with the
  Phase 8 worktree.
- The logistics dataset lives under a new path (e.g.
  `apps/api/seawatch/logistics/data/`), colliding with nothing in Phase 8.
- The two features can ship and demo independently; neither blocks the other.

Because the module is self-contained and dependency-free, it integrates cleanly
on top of Phase 8 once that branch merges, with no expected merge conflict in
`apps/api/` beyond adding one `include_router(logistics.router)` line in
`main.py` during the later implementation phase.

---

## 16. Future integration with maritime anomalies (#07 → #10)

The long-term SENSE → RESPOND loop:

```text
Live AIS / maritime condition (SENSE, #07)
        -> SeaWatch maritime review signal
        -> suggested port/route disruption condition
        -> logistics impact (RESPOND, #10)
        -> alternative port / route
        -> Resilience Decision Brief
```

The v1 seam that makes this possible without rework: a `DisruptionScenario` can
in future be **constructed from a maritime signal** instead of selected manually.
Because the simulator consumes a `DisruptionScenario` object (not a UI click), a
later phase can add an adapter that proposes a scenario (e.g. "elevated review
activity near Kaohsiung approaches → suggest a Kaohsiung-disruption scenario for
the analyst to run") while keeping a human in the loop. v1 deliberately stops at
**manual scenario selection** and does not auto-trigger, consistent with the
decision-support (not autonomous) principle. No anomaly auto-trigger is built in
this phase.

---

## 17. Safety and integrity

- Civilian logistics only: public maritime data, scenario planning, decision
  support.
- Excluded: military logistics optimization, weapons transport, operational
  military routing, military base supply planning, sensitive deployment data.
- Only public civilian ports and generic logistics context appear on the map.
- All non-official figures are labeled `scenario` or `synthetic` and never
  presented as real operational data.
- Output is advisory only; the brief always states it is for human review and is
  neither an instruction nor a prediction of a real event.
- Consistent with #07, the module makes no intent, hostility, legality, or
  identity determination.

---

## 18. Demo script (SENSE → SURVIVE → RESPOND)

1. **SENSE** — Open SeaWatch Cloud Live. Show live Taiwan AIS, select a vessel,
   view its track and an explainable review candidate.
2. **SURVIVE** — Simulate loss of Internet (Phase 8). SeaWatch switches to Edge
   Live / offline map on localhost; the operator still has situational
   awareness. *(Owned by Phase 8; shown, not re-implemented here.)*
3. **RESPOND** — Switch to the Resilience Logistics view. Select
   `Kaohsiung Port Disruption`. The map marks Kaohsiung as disrupted and shows
   affected medical/food/fuel demand and the Taichung/Keelung alternatives.
   Click **Run Simulation**. SeaWatch computes:
   - affected demand and whether it can be satisfied;
   - alternative ports with ETA / distance / cost / capacity / risk;
   - a recommended, priority-ordered allocation;
   - trade-offs.
   Read the **Resilience Decision Brief** aloud, pointing at the visible truth
   badge: these are scenario-based planning estimates for human review.

Close by restating the one story: SeaWatch helps analysts **SENSE** what is
happening, **SURVIVE** disruption to its own operation, and **RESPOND** with an
explainable logistics decision brief — always with a human in the loop.

---

## 19. Deliverable for this round

This round delivers **only this design document**. No implementation plan, no
application code, no dependency change, no deployment, no merge. Implementation
is a separate future phase that must honor Sections 2 and 15 (additive,
isolated, no interference with Phase 8).

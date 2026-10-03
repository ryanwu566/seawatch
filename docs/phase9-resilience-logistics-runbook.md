# Phase 9 Resilience Logistics demo runbook

This runbook drives the SeaWatch **SENSE → SURVIVE → RESPOND** demonstration on
one Windows laptop. Phase 9 adds only the **RESPOND** layer: a deterministic,
explainable, decision-support simulation for a civilian port-disruption
scenario. It is **for human review only** — not an instruction, a prediction,
or an autonomous command. All capacity, cost, risk, and demand figures are
`scenario`/`synthetic` planning values, never real operational data.

Phase 9 adds no new runtime dependency, reuses the Phase 8 shared API client
(`getBaseUrl`) and map/offline machinery, and consumes Phase 8 only through the
stable, read-only `/resilience/status` contract.

## Prerequisites

- The prepared repository, Python virtual environment, and built web UI, exactly
  as in the Phase 8 runbooks (`docs/edge-ais-runbook.md`,
  `docs/offline-startup-runbook.md`).
- No Internet, SDR, AIS-catcher, PMTiles archive, database, or production secret
  is required for the RESPOND simulation. The logistics backend is pure: same
  request + same dataset ⇒ byte-identical result.

## Terminology (unchanged from Phase 8)

- **Cloud Live (`CLOUD_LIVE`)** — broad Taiwan network AIS coverage (the default
  public deployment).
- **Edge Live (`EDGE_LIVE`)** — only AIS received by the local VHF antenna via
  AIS-catcher UDP. Local coverage only; never Taiwan-wide.
- **Edge Replay (`EDGE_REPLAY`)** — recorded NMEA played back; always labeled
  replay/simulated, never RF live.
- **No live source (`NO_LIVE_SOURCE`)** — neither Cloud nor Edge is fresh.
- **Offline Demo** — synthetic, explicit-only, never live.

The logistics RESPOND layer works regardless of the operating mode and even if
the `/resilience/status` endpoint is absent.

---

## Demo story: SENSE → SURVIVE → RESPOND

The on-screen rail is labeled **Illustrative workflow / 演示流程**. It is a
presenter-guided narrative, not a report of an actual network failure, not an
automatic failover, and not a real-time transition.

### SENSE — existing maritime awareness

The LIVE MAP view is the existing SeaWatch product: Taiwan maritime situational
awareness from AIS behavioral observations, with explainable review-ranking.
This layer is unchanged by Phase 9. Start it per the Phase 8 runbook and show
the live/offline Taiwan map and vessel context.

### SURVIVE — honest operating context

SeaWatch distinguishes its live-source modes honestly. In the **RESILIENCE
LOGISTICS** view, an optional, read-only operating-context banner reflects the
current Phase 8 mode when `/resilience/status` is reachable:

- `CLOUD_LIVE` → broad Taiwan network feed
- `EDGE_LIVE` → local RF only (local antenna coverage)
- `EDGE_REPLAY` → recorded playback, not live RF
- `NO_LIVE_SOURCE` → no fresh live source

The banner is display-only. It never changes the logistics result and never
auto-triggers a scenario. If the endpoint is missing or errors, no banner is
shown and logistics still works.

### RESPOND — Kaohsiung Port Disruption decision support

1. Start the backend and open the built UI at `?demo=resilience` (same-origin,
   per the Phase 8 offline-startup runbook). For a pure RESPOND-only demo no
   live source is required.
2. The demo entry opens **RESILIENCE LOGISTICS** with **Kaohsiung Port
   Disruption** preselected. It does not start a simulation or manufacture a
   live-source transition.
3. Review the scenario context. It shows that
   Kaohsiung is the disrupted port and that southern medical, food, and fuel
   demand must be absorbed by alternative civilian ports (Taichung, Keelung).
4. Click **Run Simulation**. The view renders the allocation table, the
   bilingual Decision Brief, the trade-offs, unmet demand (none in this
   scenario), and the always-visible TruthBadge.

The map overlay reuses the Phase 8 NLSC → PMTiles → emergency basemap hierarchy,
shows only public civilian ports, and labels routes without authoritative
geometry as `SCHEMATIC CONNECTOR / 示意連線` — never as measured road or shipping
routes.

---

## Exact Kaohsiung simulate request/response

The RESPOND computation is a single pure endpoint. Request:

```http
POST /logistics/simulate
Content-Type: application/json

{"scenario_id": "kaohsiung-disruption"}
```

PowerShell against a local backend:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/logistics/simulate `
  -ContentType "application/json" `
  -Body '{"scenario_id":"kaohsiung-disruption"}'
```

Deterministic response (abridged to the demo-relevant fields; byte-identical on
every run with the shipped dataset and default weights):

```json
{
  "scenario_id": "kaohsiung-disruption",
  "summary_en": "Recommended allocation for the Kaohsiung Port Disruption scenario: 120 unit(s) routed to alternative civilian ports, 0 unit(s) unmet. Highest-priority medical demand is prioritized via taichung. These are planning estimates for human review, not an instruction.",
  "recommended_allocations": [
    {
      "demand_id": "medical-south",
      "assignments": [
        {"port_id": "taichung", "route_id": "taichung->south-node", "units": 30.0, "eta_hours": 9.5, "cost": 2.2, "risk": 0.21}
      ],
      "satisfied_units": 30.0,
      "unmet_units": 0.0
    },
    {
      "demand_id": "food-south",
      "assignments": [
        {"port_id": "taichung", "route_id": "taichung->south-node", "units": 30.0, "eta_hours": 9.5, "cost": 2.2, "risk": 0.21},
        {"port_id": "keelung", "route_id": "keelung->south-node", "units": 20.0, "eta_hours": 15.0, "cost": 2.6, "risk": 0.28}
      ],
      "satisfied_units": 50.0,
      "unmet_units": 0.0
    },
    {
      "demand_id": "fuel-south",
      "assignments": [
        {"port_id": "keelung", "route_id": "keelung->south-node", "units": 40.0, "eta_hours": 15.0, "cost": 2.6, "risk": 0.28}
      ],
      "satisfied_units": 40.0,
      "unmet_units": 0.0
    }
  ],
  "alternatives": [
    {"port_id": "taichung", "port_label": "臺中港 Taichung", "eta_hours": 9.5, "distance_km": 185.8, "per_unit_cost": 2.2, "capacity_units": 60.0, "capacity_utilization": 1.0, "risk": 0.21, "schematic": true, "schematic_label": "SCHEMATIC CONNECTOR / 示意連線", "route_source_type": "derived"},
    {"port_id": "keelung", "port_label": "基隆港 Keelung", "eta_hours": 15.0, "distance_km": 314.7, "per_unit_cost": 2.6, "capacity_units": 70.0, "capacity_utilization": 0.8571, "risk": 0.28, "schematic": true, "schematic_label": "SCHEMATIC CONNECTOR / 示意連線", "route_source_type": "derived"}
  ],
  "trade_offs": [
    "food: split across taichung, keelung because no single alternative port had enough remaining capacity; this is a planning estimate for human review."
  ],
  "unmet_demand": [],
  "provenance_note": "此為供人工審查的情境規劃估計值，並非真實作業資料，也非對真實事件的預測。 Scenario-based planning estimates for human review; not real operational data and not a prediction of a real event.",
  "provenance_summary": {"official": 3, "derived": 2, "scenario": 7, "synthetic": 0}
}
```

How to read it:

- **Medical first.** The highest-priority demand (medical, 30 units) is allocated
  before food and fuel; priority is expressed by allocation ordering, not a
  hidden weight.
- **Deterministic split.** Food (50 units) fills Taichung's remaining capacity
  (30 after medical) and then Keelung (20). The split is shown as two explicit
  rows so a human sees exactly how the demand was divided.
- **Totals.** 120 units routed to alternative civilian ports, 0 unmet.
- **Provenance preserved.** `distance_km` is `derived` (great-circle); ETA, cost,
  risk, and capacity are `scenario`/`synthetic` planning values; the brief always
  carries a provenance note and a `provenance_summary`. Nothing upgrades a
  `scenario`/`synthetic` figure to `official`.

The two read endpoints support the UI:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/logistics/scenarios
Invoke-RestMethod http://127.0.0.1:8000/logistics/scenarios/kaohsiung-disruption
```

---

## Hardware validation notes (PENDING — not yet validated)

The RESPOND simulation requires **no** radio hardware. The SENSE/SURVIVE live-RF
path is Phase 8 and **remains pending real-hardware validation**. The following
RTL-SDR / AIS-catcher acceptance items are **NOT yet validated** and must not be
presented as complete:

1. **PENDING** — RTL-SDR driver and AIS-catcher recognize the exact receiver.
2. **PENDING** — decodable live NMEA on UDP `127.0.0.1:10110` with an installed
   VHF/AIS antenna and local vessel traffic.
3. **PENDING** — measured real local RF range/coverage (never extrapolated
   Taiwan-wide).
4. **PENDING** — controlled Internet-disconnect exercise confirming
   `CLOUD_LIVE → EDGE_LIVE → CLOUD_LIVE` after the recovery hold.
5. **PENDING** — measured laptop/UPS runtime under receiver, API, and browser
   load.
6. **PENDING** — installation/validation of a licensed Taiwan PMTiles archive.

Until a field exercise with real hardware is performed and recorded, SeaWatch
makes no claim that live RTL-SDR Edge reception has been validated. The
automated Phase 9 and Phase 8 suites exercise software behavior only.

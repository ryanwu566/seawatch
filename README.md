# SeaWatch

Explainable maritime anomaly review combining live vessel feeds, historical
traffic context, geospatial reference layers, and human-in-the-loop detection.

## Overview

SeaWatch is a maritime situational-awareness prototype for reviewing vessel
behavior with evidence and context. When provider credentials are enabled, it
can acquire a live maritime picture through a protected Area Scan workflow. It
also combines historical vessel-presence context, maritime reference geography,
deterministic behavior rules, alert fusion, and optional model-based second
opinions in an analyst-facing Watch Floor.

SeaWatch is decision support, not an autonomous enforcement system. Alerts are
candidates for human review; they are not findings of hostile intent,
illegality, or authorization status.

## Key Features

### Live maritime picture

- Provider-backed Area Scan architecture with polygon and rectangle areas of
  interest.
- Deterministic provider query planning followed by exact WGS84 geometry
  filtering.
- Provider readiness, health, recovery, request-budget, and graceful-degradation
  handling.
- Normalized vessel categories and map visualization.
- Same-origin Vercel rewrites keep browser API requests on the public frontend
  origin.
- Provider credentials and raw provider identities remain server-side.
- Canonical Area Scan-to-Live Detection hook with a rolling live track buffer.

### Explainable detection

- Deterministic review signals for AIS gaps, loitering, rendezvous and
  clustering, zone entry, position jumps, identity conflicts, status mismatch,
  route deviation, and survey-pattern-related behavior.
- Risk fusion with an explainable factor breakdown, evidence, uncertainty,
  benign alternatives, and recommended analyst actions.
- Optional statistical or machine-learning second opinions when a compatible
  regional model is available. No model score is invented when a model is
  absent.
- Human review workflow for status decisions, notes, allow-list feedback, and
  path-review decisions.
- Scenario and Live operating modes in the Watch Floor.

### Historical context

- Historical Runtime v2 summary and Historical Context card.
- Historical Traffic Density visualization across 2,457 coarse traffic cells.
- The source runtime contains 33,209,747 standardized hourly vessel-presence
  observations representing 400,821 historical vessel IDs.
- Conservative cross-source identity policy: only unambiguous, valid
  dataset-internal identity candidates are eligible for matching.
- Optional local runtime bundle; the application remains usable when it is not
  installed.

> Historical Runtime data is standardized hourly vessel presence, not raw or
> message-level AIS. The approximately 0.1-degree cells are contextual summaries,
> not precise vessel positions or reconstructed live trajectories.

### Maritime reference context

- EEZ reference areas.
- Derived 12 NM territorial-sea reference polygons.
- Derived 12-24 NM contiguous-zone reference bands.
- Source provenance and overlapping claims are preserved without selecting a
  legally preferred claimant.

These layers are neutral reference context only. They are not for navigation,
sovereignty determinations, or legal adjudication.

### Resilience extension

- Deterministic, explainable disruption-scenario and logistics simulation.
- Offline-capable demonstration paths with explicit provenance labels.
- Synthetic planning values and recommendations remain subject to human review.

## Architecture

```mermaid
flowchart LR
    Provider[Live provider<br/>credentials required] --> AreaScan[Area Scan]
    AreaScan --> Validation[Validation, normalization,<br/>exact AOI filtering]
    Validation --> Adapter[Live Detection Adapter]
    Adapter --> Engine[Detection Engine]
    Engine --> Review[Rules, fusion,<br/>optional ML second opinion]
    Review --> WatchFloor[Watch Floor<br/>human review]

    Historical[Historical Runtime v2] --> HistoricalUI[Historical Context<br/>Traffic Density]
    HistoricalUI --> WatchFloor

    DetectionGIS[Approximate territory context<br/>used by detection] --> Engine
    GIS[Canonical reference overlays<br/>EEZ / 12 NM / 12-24 NM] --> WatchFloor
```

Historical hourly presence supplies coarse context; it does not create raw live
tracks. The live provider path and the historical context path remain separate
until they are presented to detection and analyst-review surfaces. Canonical
maritime reference overlays are map context; detection uses its separately
documented approximate territory context.

## Demo / Service Status

**Public frontend:** [seawatch-web.vercel.app](https://seawatch-web.vercel.app/)
(live provider scans may be unavailable; public uptime is not guaranteed).

> Public demo note: live provider-backed vessel scans may be unavailable because
> the paid API subscription is currently disabled. Historical Runtime features
> are available when the optional runtime bundle is configured locally; the
> public deployment may not include that bundle. The integration logic remains
> implemented in the repository.

### Code status

The provider adapter, Area Scan planning and validation, access controls, live
detection hook, Watch Floor behavior, historical runtime integration, and map
layers are implemented and preserved in this repository.

### Live external provider

**Live provider status:** The paid live vessel-data API used during development
has been disabled after the hackathon to avoid ongoing API charges. The provider
integration and detection pipeline remain implemented in the repository and can
be re-enabled with valid credentials.

Datalastic live API access is therefore currently disabled due to subscription
cost. This is an operational cost decision, not removal or failure of the
integration. The public deployment must not be assumed to serve paid live
provider data.

### Historical Runtime

Historical Runtime v2 is an optional local bundle and is not checked into Git.
When it is absent, the API and interface report the unavailable state while the
remaining local, scenario, detection, and map functionality continues to work.

## Quick Start

Prerequisites: Python, Node.js, and npm versions compatible with the pinned
project dependencies.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Set-Location apps\web
npm ci
Set-Location ..\..
```

Start the backend from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn apps.api.seawatch.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```powershell
Set-Location apps\web
npm run dev
```

Open `http://localhost:5173`. API documentation is available at
`http://127.0.0.1:8000/docs`.

### Optional historical context

Point SeaWatch at an extracted Historical Runtime v2 bundle:

```powershell
$env:SEAWATCH_HISTORICAL_RUNTIME = "C:\path\to\SeaWatch_Runtime_Taiwan_2026_v2"
```

That path is only a generic Windows example. The bundle may live anywhere, is
optional, and must not be committed to this repository.

### Optional paid live provider

To re-enable the implemented Datalastic provider adapter, supply a valid
server-side credential before starting the backend:

```powershell
$env:DATALASTIC_API_KEY = "<your valid credential>"
```

`DATALASTIC_API_KEY` enables the provider adapter; authenticated Area Scan
requests remain fail-closed until the existing server-side access controls are
also configured. A local-only scan session requires a signing secret of at
least 32 bytes plus loopback auto-auth:

```powershell
$env:SEAWATCH_AREA_SCAN_SIGNING_KEY = "<at least 32 random bytes>"
$env:SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK = "true"
```

Loopback auto-auth is for local development only. Controlled deployments use
the existing `SEAWATCH_AREA_SCAN_OPERATOR_KEY` instead; see the
[demo readiness runbook](docs/demo-readiness-runbook.md). The repository does
not contain these credentials. Never expose a key to the browser, print it in
logs, or commit it.

## Data, Provenance, and Limitations

- Historical Runtime v2 contains standardized hourly vessel presence, not raw
  AIS messages. Its approximately 0.1-degree grid cannot support message-level
  trajectory claims.
- Historical Traffic Density is analyst context, not a threat, risk, or
  suspicious-activity map.
- AIS and provider identity fields are self-reported or externally supplied and
  may be incomplete, stale, duplicated, or incorrect.
- Missing AIS can result from coverage, equipment, transmission, or processing
  conditions; it does not by itself prove suspicious behavior.
- Alerts are prioritized human-review candidates, not determinations of intent,
  identity, legality, or guilt.
- Maritime boundaries and derived zones are reference-only and are not suitable
  for navigation, sovereignty decisions, or legal adjudication.
- Provider-backed live behavior depends on valid external credentials and
  provider availability.
- Optional model results depend on compatible local artifacts and regional
  validation. Core rule-based detection does not require an ML model.

See [data provenance](docs/data-provenance.md), the
[Taiwan historical-data notes](docs/taiwan-real-data.md), and the
[maritime reference dataset documentation](data/gis/taiwan_maritime_reference/README.md)
for source-specific details and licenses.

## Privacy and Security

- Provider credentials, raw MMSI values, and provider-specific identities remain
  backend-only on the live integration path.
- Browser responses use public vessel identifiers generated by the backend.
- Historical/live identity joins use a conservative policy; shared, malformed,
  or ambiguous identities are rejected rather than guessed.
- The integration does not fabricate MMSIs when a source identity is missing.
- Area Scan uses short-lived signed capabilities, protected operator sessions,
  bounded request bodies, secure cookie defaults, and fail-closed configuration.
- Provider requests are bounded by scan-size, vessel-count, concurrency,
  caching, and shared request/rate-limit controls.

Secret values are never part of the public status or frontend payloads.

## Development and Testing

Backend and frontend test suites cover live adapters, Area Scan, historical
runtime behavior, map layers, detection logic, and analyst-facing components.

```powershell
python -m pytest

Set-Location apps\web
npm test
npm run build
```

The project intentionally avoids permanent test-count badges; counts change as
the prototype evolves.

## Repository Structure

```text
apps/api/      FastAPI services, provider adapters, detection, and runtimes
apps/web/      React, TypeScript, MapLibre, and Watch Floor UI
data/gis/      Versioned maritime reference layers and provenance
docs/          Architecture, runbooks, validation reports, and source notes
scripts/       Data preparation, evaluation, training, and demo utilities
tests/         Backend unit and integration tests
```

Large raw datasets, generated models, local caches, and the optional Historical
Runtime bundle are not repository artifacts.

## Further Documentation

- [Integration guide](docs/INTEGRATION.md)
- [Area Scan and Live Detection hook](docs/area-scan-detection-hook.md)
- [Live Detection Adapter](docs/live-detection-adapter.md)
- [Detection stack](docs/detection-stack.md)
- [Demo readiness runbook](docs/demo-readiness-runbook.md)
- [Edge AIS operations](docs/edge-ais-runbook.md)
- [Resilience logistics runbook](docs/phase9-resilience-logistics-runbook.md)

## Project Principles

- Explainability over black-box conclusions.
- Human review over autonomous judgment.
- Reproducible provenance over hidden data transformations.
- Decision support over claims of hostile intent or illegality.

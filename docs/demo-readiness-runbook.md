# Demo readiness runbook

This runbook starts the existing SeaWatch API and production web build on one
Windows machine. It does not add a new data path or substitute demo data when a
live or historical source is unavailable.

## Required configuration

From the repository root, supply the deployment's existing stable identity key:

```powershell
$env:SEAWATCH_IDENTITY_KEY = "<existing stable live/historical identity key>"
```

Use the same `SEAWATCH_IDENTITY_KEY` for every run that must join live vessel
identities to historical baselines. `start_demo.ps1` never creates or rotates
this key. Retrieve it from the approved secret store; a new per-run value breaks
live/historical identity continuity.

If local historical GFW data should be available, also point SeaWatch at the
root containing `ais/historical/processed/daily/*.parquet`:

```powershell
$env:SEAWATCH_DATA_ROOT = "C:\path\to\seawatch-data"
```

The historical store remains lazy. Files and environment variables alone do
not make it ready.

## Live ingest choice

When `SEAWATCH_LIVE_INGEST` is absent, `start_demo.ps1` enables the existing
anonymous Open Waters ingest for that process. Any explicit value is preserved.
To keep live ingest off:

```powershell
$env:SEAWATCH_LIVE_INGEST = "false"
```

An upstream connection failure is a warning, not an API startup failure. Check
`/live/health` for provider connectivity and freshness; the API and explicit
illustrative vessel scenario remain available when the provider is degraded.

## Preflight and start

Run preflight without rebuilding or starting the server when a current web
build already exists:

```powershell
.\start_demo.ps1 -PreflightOnly -SkipWebBuild
```

For a normal demo start, build the web application and launch FastAPI:

```powershell
.\start_demo.ps1
```

Open `http://127.0.0.1:8000/?demo=vessel`. The `demo=vessel` query is the only
opt-in for the existing deterministic vessel scenario. It opens with a visible
`DEMO / illustrative data (not live AIS)` label. Without that exact query,
SeaWatch does not enter the vessel scenario. The scenario does not request a
separate historical baseline and does not add satellite evidence; those
sections remain unavailable or absent instead of being fabricated. The fixed
route-deviation and geographic-context fixture remains labeled as part of the
existing illustrative scenario.

## Readiness interpretation

`GET /health` always reports API liveness separately from the historical store:

- `historical: not_initialized` — no historical lookup has attempted to build
  the process store.
- `historical: available` — the process store actually initialized
  successfully. This can be true even when a particular opaque vessel has no
  matching baseline.
- `historical: unavailable` — initialization failed and that sanitized failure
  is cached for the process lifetime. Correct the configuration or data, then
  restart the API before retrying.

The health endpoint never infers historical readiness from configuration or
filesystem presence.

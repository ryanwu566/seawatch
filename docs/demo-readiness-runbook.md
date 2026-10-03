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

Supply the paid live provider key only to the backend process:

```powershell
$env:DATALASTIC_API_KEY = "<private Datalastic key>"
```

The value is sent to Datalastic only in the server-side `x-api-key` header. It
must not be placed in Vite variables, browser code, URLs, logs, screenshots, or
fixtures. `.env.example` contains a blank placeholder only.

Area Scan is a paid, explicitly triggered operation. Always configure a
high-entropy capability-signing key of at least 32 bytes. Public deployments
also require an independent out-of-band operator credential:

```powershell
$env:SEAWATCH_AREA_SCAN_SIGNING_KEY = "<private high-entropy signing key>"
$env:SEAWATCH_AREA_SCAN_OPERATOR_KEY = "<private operator credential>"
```

Neither value is the Datalastic key. Do not place any of them in Vite variables,
URLs, logs, screenshots, or fixtures. The operator credential is supplied to
the login form out of band; the signing key is never supplied to the browser.
The backend exchanges a valid operator credential for a 15-minute signed
capability in a `SameSite=Strict`, `HttpOnly` cookie. JavaScript cannot read the
capability, and the login field is cleared after submission. If either secret
is missing or too short, or an admission-limit setting is invalid, the workflow
fails closed. This is controlled-demo authentication, not production user
identity, per-user authorization, or revocation.

For the controlled local demo only, password entry can be replaced with an
explicit loopback-only opt-in:

```powershell
$env:SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK = "true"
```

The backend accepts this mode only when the request URL host is exactly
`localhost` or `127.0.0.1` and the direct socket peer is loopback. It still issues
the same 15-minute signed HttpOnly capability cookie. A spoofed loopback `Host`
from a non-loopback peer, a public host reached through a loopback peer, an
unset/false flag, or an invalid flag value cannot bypass operator
authentication. No operator credential is required in this local-only mode.

Cookies are secure by default and therefore require HTTPS. Loopback auto-auth
automatically permits its HttpOnly cookie over the verified local HTTP request.
For manual operator authentication on `http://127.0.0.1:8000`, use the separate
explicit local exception:

```powershell
$env:SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE = "true"
```

Never use that exception on a non-loopback or shared HTTP deployment. Omit it
behind HTTPS. The backend ignores the exception on non-loopback request hosts.
`start_demo.ps1` reports the cookie and session mode without printing any key.

The backend enforces a hard 64-KiB request-body ceiling, 4 accepted scans per
minute, and 32 reserved provider requests per minute. The body setting may only
lower that ceiling. A cache miss atomically reserves the
entire worst-case provider request count (covering circles plus one shared
retry) before starting Datalastic traffic. Override these process-local limits
only with positive integers:

```powershell
$env:SEAWATCH_AREA_SCAN_MAX_BODY_BYTES = "65536"
$env:SEAWATCH_AREA_SCAN_MAX_SCANS_PER_MINUTE = "4"
$env:SEAWATCH_AREA_SCAN_MAX_PROVIDER_REQUESTS_PER_MINUTE = "32"
```

Invalid values disable Area Scan without preventing the rest of the API from
starting.

## Live ingest choice

Any explicit `SEAWATCH_LIVE_INGEST` value is preserved exactly, including
`false`. When it is absent, `start_demo.ps1` defaults the existing anonymous
Open Waters ingest off if `DATALASTIC_API_KEY` is configured; without a
Datalastic key, it preserves the anonymous Open Waters default by enabling it.
To explicitly keep continuous ingest off:

```powershell
$env:SEAWATCH_LIVE_INGEST = "false"
```

An upstream connection failure is a warning, not an API startup failure. Check
`/live/health` for cached provider connectivity and freshness; neither that
endpoint nor global `/health` initiates provider traffic. The API and explicit
illustrative vessel scenario remain available when a live provider is degraded.

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

During the web build, `start_demo.ps1` removes `SEAWATCH_*`, `DATALASTIC_*`,
and `GFW_API_TOKEN` values from the npm child environment, then restores them
only for the backend process. This keeps permanent backend credentials outside
the frontend toolchain as well as outside the generated bundle.

Open the real-data application at `http://127.0.0.1:8000/`.

The separate `http://127.0.0.1:8000/?demo=vessel` URL is the only opt-in for
the existing deterministic vessel scenario. It opens with a visible
`DEMO / illustrative data (not live AIS)` label. Without that exact query,
SeaWatch does not enter the vessel scenario. The scenario does not request a
separate historical baseline and does not add satellite evidence; those
sections remain unavailable or absent instead of being fabricated. The fixed
route-deviation and geographic-context fixture remains labeled as part of the
existing illustrative scenario.

## Datalastic Area Scan

The Area Scan workflow is request-driven and never runs from pan, zoom, pointer
movement, drawing, or the ordinary eight-second vessel refresh:

1. Click **Area Scan**. With loopback auto-auth enabled, the backend immediately
   establishes the session without displaying a password field. Otherwise,
   enter the out-of-band operator credential and press **Authenticate**. The
   browser receives only an HttpOnly short-lived cookie; it never receives the
   signing key, operator key, or Datalastic key.
2. Choose **Polygon** or **Rectangle** and draw the region in Taiwan waters.
3. Confirm the visible outline, then press **Scan Area**. Drawing, panning,
   zooming, and the ordinary live refresh never initiate a paid request.
4. Inspect the returned real-vessel count and emphasized map markers.
5. Select a vessel to open the existing Vessel panel. Area Scan selection uses
   a source-qualified Datalastic track lookup, even if the ordinary live layer
   contains the same opaque vessel ID.
6. Expand Vessel Intelligence to inspect available historical evidence.

Live Area Scan positions come from **Datalastic Live AIS**. Historical evidence
comes separately from **Global Fishing Watch historical vessel presence on
SSD**; it is standardized vessel-presence data, not raw AIS messages. The two
sources join only when Datalastic supplies a structurally valid, unambiguous
MMSI and both pipelines use the same stable `SEAWATCH_IDENTITY_KEY`. Missing,
placeholder, malformed, or conflicting MMSI evidence never fabricates a
historical match. IMO and Datalastic UUID remain provider-local only. Provider
unavailability remains visible and is never replaced with illustrative vessels,
historical data, or satellite evidence.

`scanned_at` reports when the request completed; it does not assert that every
position was observed at that moment. Each vessel retains its provider
`observed_at` and a `fresh` or `stale` state. SeaWatch marks a known position
stale after 15 minutes and does not dead-reckon a stale Area Scan position.

Datalastic currently bills Location Traffic at one credit per vessel returned,
up to 500 credits per provider request. SeaWatch caps a scan at 16 provider
circles, uses at most 45 NM per working circle (below Datalastic's 50-NM
maximum), and retains at most 1,000 normalized scan vessels. The 1,000-vessel
retention limit cannot undo credits already billed upstream: a worst-case
16-circle scan can still cost up to 8,000 credits. Small single-circle polygons
use a tight conservative radius instead of a 45-NM query.

The process-local defaults allow 4 accepted scans and reserve at most 32
provider requests per minute. Each cache miss reserves all circles plus the one
shared retry before the first call; rejection launches zero Datalastic calls.
These are request controls, not an exact monetary-credit ceiling, and each API
worker has its own counters. The shared concurrency ceiling of two includes the
startup `/stat` probe as well as scan-circle requests. Cookie-authenticated
scans also require JSON plus the frontend's non-simple confirmation header;
this forces cross-origin browsers through the configured CORS preflight while
the signed capability remains the actual authentication. HTTP 402 is surfaced
as a sanitized quota-exhausted error. An HTTP 429 can consume the scan's single
retry only when
`Retry-After` is an integer from 0 through 5 seconds; other values are neither
slept nor reflected to the browser.

## Readiness interpretation

`GET /health` always reports API liveness separately from the historical store:

- `historical: not_initialized` - no historical lookup has attempted to build
  the process store.
- `historical: available` - the process store actually initialized
  successfully. This can be true even when a particular opaque vessel has no
  matching baseline.
- `historical: unavailable` - initialization failed and that sanitized failure
  is cached for the process lifetime. Correct the configuration or data, then
  restart the API before retrying.

The health endpoint never infers historical readiness from configuration or
filesystem presence.

# Offline localhost startup runbook

The Edge production UI and FastAPI must share the exact origin
`http://127.0.0.1:8000`. No npm development server is used during operation.

## Build the Edge UI

From `apps/web`, first ensure neither the process environment nor a local Vite
environment file defines `VITE_API_BASE_URL`:

```powershell
Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
Get-ChildItem -Force .env* | Select-String -Pattern '^\s*VITE_API_BASE_URL\s*='
```

The second command must return no active assignment. Move any local `.env`
containing one out of `apps/web` before building. Then:

```powershell
npm run build
rg "http://localhost:8000|seawatch-bgsi.onrender.com|seawatch-web.vercel.app" dist
```

The scan must return no match. A production build with no explicit API base uses
relative URLs such as `/live/vessels`, `/edge/health`, and
`/resilience/status`.

## Start local production service

From the repository root:

```powershell
$env:SEAWATCH_SERVE_WEB = "true"
$env:SEAWATCH_WEB_DIST = "apps/web/dist"
.\.venv\Scripts\python.exe -m uvicorn apps.api.seawatch.main:app --host 127.0.0.1 --port 8000
```

Open only `http://127.0.0.1:8000`. Relative API calls remain on that same
FastAPI process, so Edge operation needs no CORS and must not call
`http://localhost:8000`, Render, or Vercel. Set `SEAWATCH_PMTILES_FILE` before
startup if a local archive is installed. Without it, the emergency map is safe.

## Public Cloud build remains separate

Vercel must build with the explicit setting:

```text
VITE_API_BASE_URL=https://seawatch-bgsi.onrender.com
```

Render leaves `SEAWATCH_SERVE_WEB=false` (the default). This preserves the
Vercel-to-Render architecture. Never reuse a Cloud-built `dist` for Edge.

## Offline acceptance check

Pre-provision Chromium while online, then run:

```powershell
Set-Location apps/web
npx playwright test e2e/offline-edge.spec.ts --project=chromium
```

The test fails on every non-page-origin application/API/map request, including
localhost, Vercel, Render, NLSC, CDNs, remote fonts, glyphs, and sprites.

# SeaWatch Investigation Dashboard Design (Phase 5 MVP)

The Phase 5 dashboard is a lightweight, hackathon-ready **frontend** for the
TDTH 2026 demo. It consumes the existing SeaWatch FastAPI backend and adds no
backend logic. It is a human-in-the-loop investigation surface: analysts inspect
ranked behavioral review candidates and their feature-derived explanations.

Terminology is deliberately neutral. Candidates describe *behavior deviations*
and *unusual patterns* for *review priority*. The UI never uses "threat",
"hostile", or "illegal".

## Technology

- React 18 + TypeScript
- Vite (dev server + build)
- MapLibre GL (base map)
- Vitest + Testing Library (tests)

No Next.js, authentication, database, cloud deployment, Redux, or heavy UI
frameworks — state is plain React hooks.

## Project structure

```text
apps/web/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── .env.example              # VITE_API_BASE_URL
└── src/
    ├── main.tsx              # React entry point
    ├── App.tsx               # App shell -> Dashboard
    ├── styles.css            # Lightweight dark theme
    ├── api/
    │   ├── client.ts         # Typed fetch wrapper for the backend
    │   └── client.test.ts
    ├── components/
    │   ├── MapView.tsx        # MapLibre base map + selected track LineString
    │   ├── AlertList.tsx      # Ranked candidates table (selectable)
    │   ├── AlertDetail.tsx    # Investigation panel
    │   ├── Timeline.tsx       # Trajectory time summary
    │   ├── format.ts          # Presentation helpers
    │   └── components.test.tsx
    ├── pages/
    │   └── Dashboard.tsx      # Orchestrates data + selection state
    └── types/
        └── index.ts           # Types mirroring the API schemas
```

## Page structure

A single `Dashboard` page with a three-column layout:

```text
┌───────────────┬───────────────────────────┬─────────────────┐
│  Alert List   │  Map (top) + Timeline      │  Alert Detail   │
│  (ranked)     │  (bottom)                  │  (investigation)│
└───────────────┴───────────────────────────┴─────────────────┘
```

- **Left** — `AlertList`: ranked review candidates.
- **Center** — `MapView` above `Timeline`.
- **Right** — `AlertDetail`: full explanation of the selected candidate.

A header shows the app title and a live API health indicator.

## Component responsibilities

| Component     | Responsibility                                                                 |
|---------------|--------------------------------------------------------------------------------|
| `Dashboard`   | Fetches `/health` and `/alerts`; holds the selected `alert_id`; fetches `/alerts/{id}` on selection; passes data down. |
| `AlertList`   | Renders ranked rows (rank, track, score, method); emits selection. Empty/loading states. |
| `MapView`     | Renders a MapLibre base map and draws the selected track as a GeoJSON LineString (with endpoint markers) when geometry is available; shows loading / error / no-geometry / select placeholders otherwise. Never fabricates coordinates. |
| `AlertDetail` | Shows review priority (%), alert/track ids, score, method, rank, review status, explanation reasons, supporting features, and data quality. |
| `Timeline`    | Compact static trajectory time summary (date, observed duration, observations, average cadence). No animation. |
| `format.ts`   | Pure presentation helpers (priority %, duration, percentile, fraction).        |
| `api/client.ts` | Typed `fetch` wrapper; base URL from `VITE_API_BASE_URL`; `ApiError` on failures. |

## API usage

The dashboard consumes these existing endpoints only:

| Endpoint                      | Used by     | Purpose                                   |
|-------------------------------|-------------|-------------------------------------------|
| `GET /health`                 | Dashboard   | Header health indicator.                  |
| `GET /alerts`                 | Dashboard   | Ranked review candidates for the list.    |
| `GET /alerts/{id}`            | Dashboard   | Full detail for the selected candidate.   |
| `GET /tracks/{id}/geometry`   | Dashboard   | Privacy-safe track LineString for the map.|
| `GET /tracks`                 | client.ts   | Track metadata (client method available). |

The API base URL is configured via `VITE_API_BASE_URL` (see `.env.example`,
default `http://localhost:8000`). No backend logic is duplicated on the client.

All network access goes through `src/api/dataSource.ts`, which selects between
the live client (`src/api/client.ts`) and bundled demo fixtures based on
`VITE_DEMO_MODE`.

### Track geometry flow

The map draws the selected track's real trajectory. Coordinates are never
fabricated — they come from existing Phase 1 processed observations via a
read-only backend endpoint.

```text
AlertList: user clicks a candidate
        ↓
Dashboard: fetchAlert(alert_id)  → detail (includes track_id)
        ↓
Dashboard: fetchTrackGeometry(track_id)  → GeoJSON LineString
        ↓
MapView: draws the LineString + endpoints, fits bounds
```

- The endpoint returns a `LineString` (≥ 2 coordinate pairs) or `404` when a
  track has no available geometry. `MapView` shows a clear placeholder for the
  loading, error, and no-geometry states, and never invents positions.
- The geometry contains coordinates only; no vessel identity is present.

### Offline demo mode

`VITE_DEMO_MODE` guards a fully offline presentation path so a demo never fails
if the backend or data is unavailable:

- `VITE_DEMO_MODE=false` (default) — the dashboard uses the FastAPI backend.
- `VITE_DEMO_MODE=true` — the dashboard reads bundled fixtures from `src/demo/`
  (`demo_alerts.json`, `demo_details.json`, `demo_geometry.json`) and performs no
  network requests.

Demo data is **clearly labeled** and never presented as live: the header shows a
"Demo Mode" badge and a banner states the data is bundled sample data. The demo
health status reports `seawatch-demo`.

#### Offline presentation workflow

```bash
cd apps/web
cp .env.example .env
# set VITE_DEMO_MODE=true in .env
npm install
npm run dev        # or: npm run build && npm run preview
```

The dashboard then runs end to end (list → detail → map geometry) with no backend
and no raw data on the machine.

## Local development

```bash
cd apps/web
cp .env.example .env      # adjust VITE_API_BASE_URL if needed
npm install
npm run dev               # Vite dev server on http://localhost:5173
npm run build             # tsc --noEmit && vite build -> dist/
npm test                  # Vitest smoke tests
```

Run the backend separately (see `docs/api-design.md`) so the dashboard has an API
to consume.

## Testing

- `src/api/client.test.ts` — API client: base URL resolution, request URLs, the
  `shortlisted_only` filter, id encoding, and `ApiError` on error responses
  (fetch is mocked; fully offline).
- `src/api/dataSource.test.ts` — demo mode serves bundled fixtures with no
  network, returns a demo `LineString`, 404s unknown demo tracks, reports the
  `seawatch-demo` health service, and delegates to the network when demo mode is
  off.
- `src/components/components.test.tsx` — `AlertList` rendering/selection/empty
  state and `AlertDetail` rendering, including a guard that prohibited vocabulary
  (threat/hostile/illegal) never appears.
- `src/components/MapView.test.tsx` — `MapView` states (select / loading / error /
  has-geometry) with `maplibre-gl` mocked (jsdom has no WebGL context).

## Future extensions

- Alert-window markers along the track once the API exposes per-window positions.
- Track-centric view backed by `GET /tracks`.
- Filter/sort controls (by method, shortlisted-only, score threshold).
- Human review actions (mark relevant / false positive) if the backend adds write endpoints.
- Time-window animation across a track's observations.

## Explicitly out of scope for this MVP

Emergency logistics simulation, hardware integration, advanced map animations,
and authentication are **not** part of this phase.

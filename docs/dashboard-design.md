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
    │   ├── MapView.tsx        # MapLibre base map + alert markers
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
| `MapView`     | Renders a MapLibre base map. Plots alert markers when coordinates are available; otherwise shows an informative overlay (the current API is position-free). |
| `AlertDetail` | Shows review priority (%), alert/track ids, score, method, rank, review status, explanation reasons, supporting features, and data quality. |
| `Timeline`    | Compact static trajectory time summary (date, observed duration, observations, average cadence). No animation. |
| `format.ts`   | Pure presentation helpers (priority %, duration, percentile, fraction).        |
| `api/client.ts` | Typed `fetch` wrapper; base URL from `VITE_API_BASE_URL`; `ApiError` on failures. |

## API usage

The dashboard consumes these existing endpoints only:

| Endpoint             | Used by      | Purpose                                  |
|----------------------|--------------|------------------------------------------|
| `GET /health`        | Dashboard    | Header health indicator.                 |
| `GET /alerts`        | Dashboard    | Ranked review candidates for the list.   |
| `GET /alerts/{id}`   | Dashboard    | Full detail for the selected candidate.  |
| `GET /tracks`        | client.ts    | Available (client method provided for future track views). |

The API base URL is configured via `VITE_API_BASE_URL` (see `.env.example`,
default `http://localhost:8000`). No backend logic is duplicated on the client.

### A note on the map

The Phase 4 API exposes **privacy-safe metadata only** and does not return vessel
coordinates. `MapView` therefore renders a base map and an explanatory overlay
rather than fabricating positions. It is written to plot markers automatically if
the API is later extended with optional `longitude`/`latitude` fields, so no
rewrite is needed when geographic data becomes available.

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
- `src/components/components.test.tsx` — `AlertList` rendering/selection/empty
  state and `AlertDetail` rendering, including a guard that prohibited vocabulary
  (threat/hostile/illegal) never appears.

`MapView` is intentionally excluded from the render tests because MapLibre
requires a WebGL context that jsdom does not provide; it is covered by the
production `npm run build` typecheck instead.

## Future extensions

- Plot real vessel tracks and alert positions once the API exposes geometry.
- Track-centric view backed by `GET /tracks`.
- Filter/sort controls (by method, shortlisted-only, score threshold).
- Human review actions (mark relevant / false positive) if the backend adds write endpoints.
- Time-window animation across a track's observations.

## Explicitly out of scope for this MVP

Emergency logistics simulation, hardware integration, advanced map animations,
and authentication are **not** part of this phase.

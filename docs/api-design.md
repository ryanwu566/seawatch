# SeaWatch Dashboard API Design (Phase 4 Foundation)

The Phase 4 API is a **read-only** HTTP surface over the existing Phase 3B
explainable review-ranking outputs. It exists to feed a future React + MapLibre
investigation dashboard. It performs **no ranking computation** at request time
and modifies **no** Phase 1-3 data, logic, or artifacts.

Alerts are **behavioral review candidates** ranked by review priority. They
surface *unusual patterns* and *behavior deviations* for human review. They are
**not** threat assessments, findings of hostility, or determinations of legality.

## Architecture

```text
Phase 3B ranking outputs (local Parquet, read-only)
        ↓
services/  (artifacts loader → track_service, alert_service)
        ↓
schemas/   (Pydantic response models)
        ↓
api/       (FastAPI routers: health, tracks, alerts)
        ↓
main.py    (create_app factory)
        ↓
Future React + MapLibre dashboard
```

### Layering

| Layer      | Location                              | Responsibility                                        |
|------------|---------------------------------------|-------------------------------------------------------|
| Routers    | `apps/api/seawatch/api/`              | HTTP routing, status codes, query params only.        |
| Schemas    | `apps/api/seawatch/schemas/`          | Pydantic request/response contracts.                  |
| Services   | `apps/api/seawatch/services/`         | Read artifacts, map rows to schemas. No HTTP concerns. |
| App factory| `apps/api/seawatch/main.py`           | Wire routers into a `FastAPI` app.                    |

Business logic lives in services and stays independent of the web framework, so
routes remain thin and testable.

### Data source

The API reads the Phase 3B row-level ranking Parquet artifacts:

- `data/processed/review_ranking/test_rankings.parquet`
- `data/processed/review_ranking/calibration_rankings.parquet`

These artifacts are **local and gitignored**. They are produced by the Phase 3B
pipeline (`scripts/run_phase3b_review_ranking.py`) and are treated as immutable
inputs — the API only reads them. The data root can be overridden for tests and
alternative deployments with the `SEAWATCH_DATA_ROOT` environment variable.

If no artifact is available, data endpoints return **HTTP 503** rather than
fabricating results.

## Endpoints

### `GET /health`

Liveness check. Always available (does not touch artifacts).

Response `200 OK`:

```json
{
  "status": "ok",
  "service": "seawatch-api"
}
```

### `GET /tracks`

Available privacy-safe trajectory metadata, one record per distinct
`(track_id, date, window_id)`.

Response `200 OK`:

```json
{
  "count": 2,
  "tracks": [
    {
      "track_id": "2024-01-03__t-000042",
      "date": "2024-01-03",
      "duration": 3540.0,
      "observation_count": 118
    }
  ]
}
```

- `duration` is the observed trajectory-window duration in seconds.
- `503 Service Unavailable` if no ranking artifact exists.

### `GET /tracks/{track_id}/geometry`

Privacy-safe trajectory geometry for a track as a GeoJSON LineString. Geometry is
read from the existing Phase 1 processed observations (coordinates only; no vessel
identity) and is not recalculated.

Response `200 OK`:

```json
{
  "track_id": "2024-01-03__t-000042",
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [-122.4, 37.7],
      [-122.3, 37.8]
    ]
  }
}
```

- Coordinates are ordered by observation time; EPSG:4326 `[longitude, latitude]`.
- `404 Not Found` when the track has no available geometry (unknown track or
  fewer than two valid coordinates).
- `503 Service Unavailable` if no Phase 1 observation artifact exists.

### `GET /alerts`

Ranked review candidates ordered by descending review priority. The list is
**paginated and slim**: items omit `explanation_reasons` (load those via
`GET /alerts/{alert_id}`). This keeps the dashboard payload small — the ranking
frame holds ~28k window-level rows, which must never be shipped whole.

Query parameters:

| Name               | Type    | Default | Description                                             |
|--------------------|---------|---------|---------------------------------------------------------|
| `method`           | string  | (all)   | Restrict to one ranking method (e.g. `empirical_percentile`). |
| `shortlisted_only` | boolean | `false` | Return only candidates within the review budget.        |
| `dedupe_by_track`  | boolean | `false` | Keep only the highest-priority window per track.        |
| `limit`            | int     | `20`    | Page size (1–200).                                      |
| `offset`           | int     | `0`     | Number of leading candidates to skip (pagination).      |

The dashboard default combines these: `method=empirical_percentile`
(the Phase 3B primary method), `shortlisted_only=true`, `dedupe_by_track=true`,
`limit=20` — the Top-20 track-level review priorities.

Response `200 OK`:

```json
{
  "count": 1,
  "total": 12,
  "limit": 20,
  "offset": 0,
  "alerts": [
    {
      "alert_id": "2024-01-03__empirical_percentile__t-000042__w-0007",
      "track_id": "2024-01-03__t-000042",
      "date": "2024-01-03",
      "ranking_score": 87.42,
      "ranking_method": "empirical_percentile",
      "rank": 3,
      "shortlisted": true,
      "explanation_reasons": []
    }
  ]
}
```

- `count` is the items on this page; `total` is the match count before pagination.
- `explanation_reasons` is intentionally empty in the list; the field is retained
  for a stable shape. Load full reasons via `GET /alerts/{alert_id}`.
- `ranking_score` is a deterministic **review priority** value, not a probability
  or confidence measure.
- Filtering, sorting, deduplication, and pagination run on a cached read-only copy
  of the ranking frame (the Parquet artifact is not re-read per request).
- `503 Service Unavailable` if no ranking artifact exists.

### `GET /alerts/{alert_id}`

Full review candidate: ranking result, explanation, supporting features, and data
quality.

`alert_id` is a stable surrogate composed as
`{date}__{ranking_method}__{track_id}__{window_id}`.

Response `200 OK`:

```json
{
  "alert_id": "2024-01-03__isolation_forest__t-000042__w-0007",
  "track_id": "2024-01-03__t-000042",
  "date": "2024-01-03",
  "ranking_score": 87.42,
  "ranking_method": "isolation_forest",
  "rank": 3,
  "shortlisted": true,
  "review_status": "unreviewed",
  "explanation_reasons": [
    {
      "reason_code": "speed_higher",
      "feature_group": "speed",
      "feature_name": "sog_mean",
      "observed_value": 14.2,
      "unit": "knots",
      "reference_percentile": 0.985,
      "direction": "higher",
      "severity": 2.31,
      "message": "Sog mean is at the 98.5th percentile of the January 1 background.",
      "attribution_kind": "supporting_evidence"
    }
  ],
  "supporting_features": [
    {
      "feature_name": "sog_mean",
      "feature_group": "speed",
      "observed_value": 14.2,
      "unit": "knots",
      "reference_percentile": 0.985
    }
  ],
  "data_quality": {
    "observation_count": 118,
    "observed_duration_seconds": 3540.0,
    "max_gap_seconds": 120.0,
    "sog_valid_fraction": 0.99,
    "cog_valid_fraction": 0.98
  }
}
```

- `404 Not Found` if the `alert_id` does not exist.
- `503 Service Unavailable` if no ranking artifact exists.

## Status codes

| Code | Meaning                                                        |
|------|----------------------------------------------------------------|
| 200  | Success.                                                       |
| 404  | Requested `alert_id` not found.                                |
| 503  | Ranking artifacts not available (run the Phase 3B pipeline).   |

## Privacy rules

SeaWatch treats AIS data as **behavioral observations** and does not claim intent
or identity classification. The API enforces this at multiple layers:

1. **No identity fields are ever exposed.** MMSI, vessel name, IMO, and call sign
   are never present in Phase 3B outputs.
2. **Defense in depth.** The read-only artifact loader defensively drops any
   column whose name matches a known identity field
   (`mmsi`, `imo`, `name`, `callsign`, `call_sign`, `vessel_name`, `shipname`,
   `ship_name`) before data reaches the response schemas, even if an upstream
   change were to introduce one.
3. **Surrogate identifiers only.** `track_id`, `window_id`, and the derived
   `alert_id` are date-scoped surrogates, not real-world vessel identities.
4. **Neutral terminology.** Responses use *behavior deviation*, *review priority*,
   and *unusual pattern*. They avoid *threat*, *hostile*, and *illegal*.
5. **No fabrication.** When artifacts are missing, the API returns 503 instead of
   inventing data.

## Interpretation limits

- Rankings identify deviations from a statistical background **for human review
  only**. No ground-truth event labels, accuracy, precision, recall, or inferred
  intent are reported.
- `review_priority_score` is a ranking value, not a probability or confidence.
- Isolation Forest reasons are **supporting feature evidence**, not model
  attribution (`attribution_kind` distinguishes `exact_component` from
  `supporting_evidence`).
- Overlapping windows and repeated vessel tracks are dependent observations.

## Local development

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt

# Run the offline tests
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_dashboard_api.py -q

# Optional: run a live dev server (requires an ASGI server such as uvicorn)
& '.\.venv\Scripts\python.exe' -m pip install uvicorn
& '.\.venv\Scripts\python.exe' -m uvicorn apps.api.seawatch.main:app --reload
```

The application object is `apps.api.seawatch.main:app` (created by the
`create_app()` factory). No ASGI server is bundled with this foundation; tests
exercise the app in-process with Starlette's `TestClient`.

> Note: the repository `pytest.ini` sets `--basetemp=.pytest_cache/tmp`. If that
> directory is not writable in your environment, override it with
> `--basetemp=<writable-path>`. The API tests themselves are fully offline and do
> not depend on real local artifacts; they build synthetic fixtures under a
> temporary `SEAWATCH_DATA_ROOT`.

## Explicitly out of scope for this foundation

React, MapLibre, any frontend, authentication, database migrations, Docker, cloud
deployment, hardware, and the logistics simulation extension are **not** part of
this phase.

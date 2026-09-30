# Trajectory Feature Contract (Phase 2)

Phase 2 transforms the ignored Phase 1 EPSG:4326/UTC observation Parquet into
deterministic segment summaries, segmented observations, and window features.
It performs no anomaly labeling, scoring, model fitting, alerting, or behavior
classification.

## Input, configuration, and outputs

The input schema is exactly `track_id`, `base_date_time`, `longitude`,
`latitude`, `sog`, `cog`, `heading`, and `vessel_type`. Coordinates must be
finite WGS84 longitude/latitude, timestamps normalize to UTC, and the input
Parquet must declare `EPSG:4326` and `UTC` metadata.

The versioned configuration is:

| Setting | Value |
|---|---:|
| `segment_gap_seconds` | 600 |
| `window_duration_seconds` | 1800 |
| `window_stride_seconds` | 300 |
| `minimum_window_observations` | 10 |
| `minimum_observed_span_seconds` | 1200 |
| `minimum_valid_fraction` | 0.80 |
| `low_speed_threshold_knots` | 3.0 |
| `course_min_speed_knots` | 1.0 |
| `minimum_displacement_for_ratio_m` | 50.0 |

The segmented-observation output adds `segment_id`, `segment_ordinal`, and
`preceding_gap_seconds`. The segment summary records identifiers, UTC bounds,
duration, observation/gap/duplicate counts, navigation-field validity,
vessel-type consistency, and quality status. The window output records
segment/window surrogates, UTC bounds, observation/gap/duplicate counts,
feature-family validity, vessel-type consistency, quality status, then the ten
features below. Column order is fixed by code and tested.

## Segments and windows

- Observations are stable-sorted by surrogate `track_id`, UTC timestamp, and
  original row order.
- A new segment starts only when the preceding gap is strictly greater than
  600 seconds. No interpolation occurs.
- Segment IDs and window IDs are deterministic dataset-scoped surrogates.
- Windows are 1,800 seconds long, advance by 300 seconds, are anchored at each
  segment start, and use half-open membership `[start, end)`.
- Only full-duration windows are emitted; no window crosses a segment boundary.
- A window is sufficient with at least 10 observations and at least 1,200
  seconds between its first and last observation.
- Family-specific validity gates are recorded separately from movement values.

## Feature contract

| Feature | Unit | Definition |
|---|---|---|
| `sog_median_knots` | knots | Median valid AIS speed over ground |
| `sog_p95_knots` | knots | 95th percentile valid AIS speed over ground |
| `low_speed_fraction` | fraction | Valid SOG observations below 3 knots divided by valid SOG count |
| `low_speed_duration_seconds` | seconds | Positive-time intervals whose two endpoints are below 3 knots |
| `path_distance_m` | metres | Sum of consecutive WGS84 geodesic distances |
| `displacement_m` | metres | WGS84 geodesic distance from first to last observation |
| `path_displacement_ratio` | unitless | Path divided by displacement when displacement is at least 50 m |
| `course_change_abs_sum_deg` | degrees | Sum of eligible absolute circular COG changes |
| `course_change_abs_p95_deg` | degrees | 95th percentile eligible absolute circular COG change |
| `heading_cog_abs_median_deg` | degrees | Median absolute circular heading/COG difference |

Distances use `pyproj.Geod(ellps="WGS84")`; longitude/latitude degrees are
never treated as linear units. Angular differences wrap at 360 degrees.
Course and heading comparisons require SOG of at least 1 knot. Invalid or
sentinel navigation values become missing rather than zero. Duplicate-time
edges are retained and excluded from positive-time calculations.

All ten features are null for an insufficient window. In a sufficient window,
SOG features require at least one valid SOG value and at least 80% SOG
coverage. Course-change features require at least 80% valid COG coverage and
at least two eligible positive-time COG pairs whose two endpoint speeds are at
least 1 knot. The heading/COG feature requires at least one paired value and
80% paired coverage, with the same speed gate. Distance features require at
least two coordinates; the ratio additionally requires at least 50 metres of
displacement. A failed family gate leaves only that family null. Quality
status describes data usability, not vessel behavior.

## Privacy and provenance

Public artifacts may contain the Phase 1 surrogate `track_id`, but the schema
guard rejects direct source vessel identifiers. Private window membership is
removed before writing. Each Parquet embeds schema version, CRS, timezone,
source/config hashes, generator version, and a machine-readable units map.
The aggregate manifest and QA report contain no row-level vessel histories.

Generated real-data Parquet files stay ignored and local. The committed
manifest and report contain measured aggregate results only.

## Leakage and deferred work

Phase 2 features use only observations inside each window and do not use
future windows, learned fleet/corridor reference values, labels, or outcome
data. Overlapping windows intentionally share observations and are therefore
not independent samples. Phase 3 must partition by date and vessel-aware
groups before fitting or evaluation.

Acceleration/rate features, interpolation, corridor learning, reference
baselines, anomaly models, scores, thresholds, API/UI integration, storage,
and deployment are deferred and are not part of this contract.

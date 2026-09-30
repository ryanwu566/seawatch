# SeaWatch Phase 2 Trajectory Features Design

**Status:** Proposed for review; design and planning only

**Date:** 2026-09-29

**Base:** `feat/data-gis-foundation` at `5823b14b4fe1c6aada2f468149d98fd4dc64ef3c`

## 1. Purpose and boundaries

Phase 2 converts the validated Phase 1 observation table into deterministic
trajectory segments, time-based windows, interpretable movement features, and
quality metadata. It creates a trustworthy input contract for later rule and
model experiments; it does not label, fit, score, rank, or alert on anomalies.

The implementation must remain limited to the existing 2024-01-01 San
Francisco Bay cargo smoke data. It must not download another date, expose a
direct vessel identifier, interpolate gaps, add an API or UI, create an
application database, or begin challenge #10 work.

The eventual implementation branch is `feat/trajectory-features`, created
from the Phase 1 commit above. This planning turn does not create it.

## 2. Repository findings and authoritative input

The repository is clean, has no remote, and is on the validated Phase 1
branch and commit. The Phase 1 public processed contract is:

| Field | Meaning | Phase 2 treatment |
|---|---|---|
| `track_id` | deterministic dataset-scoped surrogate | required grouping key; never reversed or replaced with a source identifier |
| `base_date_time` | UTC observation timestamp | required, timezone-aware, sorted within track |
| `longitude` | WGS84 longitude in degrees | required, finite, within [-180, 180] |
| `latitude` | WGS84 latitude in degrees | required, finite, within [-90, 90] |
| `sog` | AIS speed over ground in knots | optional per observation; negative/non-finite values become missing with an audit count |
| `cog` | AIS course over ground in degrees | optional per observation; valid range [0, 360) |
| `heading` | AIS heading in degrees | optional per observation; valid range [0, 359]; sentinel 511 and other invalid values become missing |
| `vessel_type` | AIS-provided vessel type | retained as context, not independently verified identity |

The input has 5,581 rows and 15 complete tracks. Measured spacing is sparse
relative to a one-minute grid: median gap 180 seconds, p95 183 seconds, and
maximum 364 seconds. Track duration ranges from about 17.5 minutes to 23.95
hours. All smoke rows currently have valid SOG, COG, and heading values, but
the contract must continue to handle missing and sentinel values explicitly.

Direct identifiers are forbidden in feature inputs and publishable outputs:
`mmsi`, `source_vessel_id`, `source_id`, `vessel_name`, `imo`, and
`call_sign`, compared case-insensitively. This is an automated schema guard,
not a claim of anonymization. `track_id` remains susceptible to linkage and
enumeration as documented in Phase 1.

## 3. Considered approaches

### Recommended: geodesic primitives, deterministic gap segments, and fixed-duration sliding windows

Use `pyproj.Geod` with WGS84 for point distances, a configurable gap rule for
segments, and 30-minute windows advancing every 5 minutes. Window anchors are
relative to each segment's first timestamp. Only nominally complete windows
are emitted. Quality columns distinguish data sufficiency from movement
values. This stays correct in EPSG:4326, reuses installed dependencies, and
does not bind the feature layer to SF Bay.

### Alternative: project every segment into a local metric CRS

A suitable SF Bay projection would make Euclidean operations convenient, but
it introduces projection selection, transformation, and area-of-use checks
for little benefit at this scale. It would also make reuse outside SF Bay less
safe. This is not selected.

### Alternative: fixed-row windows and planar degree arithmetic

This is simpler but invalid. Actual observation spacing varies, fixed row
counts represent inconsistent durations, and degrees are not metres. This
approach is rejected.

## 4. Configuration

Commit a versioned configuration at `config/trajectory_features_v1.json`.
Defaults are engineering choices, not maritime standards:

| Setting | Default | Rationale |
|---|---:|---|
| `segment_gap_seconds` | 600 | split only when a gap is strictly greater than 10 minutes |
| `window_duration_seconds` | 1800 | 30-minute time window |
| `window_stride_seconds` | 300 | 5-minute output cadence |
| `minimum_window_observations` | 10 | compatible with the measured three-minute median spacing |
| `minimum_observed_span_seconds` | 1200 | require at least 20 minutes between first and last observation |
| `minimum_valid_fraction` | 0.80 | feature-family input coverage gate |
| `low_speed_threshold_knots` | 3.0 | neutral configurable low-speed feature threshold |
| `course_min_speed_knots` | 1.0 | suppress unstable COG interpretation at near-zero speed |
| `minimum_displacement_for_ratio_m` | 50.0 | avoid unstable path/displacement ratios near zero |

Configuration validation rejects non-positive durations and strides,
fractions outside [0, 1], a stride greater than the duration, and negative
speed or displacement thresholds. The exact configuration and its SHA-256 are
recorded in the feature manifest.

A read-only planning calculation found 3,216 nominally complete windows. A
10-observation/20-minute-span gate retained 2,829, while a 15-observation gate
retained only 34. These are planning measurements, not final Phase 2 results;
the implementation must recompute and report them from its own output.

## 5. Input validation and normalization

The pipeline reads only the ignored Phase 1 processed Parquet. It validates
the eight-column contract, CRS metadata `EPSG:4326`, UTC timestamp metadata,
non-empty `track_id`, finite in-range coordinates, and absence of forbidden
direct-identifier columns. Missing timestamps or coordinates are contract
failures; Phase 2 does not silently discard them.

Input rows are stable-sorted by `track_id`, `base_date_time`, then original
row order. The audit records how many adjacent input pairs were initially out
of order. The sorted result must be monotonic per track.

SOG, COG, and heading are normalized without zero filling:

- non-finite or negative SOG becomes missing;
- non-finite COG or COG outside [0, 360) becomes missing;
- non-finite heading, heading outside [0, 359], and sentinel 511 become
  missing;
- every normalization has a count in the QA result.

Duplicate timestamps remain in stable source order and in the same segment.
They increment `zero_duration_interval_count`. Any rate calculation excludes
their zero-duration edge, preventing division by zero. Exact duplicate removal
remains a Phase 1 responsibility and is not repeated silently.

## 6. Segmentation

Within each sorted track:

1. The first observation starts segment ordinal 1.
2. A positive time gap strictly greater than `segment_gap_seconds` starts a
   new segment.
3. A gap equal to the threshold remains in the current segment.
4. Zero-duration pairs remain in the current segment and are flagged.
5. A negative gap after sorting is an internal consistency error.
6. No coordinates are interpolated and no tracks are joined spatially.

`segment_id` is deterministic and public-safe:
`<track_id>:s<four-digit-ordinal>`. Segment ordinals restart for each track.

One-point and very short segments are retained in the segmented-observation
and segment-summary artifacts. They receive an explicit
`insufficient_duration` or `insufficient_observations` quality status and do
not produce fake distance, turning, or window features.

The segmented observation output contains the Phase 1 columns plus
`segment_id`, `segment_ordinal`, and nullable `preceding_gap_seconds`.

The segment-summary schema is fixed as: `track_id`, `segment_id`,
`segment_ordinal`, `segment_start_utc`, `segment_end_utc`,
`segment_duration_seconds`, `observation_count`, `median_gap_seconds`,
`max_gap_seconds`, `zero_duration_interval_count`, `sog_valid_count`,
`sog_valid_fraction`, `cog_valid_count`, `cog_valid_fraction`,
`heading_valid_count`, `heading_valid_fraction`, `vessel_type`,
`vessel_type_consistent`, and `segment_quality_status`. Vessel type is present
only when all non-null values agree; otherwise it is null and consistency is
false. Segment quality is `insufficient_observations` for fewer than two
observations, `insufficient_duration` for duration below 1,800 seconds, and
`sufficient` otherwise. This status describes feature usability, not behavior.

## 7. Geodesic and angular primitives

All distances use `pyproj.Geod(ellps="WGS84").inv` with longitude/latitude in
degrees and output metres:

- point-to-point distance: WGS84 geodesic distance between consecutive valid
  observations;
- path distance: sum of consecutive point distances in stable chronological
  order;
- displacement: geodesic distance from first to last observation;
- path/displacement ratio: path distance divided by displacement only when
  displacement is at least `minimum_displacement_for_ratio_m`; otherwise null.

No degree value is treated as a linear distance. Calculated speed from
distance/time is intentionally deferred because SOG is already available and
zero-duration/source-spacing cases would add complexity without serving the
MVP.

Signed circular difference is:

```text
((next_degrees - previous_degrees + 180) mod 360) - 180
```

Absolute turning uses the absolute value. Thus 359° to 1° is 2°, not 358°.
Exactly 180° resolves deterministically to -180° before taking the absolute
value. COG-change pairs require valid COG, positive elapsed time, and SOG at
both endpoints at or above `course_min_speed_knots`. Heading/COG differences
use the same circular logic and the same speed gate. Low-speed COG remains
documented as potentially unstable.

## 8. Window generation and sufficiency

Windows are time-based, segment-local, and half-open:
`[window_start_utc, window_end_utc)`. The first window starts at the segment's
first observation. Later windows advance by `window_stride_seconds`. A window
is emitted only when its nominal end is not later than the segment end. This
prevents partial trailing windows and guarantees that no window crosses a
track, segment, or large gap boundary.

`window_id` is `<segment_id>:w<four-digit-ordinal>`. The window table records
nominal start/end, first/last observed timestamps, observation count, observed
duration, median and maximum gap, zero-duration pair count, field-validity
counts/fractions, and `window_quality_status`.

The exact metadata columns are: `track_id`, `segment_id`, `window_id`,
`window_ordinal`, `window_start_utc`, `window_end_utc`,
`first_observation_utc`, `last_observation_utc`, `observation_count`,
`observed_duration_seconds`, `median_gap_seconds`, `max_gap_seconds`,
`zero_duration_interval_count`, `sog_valid_count`, `sog_valid_fraction`,
`cog_valid_count`, `cog_valid_fraction`, `heading_cog_paired_count`,
`heading_cog_paired_fraction`, `eligible_course_pair_count`, `vessel_type`,
`vessel_type_consistent`, and `window_quality_status`. The ten feature columns
follow these metadata columns. Private observation membership is never written.

A window is generally feature-eligible when it has at least 10 observations,
at least 1,200 seconds of observed span, no negative interval, and no contract
failure. Feature families add their own coverage requirements:

- SOG features require at least 80% valid SOG;
- course features require at least two eligible course-change pairs and at
  least 80% valid COG;
- heading/COG features require at least 80% valid paired heading and COG;
- distance features require at least two valid coordinates;
- path/displacement ratio additionally requires at least 50 metres of
  displacement.

All ten movement features remain null when the general window sufficiency gate
fails. For a generally sufficient window, only the feature family whose input
gate fails remains null. Values are never replaced with zero. Quality metadata
is not behavioral evidence, and Phase 3 must not treat a low-quality flag as
an anomaly signal without a separately reviewed rule.

Window quality status is `insufficient_observations` when count is below 10,
otherwise `insufficient_span` when observed span is below 1,200 seconds, and
otherwise `sufficient`. This priority makes the result deterministic when more
than one gate fails. As with segments, vessel type is emitted only when all
non-null values agree.

## 9. Feature contract

The MVP exposes ten interpretable movement features. Counts, durations,
coverage fractions, and quality flags are metadata and are not included in
this count.

| Feature | Unit | Definition | Missing behavior |
|---|---|---|---|
| `sog_median_knots` | knots | median valid SOG | null below SOG coverage gate |
| `sog_p95_knots` | knots | 95th percentile valid SOG | null below SOG coverage gate |
| `low_speed_fraction` | fraction | valid-SOG observations below configured threshold / valid-SOG observations | null below SOG coverage gate |
| `low_speed_duration_seconds` | seconds | sum of positive interval durations whose two endpoint SOG values are below threshold | null below SOG coverage gate |
| `path_distance_m` | metres | sum of consecutive WGS84 geodesic distances | null with fewer than two valid coordinates |
| `displacement_m` | metres | WGS84 geodesic start-to-end distance | null with fewer than two valid coordinates |
| `path_displacement_ratio` | unitless | path distance / displacement | null below minimum displacement |
| `course_change_abs_sum_deg` | degrees | sum of eligible absolute circular COG changes | null below course gate |
| `course_change_abs_p95_deg` | degrees | p95 eligible absolute circular COG change | null below course gate |
| `heading_cog_abs_median_deg` | degrees | median eligible absolute circular heading/COG difference | null below heading/COG gate |

These neutral components support later transparent rules such as dwell or
constrained-movement patterns without embedding labels like hostile, illegal,
or suspicious. A composite dwell score is deferred because it would introduce
an uncalibrated weighting decision.

## 10. Output artifacts and schemas

Real generated tables remain under ignored
`data/processed/features/`:

- `noaa_ais_2024-01-01_sf_bay_segmented.parquet`: public-safe observations
  with segment assignment;
- `noaa_ais_2024-01-01_sf_bay_segments.parquet`: one row per segment with
  temporal and quality summary;
- `noaa_ais_2024-01-01_sf_bay_windows.parquet`: one row per feature window,
  with keys, quality metadata, and the ten features.

All timestamps are UTC and all distance units are metres. Parquet metadata
records schema version, CRS, timezone, source manifest path and digest,
configuration path and digest, and generator version.

Commit aggregate-only metadata at
`data/manifests/noaa_ais_2024-01-01_sf_bay_trajectory_features.json`. It must
not contain individual `track_id`, `segment_id`, or `window_id` values.
Commit `docs/trajectory-feature-spec.md` as the concise data dictionary and
`docs/trajectory-feature-report.md` as the measured QA report. Tests use only
small in-memory or committed synthetic fixtures. No real feature table is
committed.

All writers preflight every destination before computing or writing, use a
`.partial` file followed by atomic replacement, reject overwrite unless
`--force` is explicit, and apply the forbidden-identifier schema guard.

## 11. Real-data QA report

The explicit local smoke workflow reads the existing Phase 1 processed
artifact and measures:

- segment count, segments per track, duration distribution, and observations
  per segment;
- window count, windows per track, windows per segment, and sufficiency status;
- feature and input-field missingness;
- maximum-gap, SOG, course-change, path-distance, displacement, and
  path/displacement-ratio distributions;
- low-speed fraction and duration distributions;
- counts of invalid/sentinel normalizations and zero-duration pairs;
- artifact sizes, row counts, and SHA-256 digests.

Numeric distributions use count, missing count/rate, minimum, p25, median,
p75, p95, and maximum. The report describes extremes only as distributional
observations; it does not call them anomalies. Aggregate reports and manifests
must not list individual IDs.

## 12. Synthetic verification cases

Tests use manually calculable trajectories:

- a straight equatorial path with ratio near 1 and near-zero turning;
- 359° to 1° COG yielding approximately 2°;
- stationary/low-speed dwell with low displacement and high low-speed
  duration;
- a loop with path distance materially above displacement and larger
  cumulative turning;
- a gap over 600 seconds producing a new segment and no crossing window;
- a gap exactly 600 seconds remaining in one segment;
- missing COG producing null course features, never zero;
- heading 511 becoming missing and reducing paired coverage;
- duplicate timestamps retained deterministically without division by zero;
- out-of-order input becoming stable chronological order with an audit count;
- a one-point and a short segment retained in summaries but producing no
  full-duration feature window;
- direct identifier columns causing a fail-closed privacy error.

No normal test downloads NOAA data. Real-data validation remains an explicit
smoke command.

## 13. Leakage boundary and Phase 3 gate

Every Phase 2 feature is a pure deterministic function of observations inside
one segment/window plus committed configuration. There is no learned route,
density, percentile, corridor, scaling, or imputation reference.

Future background-derived features must live behind a separate interface that
is fit on training data only. Because windows overlap, Phase 3 must split by
independent date/track groups before fitting or calibration; random window-row
splits are forbidden because they leak shared observations.

The Phase 2 report must end with exactly one state:

- `A. CURRENT DATA SUFFICIENT FOR INITIAL BASELINE MODEL EXPERIMENT`, or
- `B. EXPAND DATA BEFORE MODELING`.

The assessment considers temporal partitions, number and concentration of
tracks and eligible windows, feature missingness, and coverage stability. The
current one-day dataset cannot provide independent train/calibration/test date
partitions, so the expected state is B unless the modeling goal is explicitly
reduced to a non-evaluative code experiment. The report must use its measured
Phase 2 counts to recommend the smallest next data-validation tranche. January
2 and January 3 may be evaluated as the minimum two additional temporal
partitions, but they are not automatically sufficient and must not be
downloaded without separate approval.

## 14. Deferred work

Phase 2 excludes anomaly/risk scores, Isolation Forest, LOF, One-Class SVM,
learned confidence, corridor or historical-route deviation, inter-vessel
proximity, density references, graph/deep/Transformer features, hostile-intent
classification, APIs, frontend/map integration, SQLite workflows, #10
logistics, cloud deployment, remotes, and pushes.

## 15. Success criteria

Phase 2 implementation is complete only when:

1. input and privacy contracts fail closed;
2. segmentation is deterministic and uses the configurable strict `> 600 s`
   rule;
3. windows are time-based and cannot cross track or segment boundaries;
4. WGS84 geodesic and circular-angle tests pass;
5. missing, sentinel, duplicate-time, one-point, and short-segment cases are
   explicit;
6. the ten feature definitions and quality metadata match the data dictionary;
7. all synthetic expected-value tests pass without network access;
8. the explicit 5,581-row/15-track real smoke workflow completes and produces
   measured aggregate documentation;
9. generated real feature tables, environments, secrets, databases, and large
   artifacts remain uncommitted;
10. no direct source identifier appears in publishable/debug outputs;
11. no anomaly, model, UI, API, persistence, logistics, deployment, remote, or
    push scope is introduced; and
12. the measured report states the Phase 3 data gate without starting Phase 3.

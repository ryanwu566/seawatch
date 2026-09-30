# SeaWatch Phase 2 Trajectory Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the validated Phase 1 NOAA AIS observations into deterministic segments, time-based windows, ten interpretable movement features, and explicit quality metadata without implementing anomaly detection.

**Architecture:** Add focused trajectory modules for contracts, geodesic/angular primitives, segmentation, windowing, and feature aggregation; keep orchestration and artifact writing in a deterministic CLI. Real feature tables remain ignored, while configuration, tests, aggregate manifests, and measured documentation are committed.

**Tech Stack:** Python 3.12.7, pandas 3.0.6, NumPy 2.5.3, PyArrow 25.0.1, pyproj 3.8.0, pytest 9.1.1.

**Spec:** `docs/superpowers/specs/2026-09-29-trajectory-features-design.md`

## Global Constraints

- Begin from Phase 1 commit `5823b14b4fe1c6aada2f468149d98fd4dc64ef3c` on a new local branch `feat/trajectory-features`.
- Use only `C:\Projects\seawatch\.venv\Scripts\python.exe`; do not alter global Python.
- Use the existing ignored Phase 1 processed Parquet; do not download NOAA data or another date.
- Treat `track_id`, `base_date_time`, `longitude`, `latitude`, `sog`, `cog`, `heading`, and `vessel_type` as the authoritative Phase 1 input contract.
- Fail if a publishable input/output contains `mmsi`, `source_vessel_id`, `source_id`, `vessel_name`, `imo`, or `call_sign`, case-insensitively.
- Segment only on a time gap strictly greater than 600 seconds; do not interpolate or join tracks by proximity.
- Use WGS84 geodesic distances in metres and circular angle differences in degrees; never treat EPSG:4326 degrees as metres.
- Use 1,800-second windows with 300-second stride, anchored to each segment's first observation, and never cross track or segment boundaries.
- Generated real feature Parquet files remain ignored under `data/processed/features/`.
- No anomaly score, model, learned reference, API, frontend, database, #10 logistics, deployment, remote, or push is permitted.
- Normal unit/integration tests must not use the network; real-data validation is an explicit smoke workflow.
- Measurements produced during implementation override the planning estimates in the design.

## Review Focus

- A gap exactly equal to 600 seconds must not split, while 600.001 seconds must split; Task 3 pins both boundary cases.
- Half-open overlapping windows can duplicate boundary observations or cross segments if indexed incorrectly; Task 4 pins membership and boundary isolation.
- Missing/sentinel navigation values can silently become zero or contaminate circular aggregates; Tasks 1 and 5 pin null preservation and feature-family gates.
- Near-zero displacement can create infinite path/displacement ratios; Tasks 2 and 5 pin the 50-metre null gate and finite outputs.
- Direct identifiers can leak through extra columns, metadata, manifests, or reports even if feature columns are safe; Tasks 1, 6, and 8 pin schema and serialized-output privacy scans.

---

## Execution preflight

- [ ] Confirm the current checkout is clean and exactly at the approved Phase 1 base:

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
```

Expected: empty status, `feat/data-gis-foundation`, SHA
`5823b14b4fe1c6aada2f468149d98fd4dc64ef3c`, and no remote.

- [ ] Create the local implementation branch without changing the base branch:

```powershell
git switch -c feat/trajectory-features 5823b14b4fe1c6aada2f468149d98fd4dc64ef3c
```

- [ ] Verify the approved interpreter and baseline tests:

```powershell
& '.\.venv\Scripts\python.exe' --version
& '.\.venv\Scripts\python.exe' -m pytest -q
```

Expected: Python 3.12.7 and the Phase 1 suite passing before any Phase 2 edit.

### Task 1: Configuration, observation contract, and privacy guard

**Files:**
- Create: `config/trajectory_features_v1.json`
- Create: `apps/api/seawatch/trajectories/contracts.py`
- Create: `tests/unit/test_trajectory_contracts.py`

**Interfaces:**
- Produces: `FeatureConfig` with the nine typed settings listed in Step 1.
- Produces: `ValidationStats(input_rows: int, input_out_of_order_pairs: int, invalid_sog_rows: int, invalid_cog_rows: int, invalid_heading_rows: int)`.
- Produces: `ValidatedObservations(frame: pd.DataFrame, stats: ValidationStats)`.
- Produces: `load_feature_config(path: Path) -> FeatureConfig`.
- Produces: `validate_observations(frame: pd.DataFrame) -> ValidatedObservations`.
- Produces: `assert_public_feature_schema(columns: Iterable[str]) -> None`.
- Consumes: Phase 1 public observation columns only.

- [ ] **Step 1: Write failing configuration tests**

Add tests asserting the committed JSON loads to these exact values:

```python
assert config.segment_gap_seconds == 600.0
assert config.window_duration_seconds == 1800.0
assert config.window_stride_seconds == 300.0
assert config.minimum_window_observations == 10
assert config.minimum_observed_span_seconds == 1200.0
assert config.minimum_valid_fraction == 0.80
assert config.low_speed_threshold_knots == 3.0
assert config.course_min_speed_knots == 1.0
assert config.minimum_displacement_for_ratio_m == 50.0
```

Also parametrize invalid configurations: non-positive duration/stride/gap,
stride greater than duration, fractions outside [0, 1], non-positive minimum
observation count, and negative thresholds. Each must raise `ValueError` with
the setting name.

- [ ] **Step 2: Run the configuration tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_trajectory_contracts.py -k config -v
```

Expected: FAIL because the module/configuration does not exist.

- [ ] **Step 3: Implement the immutable configuration contract**

Define the nine fields above in `FeatureConfig`, validate them in
`__post_init__`, and parse the JSON with exact-key rejection so misspelled or
unknown settings fail closed.

- [ ] **Step 4: Run configuration tests and verify pass**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Write failing observation-validation tests**

Cover:

```python
assert result.frame.columns.tolist() == PHASE1_COLUMNS
assert result.frame.groupby("track_id")["base_date_time"].apply(
    lambda values: values.is_monotonic_increasing
).all()
assert result.stats.input_out_of_order_pairs == 1
assert pd.isna(result.frame.loc[heading_511_row, "heading"])
assert pd.isna(result.frame.loc[invalid_cog_row, "cog"])
assert pd.isna(result.frame.loc[negative_sog_row, "sog"])
```

Assert missing timestamp, invalid/missing coordinates, empty `track_id`, and
missing required columns raise `ValueError`. Parametrize every forbidden
identifier with mixed casing and assert the privacy guard rejects it.

- [ ] **Step 6: Run the validation tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_trajectory_contracts.py -k 'validation or privacy' -v
```

Expected: FAIL because validation is not implemented.

- [ ] **Step 7: Implement validation and normalization**

Stable-sort by `track_id`, timestamp, and original order. Preserve nullable
SOG/COG/heading values; replace invalid values with `NaN` and record counts.
Do not remove duplicate timestamps. Return a normalized eight-column copy and
immutable stats.

- [ ] **Step 8: Run Task 1 tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_trajectory_contracts.py -v
```

Expected: all Task 1 tests pass.

- [ ] **Step 9: Commit Task 1**

```powershell
git add config/trajectory_features_v1.json apps/api/seawatch/trajectories/contracts.py tests/unit/test_trajectory_contracts.py
git commit -m "feat: define trajectory feature contracts"
```

### Task 2: WGS84 geodesic and circular-angle primitives

**Files:**
- Create: `apps/api/seawatch/trajectories/geodesy.py`
- Create: `tests/unit/test_geodesy.py`

**Interfaces:**
- Produces: `PathMetrics(path_distance_m: float | None, displacement_m: float | None, path_displacement_ratio: float | None)`.
- Produces: `geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float`.
- Produces: `consecutive_geodesic_distances_m(longitude: pd.Series, latitude: pd.Series) -> pd.Series`.
- Produces: `circular_difference_degrees(start: object, end: object) -> float`.
- Produces: `path_metrics(longitude: pd.Series, latitude: pd.Series, *, minimum_displacement_m: float) -> PathMetrics`.

- [ ] **Step 1: Write failing geodesic tests**

Use manually checkable cases:

```python
assert geodesic_distance_m(0.0, 0.0, 0.0, 0.0) == 0.0
assert geodesic_distance_m(0.0, 0.0, 0.01, 0.0) == pytest.approx(1113.1949, rel=1e-5)
assert circular_difference_degrees(359.0, 1.0) == pytest.approx(2.0)
assert circular_difference_degrees(1.0, 359.0) == pytest.approx(-2.0)
assert abs(circular_difference_degrees(0.0, 180.0)) == 180.0
```

Assert a straight three-point path has path/displacement ratio approximately
1. Assert a return-to-start path has positive path distance, zero displacement,
and a null ratio. Assert a displacement below 50 metres also gives a null
ratio, never infinity.

- [ ] **Step 2: Run geodesy tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_geodesy.py -v
```

Expected: FAIL because `geodesy.py` does not exist.

- [ ] **Step 3: Implement the primitives with `pyproj.Geod(ellps="WGS84")`**

Return metres as non-negative floats. Preserve missing angles as `NaN`. The
path helper returns null metrics for fewer than two valid coordinates and
applies the configured displacement gate to the ratio.

- [ ] **Step 4: Run Task 2 tests**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add apps/api/seawatch/trajectories/geodesy.py tests/unit/test_geodesy.py
git commit -m "feat: add geodesic trajectory primitives"
```

### Task 3: Deterministic trajectory segmentation

**Files:**
- Create: `apps/api/seawatch/trajectories/segmentation.py`
- Create: `tests/unit/test_segmentation.py`

**Interfaces:**
- Consumes: normalized observations from `validate_observations` and `FeatureConfig`.
- Produces: `SegmentationResult(observations: pd.DataFrame, segments: pd.DataFrame)`.
- Produces: `segment_observations(frame: pd.DataFrame, config: FeatureConfig) -> SegmentationResult`.
- Segment observation columns add `segment_id`, `segment_ordinal`, and `preceding_gap_seconds`.

- [ ] **Step 1: Write failing segment-boundary tests**

Construct two tracks with out-of-order source rows and gaps of 0, 600, and
600.001 seconds. Assert stable chronological ordering, the exact 600-second
pair remains in one segment, the 600.001-second pair splits, and segment IDs
are exactly `track-a:s0001`, `track-a:s0002`, and `track-b:s0001`.

- [ ] **Step 2: Write failing edge-case summary tests**

Assert duplicate timestamps remain present, increment
`zero_duration_interval_count`, and never create a segment. Assert a one-point
track produces one segment row with observation count 1, duration 0, and
quality status `insufficient_observations`. Assert no output segment contains
more than one `track_id`.

- [ ] **Step 3: Run segmentation tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_segmentation.py -v
```

Expected: FAIL because segmentation is not implemented.

- [ ] **Step 4: Implement strict-gap segmentation and summaries**

Use per-track timestamp difference and cumulative split flags. A negative gap
after validated sorting raises `RuntimeError`. Build segment summaries with
start/end UTC, duration, observation count, median/max positive gap,
zero-duration count, field-validity counts/fractions, consistent-or-null vessel
type, and the exact columns/status priority specified in the design. Do not
interpolate.

- [ ] **Step 5: Run Task 3 tests**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add apps/api/seawatch/trajectories/segmentation.py tests/unit/test_segmentation.py
git commit -m "feat: segment vessel trajectories by time gap"
```

### Task 4: Segment-local time windows

**Files:**
- Create: `apps/api/seawatch/trajectories/windowing.py`
- Create: `tests/unit/test_windowing.py`

**Interfaces:**
- Consumes: `SegmentationResult.observations`, `SegmentationResult.segments`, and `FeatureConfig`.
- Produces: `build_feature_windows(observations: pd.DataFrame, segments: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame`.
- Window rows contain the exact metadata columns from design section 8 plus a private `_observation_positions` tuple used only by Task 5.

- [ ] **Step 1: Write failing window cadence and membership tests**

For one segment from 00:02 through 01:02, assert starts at 00:02, 00:07,
00:12, and so on; each nominal duration is 1,800 seconds. Assert membership is
half-open, so an observation exactly at a window end is excluded from that
window and may enter the next.

- [ ] **Step 2: Write failing isolation and sufficiency tests**

Assert windows never contain observations from another `track_id` or
`segment_id`, no window spans a >600-second split, and segments shorter than
30 minutes emit no windows. Assert 10 observations spanning 1,200 seconds are
`sufficient`, while 9 observations or a 1,199-second span receive the explicit
insufficiency status. Include a zero-duration pair and assert it is counted
without a division operation.

- [ ] **Step 3: Run window tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_windowing.py -v
```

Expected: FAIL because window generation is not implemented.

- [ ] **Step 4: Implement deterministic full-duration windows**

Generate starts from each segment's first timestamp by the configured stride
while `start + duration <= segment_end`. Assign deterministic window ordinals
and IDs. Apply quality-status priority `insufficient_observations`, then
`insufficient_span`, then `sufficient`. Emit vessel type only when all non-null
values agree. Store membership in `_observation_positions`, preserving stable
row order; Task 5 must remove it from the public output.

- [ ] **Step 5: Run Task 4 tests**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add apps/api/seawatch/trajectories/windowing.py tests/unit/test_windowing.py
git commit -m "feat: add segment-local trajectory windows"
```

### Task 5: Interpretable feature aggregation

**Files:**
- Create: `apps/api/seawatch/trajectories/features.py`
- Create: `tests/unit/test_trajectory_features.py`

**Interfaces:**
- Consumes: segmented observations, private window membership, `FeatureConfig`, and Task 2 primitives.
- Produces: `compute_window_features(observations: pd.DataFrame, windows: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame`.
- Produces the exact metadata schema from design section 8 followed by the ten feature columns from section 9; `_observation_positions` is absent.

- [ ] **Step 1: Write failing straight-path and circular-course tests**

For a straight, constant-speed synthetic window, assert:

```python
assert row["path_displacement_ratio"] == pytest.approx(1.0, rel=1e-4)
assert row["course_change_abs_sum_deg"] == pytest.approx(0.0)
assert row["sog_median_knots"] == pytest.approx(expected_median)
```

For COG 359° to 1°, assert the sum and p95 use approximately 2°, not 358°.

- [ ] **Step 2: Write failing dwell and loop tests**

Use regularly spaced points with known SOG. Assert stationary/low-speed input
has high `low_speed_fraction`, the expected interval-summed
`low_speed_duration_seconds`, and displacement near zero. Assert a loop has
path distance materially greater than displacement and a null ratio when the
displacement is below 50 metres.

- [ ] **Step 3: Write failing missingness and speed-gate tests**

Assert missing COG yields null course features, heading 511 from Task 1 yields
null heading/COG output when paired coverage is below 80%, and no missing
feature is zero-filled. Assert COG changes whose endpoints are below 1 knot do
not enter course aggregates. Assert an otherwise computable nine-observation
window has all ten movement features null because the general sufficiency gate
fails. Assert duplicate timestamps cannot create an infinite or divide-by-zero
result.

- [ ] **Step 4: Run feature tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_trajectory_features.py -v
```

Expected: FAIL because aggregation is not implemented.

- [ ] **Step 5: Implement the ten features and family-specific gates**

Use pandas/NumPy aggregation and Task 2 primitives. Quantiles use pandas'
deterministic default linear interpolation. Keep quality metadata separate
from the ten movement features and retain null values when gates fail. Remove
private observation-membership data before returning the public frame.

- [ ] **Step 6: Assert the exact public window schema**

Add a test that compares the returned column list to the committed contract,
runs `assert_public_feature_schema`, and verifies every numeric feature is
finite or null.

- [ ] **Step 7: Run Task 5 tests**

Run the Step 4 command. Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```powershell
git add apps/api/seawatch/trajectories/features.py tests/unit/test_trajectory_features.py
git commit -m "feat: compute interpretable trajectory features"
```

### Task 6: Artifact I/O and deterministic CLI

**Files:**
- Create: `apps/api/seawatch/trajectories/feature_io.py`
- Create: `scripts/prepare_trajectory_features.py`
- Create: `tests/unit/test_feature_io.py`
- Create: `tests/integration/test_trajectory_feature_cli.py`

**Interfaces:**
- Produces: `read_phase1_parquet(path: Path) -> pd.DataFrame`, validating columns plus `seawatch_crs=EPSG:4326` and `seawatch_timezone=UTC` metadata.
- Produces: `write_feature_parquet(frame: pd.DataFrame, path: Path, metadata: Mapping[str, str], *, overwrite: bool = False) -> ArtifactRecord`.
- Produces: `preflight_feature_outputs(paths: Iterable[Path], *, overwrite: bool) -> None`.
- Consumes: the existing generic `ArtifactRecord` from `apps.api.seawatch.trajectories.preprocess`.
- CLI orchestrates validation, segmentation, windows, features, three Parquet writes, aggregate manifest, and report.

- [ ] **Step 1: Write failing Parquet contract and atomic-write tests**

Assert the reader rejects missing CRS/timezone metadata and unexpected input
columns. Assert a successful write records schema/config/source provenance
metadata, preserves UTC timestamps, and returns measured size/row count/hash.
Assert existing destinations and `.partial` files fail unless overwrite is
explicit.

- [ ] **Step 2: Run I/O tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_feature_io.py -v
```

Expected: FAIL because feature I/O does not exist.

- [ ] **Step 3: Implement guarded Parquet reading and writing**

Call the public schema guard for every output. Write to sibling `.partial`
files and replace only after PyArrow closes successfully. Store Phase 2 schema
version, CRS, timezone, source artifact SHA-256, source manifest SHA-256,
configuration SHA-256, and generator version in every output schema.

- [ ] **Step 4: Write a failing synthetic CLI integration test**

Create a tiny Phase 1-contract Parquet entirely under `tmp_path`, run the CLI
through its importable `main`, and assert all three output tables are created,
window rows do not cross segments, aggregate manifest/report values equal the
tables, and serialized public outputs contain none of the forbidden names or
fixture source identifiers.

Add collision tests proving an existing final destination is detected before
any other output is written. Add `--help` and invalid-config tests. Do not use
the network.

- [ ] **Step 5: Run the CLI test and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_trajectory_feature_cli.py -v
```

Expected: FAIL because the CLI does not exist.

- [ ] **Step 6: Implement `scripts/prepare_trajectory_features.py`**

Defaults:

```text
input: data/processed/noaa_ais_2024-01-01_sf_bay.parquet
config: config/trajectory_features_v1.json
segmented: data/processed/features/noaa_ais_2024-01-01_sf_bay_segmented.parquet
segments: data/processed/features/noaa_ais_2024-01-01_sf_bay_segments.parquet
windows: data/processed/features/noaa_ais_2024-01-01_sf_bay_windows.parquet
manifest: data/manifests/noaa_ais_2024-01-01_sf_bay_trajectory_features.json
report: docs/trajectory-feature-report.md
```

Preflight every output before reading the source. Require `--force` to
regenerate committed measured manifest/report files. Keep business logic in
the imported modules rather than the CLI.

- [ ] **Step 7: Run Task 6 tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_feature_io.py tests/integration/test_trajectory_feature_cli.py -v
```

Expected: PASS with no network access.

- [ ] **Step 8: Commit Task 6**

```powershell
git add apps/api/seawatch/trajectories/feature_io.py scripts/prepare_trajectory_features.py tests/unit/test_feature_io.py tests/integration/test_trajectory_feature_cli.py
git commit -m "feat: add trajectory feature pipeline"
```

### Task 7: Synthetic end-to-end contract and user-facing data dictionary

**Files:**
- Create: `tests/integration/test_trajectory_feature_pipeline.py`
- Create: `docs/trajectory-feature-spec.md`
- Modify: `README.md`

**Interfaces:**
- Consumes all Task 1-6 public interfaces.
- Produces a concise committed field dictionary and reproducible local command.

- [ ] **Step 1: Write the failing end-to-end synthetic test**

Combine straight, wraparound, dwell, loop, missing-COG, gap, duplicate-time,
out-of-order, and one-point tracks in one fixture. Assert the expected segment
counts, no cross-boundary windows, all ten feature columns, null behavior,
stable rerun equality, UTC timestamps, metres/knots/degrees/seconds units in
metadata, and absence of direct identifiers.

- [ ] **Step 2: Run the integration test and verify its initial result**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_trajectory_feature_pipeline.py -v
```

Expected before any required wiring fix: FAIL at the first missing integration
contract. If it unexpectedly passes, retain the test and proceed without
inventing a code change.

- [ ] **Step 3: Make only the minimal integration fixes**

Adjust module wiring or output ordering; do not change feature definitions to
make synthetic expectations easier.

- [ ] **Step 4: Write `docs/trajectory-feature-spec.md`**

Document input/output schemas, every configuration setting, segmentation and
window rules, the ten-feature data dictionary with units and null behavior,
quality statuses, sentinel treatment, privacy boundary, leakage boundary, and
deferred features. Use synthetic names such as `track-demo`, never real IDs.

- [ ] **Step 5: Add setup and explicit smoke instructions to README**

Document a PowerShell command using the project `.venv`, the existing local
Phase 1 artifact, and `--force`. State that normal tests are offline and the
real outputs are ignored.

- [ ] **Step 6: Run the complete synthetic suite**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
```

Expected: all Phase 1 and Phase 2 tests pass.

- [ ] **Step 7: Commit Task 7**

```powershell
git add tests/integration/test_trajectory_feature_pipeline.py docs/trajectory-feature-spec.md README.md
git commit -m "docs: define trajectory feature data contract"
```

### Task 8: Explicit real-data smoke analysis and measured report

**Files:**
- Create: `data/manifests/noaa_ais_2024-01-01_sf_bay_trajectory_features.json`
- Create: `docs/trajectory-feature-report.md`
- Modify only if measurements require correction: `docs/trajectory-feature-spec.md`

**Interfaces:**
- Consumes the ignored Phase 1 Parquet and committed Phase 1 manifest.
- Produces ignored real feature Parquets plus aggregate-only committed metadata.

- [ ] **Step 1: Reconfirm the Phase 1 local source instead of downloading**

```powershell
Get-Item data/processed/noaa_ais_2024-01-01_sf_bay.parquet | Select-Object Length
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_smoke_pipeline.py -q
```

Expected: the local artifact exists and Phase 1 integration tests pass. Stop
and report if it is missing or invalid; do not download NOAA data.

- [ ] **Step 2: Run the explicit Phase 2 smoke workflow**

```powershell
& '.\.venv\Scripts\python.exe' scripts/prepare_trajectory_features.py --force
```

Expected: three ignored Parquet outputs plus the aggregate manifest and report.
Do not hard-code the planning estimates of 15 segments, 3,216 windows, or
2,829 sufficient windows; record the independently measured results.

- [ ] **Step 3: Audit real outputs read-only**

Verify source and output hashes, row counts, exact schemas, UTC ordering,
segment and window boundaries, no window crossing a >600-second gap, feature
finiteness/nullability, configuration provenance, aggregate report/manifest
agreement, and absence of direct source identifiers or individual IDs from
the report and manifest.

- [ ] **Step 4: Complete measured distributions and the Phase 3 gate**

The report must include segment/window counts by aggregate distribution,
feature missingness, and min/p25/median/p75/p95/max distributions for max gap,
SOG, turning, path, displacement, ratio, and low-speed metrics. It must not
label extremes as anomalies.

End with exactly A or B from the design. Because only one date exists, B is
expected. Use measured track/window concentration and missingness to recommend
the smallest next approved data-validation tranche; do not download it.

- [ ] **Step 5: Confirm ignored artifact behavior and privacy**

```powershell
git check-ignore data/processed/features/*.parquet
git status --short --ignored
rg -n -i 'mmsi|source_vessel_id|source_id|vessel_name|call_sign|"imo"' docs/trajectory-feature-report.md data/manifests/noaa_ais_2024-01-01_sf_bay_trajectory_features.json
```

Expected: real Parquets are ignored and the privacy scan returns no matches.

- [ ] **Step 6: Commit only measured aggregate documents**

```powershell
git add data/manifests/noaa_ais_2024-01-01_sf_bay_trajectory_features.json docs/trajectory-feature-report.md
git commit -m "docs: record trajectory feature QA"
```

### Task 9: Final verification and scope audit

**Files:**
- Modify only files needed to correct a verified failure.

**Interfaces:**
- Verifies the complete Phase 2 branch; introduces no new behavior.

- [ ] **Step 1: Run the complete automated suite and compilation**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m compileall -q apps scripts
& '.\.venv\Scripts\python.exe' scripts/prepare_trajectory_features.py --help
```

Expected: all tests pass and both commands exit 0.

- [ ] **Step 2: Repeat the explicit real-artifact audit**

Recompute results from the existing Phase 1 input and compare every committed
aggregate value to the generated tables. This command remains separate from
pytest and must perform no network access.

- [ ] **Step 3: Audit scope and forbidden content**

Search changed files for anomaly/model scoring, Isolation Forest, LOF,
One-Class SVM, API routes, frontend/MapLibre, SQLite workflows, #10 logistics,
cloud deployment, direct identifiers, secrets, and binary/model artifacts.
Documentation may mention exclusions; no implementation may exist.

- [ ] **Step 4: Explicitly inspect Git state before finalizing**

```powershell
git status --short
git diff --check
git diff --stat 5823b14..HEAD
git diff 5823b14..HEAD
git ls-files
```

Verify no raw NOAA file, Phase 1/2 generated Parquet, generated preview,
`.venv`, `.env`, secret, cache, database, or model artifact is tracked.

- [ ] **Step 5: Stage any final justified correction explicitly and audit it**

If a correction was needed, stage each exact corrected path individually and
then run:

```powershell
git diff --cached --stat
git diff --cached --name-only
git diff --cached --check
```

Inspect staged blob sizes. If no correction is needed, leave the index empty
and do not create an empty commit.

- [ ] **Step 6: Commit a final correction only if Step 5 staged one**

```powershell
git commit -m "fix: finalize trajectory feature foundation"
```

- [ ] **Step 7: Record final evidence**

```powershell
git status --short
git log --oneline 5823b14..HEAD
git remote -v
```

Expected: clean working tree, only reviewed Phase 2 commits, and no remote.
Stop after reporting Phase 2 results and the A/B data gate. Do not start Phase
3, download more dates, merge, push, or add a remote.

# NOAA AIS Data Foundation Design

## Status

Approved in-chat design recorded for implementation planning. This document covers Phase 1 only and does not authorize implementation until the accompanying plan is approved.

## Purpose

Build a reproducible, provenance-preserving data foundation for SeaWatch from one day of the official NOAA/MarineCadastre 2024 AIS GeoParquet product. The result will support later trajectory research while making no anomaly, identity, intent, or threat claims.

The source date is 2024-01-01. The engineering smoke-study area is the San Francisco Bay bounding box `[-122.55, 37.68, -122.25, 37.90]`. This area is a development choice, not an official challenge region and not evidence of suitability for Taiwan.

## Scope

Phase 1 includes:

- deterministic acquisition of the official daily source file;
- source provenance, hash, size, and download-time capture;
- actual Parquet and GeoParquet schema inspection;
- coordinate, timestamp, duplicate, null, ordering, and time-gap QA;
- SF Bay bounding-box filtering;
- cargo vessel filtering for AIS type codes 70 through 79 when sufficient records exist;
- deterministic privacy-conscious surrogate identifiers;
- a small chronological processed Parquet dataset and smaller GeoJSON preview;
- a machine-readable manifest, provenance document, measured QA report, and tests.

Phase 1 explicitly excludes anomaly detection, ML, behavioral rules, interpolation, application APIs, frontend work, databases, live AIS, authentication, logistics challenge work, deployment, and remote Git operations.

## Source and Trust Boundaries

The only permitted real source is:

`https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-01.parquet`

Source documentation is:

`https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/data/ais-broadcast-points-2024-readme.md`

The implementation must verify the source documentation and observed license before recording it. If the official file or documentation cannot be obtained, the workflow stops with a clear failure; it must not substitute a mirror or proprietary source.

The downloaded Parquet file is authoritative for physical schema, row count, timestamp representation, geometry encoding, CRS metadata, and observable nullability. Prior field-name expectations are hints only. Column resolution must be explicit and fail with a useful message when required semantic fields cannot be identified.

## Environment and Dependencies

The project-local `.venv` will be created specifically with `C:\wu\python.exe`, observed as Python 3.12.7. No global Python installation or global package set will be changed.

The intended runtime dependencies are:

- `pandas` for tabular validation, grouping, sorting, and summaries;
- `numpy` for numeric validity checks and summary calculations;
- `pyarrow` for Parquet metadata, GeoParquet metadata, filtered/batched reads, and output;
- `shapely` for verified WKB point decoding where Arrow-native coordinate columns are unavailable;
- `pyproj` for CRS interpretation or transformation only if the source metadata requires it;
- `pytest` for unit and integration tests.

GeoPandas, DuckDB, and ML packages are not required. `requirements.txt` will contain the exact successfully installed and imported versions, recorded only after environment verification.

## Repository Structure

The implementation will add these focused units:

```text
apps/api/seawatch/
  __init__.py
  adapters/
    __init__.py
    noaa_ais.py          # download, hashing, and source metadata inspection
  trajectories/
    __init__.py
    preprocess.py        # normalization, validation, filtering, IDs, selection, QA
scripts/
  download_noaa_ais.py   # deterministic acquisition CLI
  inspect_noaa_ais.py    # explicit source-inspection CLI
  prepare_smoke_dataset.py
tests/
  unit/
  integration/
docs/
  data-provenance.md
  data-foundation-report.md
data/manifests/
  noaa_ais_2024-01-01_sf_bay.json
```

Only tiny synthetic test fixtures may be committed. `data/raw/` and `data/processed/` remain ignored except for their existing `.gitkeep` files. Real downloaded and generated Parquet/GeoJSON artifacts remain local and uncommitted.

## Components and Interfaces

### NOAA adapter

`apps.api.seawatch.adapters.noaa_ais` owns external-source concerns:

- stream an HTTP response to a temporary sibling file;
- fail clearly on transport or HTTP errors;
- refuse to overwrite a complete destination unless `--force` is explicitly supplied;
- atomically rename a completed download into place;
- compute SHA-256 and byte size from the downloaded bytes;
- capture a UTC completion timestamp;
- inspect Parquet file metadata without assuming the schema;
- decode GeoParquet metadata and report geometry column, encoding, geometry types, and CRS as observed.

Temporary downloads use an unambiguous partial suffix. A failed transfer never appears under the final filename. An existing final file can be verified and reused by a separate explicit path, but download behavior does not silently overwrite it.

### Trajectory preprocessing

`apps.api.seawatch.trajectories.preprocess` owns pure or locally deterministic transformations:

- resolve required semantic source fields from the inspected schema;
- normalize timestamps to timezone-aware UTC;
- derive longitude and latitude from verified point geometry when necessary;
- reject null, non-finite, or out-of-range coordinates before bbox filtering;
- apply an inclusive bounding box (`west <= longitude <= east`, `south <= latitude <= north`);
- apply numeric AIS cargo codes 70 through 79;
- remove exact duplicate observations using the normalized output observation fields;
- report repeated timestamps within a vessel separately from exact duplicates;
- sort by source vessel identifier, UTC timestamp, and a stable source-order tie-breaker;
- calculate per-vessel consecutive time gaps for QA without interpolation;
- generate deterministic surrogate IDs;
- select complete vessel histories under the maximum observation target.

Unexpected motion is retained. No speed, course, heading, or time-gap value is removed merely because it looks unusual.

### Command-line orchestration

The scripts are thin wrappers around importable functions. They provide stable defaults for the approved date and bbox, explicit input/output paths, human-readable summaries, and nonzero exit status on failure. They do not contain business logic that would be inaccessible to tests.

## Schema Resolution and Geometry

Inspection occurs before transformation. The inspection output records:

- all source column names and Arrow data types;
- row count from Parquet metadata;
- row-group count;
- field nullability from the Arrow schema;
- Parquet key/value metadata;
- GeoParquet metadata, including primary geometry column and CRS when present;
- timestamp physical/logical representation;
- geometry representation as actually observed.

The preprocessor accepts a resolved mapping for vessel identifier, timestamp, SOG, COG, heading, vessel type, and either geometry or coordinate columns. It does not fabricate absent optional measurements. A missing field is reported as unavailable; a missing required vessel identifier, timestamp, or usable point location stops processing.

Longitude and latitude degrees are only used for WGS84-style angular bbox filtering. If source coordinates are declared in another CRS, coordinates are transformed with `pyproj` before applying the EPSG:4326 bbox. Degree values are never treated as linear distances.

## Surrogate Identifier

The public project identifier is named `track_id`. For each non-null normalized source vessel identifier, it is derived as:

```text
hex(SHA-256("seawatch:noaa-ais:2024-01-01:" + normalized_source_identifier))[:16]
```

The domain separator and source date make the method explicit and dataset-scoped. The result is deterministic for the same source identifier in this dataset and does not display MMSI directly. Documentation will state that an unsalted deterministic digest does not prevent re-identification by enumeration and is a display/privacy control, not anonymization.

The raw source identifier may exist in ignored local intermediate memory or files for grouping. It is excluded from the processed public columns, preview GeoJSON, committed manifest content, QA examples, and documentation examples.

## Deterministic Dataset Selection

Processing applies these stages in order:

1. Validate and normalize required values.
2. Retain valid coordinates and report invalid-coordinate counts.
3. Apply the inclusive SF Bay bbox.
4. Apply cargo vessel codes 70 through 79.
5. Remove exact duplicate observations and report them.
6. Sort each vessel chronologically with stable tie handling.
7. Compute QA statistics and time gaps.
8. Select complete vessel histories for output.

The default maximum is 50,000 observations, not a quota. When the eligible dataset is at or below that limit, all eligible observations are retained. When it exceeds the limit, complete vessel histories are chosen deterministically in ascending `track_id` order while the next complete history fits. A single vessel history larger than the maximum is not truncated; it is skipped and reported. No point-level random sampling or head/tail truncation is allowed.

If this selection yields no useful smoke dataset, the operator may explicitly use a smaller documented bbox in a later reviewed change. The approved bbox is not silently changed. Temporal downsampling is not part of this design.

## Output Contracts

The processed Parquet contains only source-backed or explicitly synthetic fields needed for later trajectory work:

- `track_id` (synthetic);
- `base_date_time` or the resolved canonical UTC timestamp name;
- `longitude` and `latitude` derived from the verified source geometry or source coordinates;
- `sog`, `cog`, `heading`, and `vessel_type` when present in the source;
- an optional non-identifying `source_row_number` only if needed for deterministic tie handling and explicitly recorded as synthetic.

The manifest's `source_columns`, `output_columns`, and `synthetic_fields` distinguish observed source values from derived fields. Output timestamps are timezone-aware UTC, and output coordinates are EPSG:4326.

The GeoJSON preview contains only a small deterministic set of complete selected vessel histories. Each feature is a `LineString` when a track has at least two valid points; single-point histories, if included for debugging, are `Point` features and identified as such. Properties contain `track_id` and non-identifying summary fields only. Raw MMSI or any source vessel identifier is forbidden.

## Manifest and Reports

The manifest is generated from measured processing results rather than hand-entered estimates. It includes every requested field, using JSON `null` and explanatory notes when a value cannot be observed. `git_commit_or_version_reference` may be `null` during generation because the final commit does not yet exist; the finalization step updates it to the intended processing version or commit reference without inventing a hash.

`docs/data-provenance.md` records the official source, verified license and attribution, date, study area, historical and US-specific nature, self-reported vessel type, reception/transmission limitations, and the rule that missing AIS is not automatically suspicious.

`docs/data-foundation-report.md` is generated or updated from measured values. It reports source bytes and metadata rows, bbox and cargo rows, vessel count, timestamp range, requested missing rates, coordinate validity, duplicates, time-gap statistics, and local artifact sizes. Unmeasured values are labeled explicitly rather than estimated.

## Failure Handling

The workflow fails with actionable messages for:

- inaccessible or non-successful official HTTP source;
- an existing destination without explicit overwrite intent;
- incomplete transfer or local I/O failure;
- unreadable or invalid Parquet metadata;
- missing required semantic fields;
- unsupported or ambiguous geometry/CRS metadata;
- timestamp values that cannot be normalized;
- no valid bbox or cargo records;
- attempted preview serialization containing a forbidden source identifier;
- output paths that would overwrite existing artifacts without explicit permission.

Failures must not leave a final-looking partial download or report fabricated completion statistics.

## Testing Strategy

Tests use tiny in-memory tables or tiny committed synthetic fixtures; normal automated tests never download NOAA data.

Unit tests cover deterministic surrogate IDs, inclusive bbox boundaries, invalid coordinates, UTC timestamp parsing, chronological ordering, exact duplicate removal, duplicate-timestamp reporting, cargo filtering, complete-track maximum selection, and preview identifier exclusion.

Adapter tests cover download refusal, explicit overwrite, HTTP failure, partial-file behavior, hashing, and metadata inspection using local test data. Network behavior is exercised through a local or injected response boundary rather than NOAA.

An integration test executes the synthetic flow from input observations through validation, bbox filtering, cargo filtering, ordering, output writing, manifest statistics, and preview writing. A separate explicit smoke command validates the real local NOAA file.

## Version-Control and Completion Rules

Implementation occurs on `feat/data-gis-foundation`. Before the single final commit, the complete test suite, explicit real-data smoke workflow, `git diff --check`, staged-file inspection, and checks for raw data, processed binary artifacts, `.env`, credentials, `.venv`, and `node_modules` must pass.

Only one local implementation commit is created, with message:

`feat: establish NOAA AIS data foundation`

No remote is added and nothing is pushed.

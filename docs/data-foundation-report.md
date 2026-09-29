# NOAA AIS Data Foundation QA Report

Measured from the official source and generated Phase 1 artifacts. Metrics prefixed `Eligible cargo` describe valid in-bbox cargo observations before the complete-track ceiling; vessel, timestamp, missing-rate, and final-row metrics describe the selected output.

| Metric | Observed value |
|---|---:|
| Source file size (bytes) | 227181435 |
| Source metadata row count | 7293408 |
| Selected bbox | [-122.55, 37.68, -122.25, 37.9] |
| BBox rows | 111179 |
| Cargo-filter rows (before exact deduplication) | 5582 |
| Number of vessels/tracks | 15 |
| Timestamp range (UTC) | 2024-01-01T00:00:01Z to 2024-01-01T23:59:50Z |
| SOG missing rate | 0.0000% |
| COG missing rate | 0.0000% |
| Heading missing rate | 0.0000% |
| Vessel type missing rate | 0.0000% |
| Coordinate-valid source rows | 7293408 |
| Coordinate validity rate | 100.0000% |
| Invalid coordinate rows | 0 |
| Invalid timestamp rows | 0 |
| Invalid source-identifier rows | 0 |
| Eligible cargo exact duplicate observations removed | 1 |
| Eligible cargo duplicate-timestamp rows retained | 0 |
| Eligible cargo time-gap observation pairs | 5566 |
| Eligible cargo positive time gaps | 5566 |
| Eligible cargo zero time gaps | 0 |
| Eligible cargo negative time gaps | 0 |
| Eligible cargo gaps greater than 10 minutes | 0 |
| Eligible cargo minimum positive gap (seconds) | 10.0 |
| Eligible cargo median positive gap (seconds) | 180.0 |
| Eligible cargo maximum positive gap (seconds) | 364.0 |
| Tracks skipped by the observation ceiling | 0 |
| Oversized tracks skipped | 0 |
| Final processed rows | 5581 |
| Processed Parquet size (bytes) | 91702 |
| GeoJSON preview size (bytes) | 145341 |

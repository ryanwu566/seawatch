# Trajectory Feature QA Report

Measured from the existing Phase 1 processed observations. Values describe data quality and movement distributions; statistical extremes are not labels.

## Counts

| Metric | Value |
|---|---:|
| Input observations | 8385 |
| Input tracks | 22 |
| Segments | 23 |
| Candidate windows | 4435 |
| Accepted windows | 3680 |
| Rejected windows | 755 |

## Planning estimate reconciliation

The 3,216/2,829 planning comparison does not apply to source dataset `noaa-ais-2024-01-03-sf-bay-cargo-smoke`.

## Rejected windows by reason

| Reason | Count |
|---|---:|
| insufficient_observations | 755 |

## Feature missingness

| Feature | Missing | Rate |
|---|---:|---:|
| sog_median_knots | 755 | 17.0237% |
| sog_p95_knots | 755 | 17.0237% |
| low_speed_fraction | 755 | 17.0237% |
| low_speed_duration_seconds | 755 | 17.0237% |
| path_distance_m | 755 | 17.0237% |
| displacement_m | 755 | 17.0237% |
| path_displacement_ratio | 3727 | 84.0361% |
| course_change_abs_sum_deg | 4248 | 95.7835% |
| course_change_abs_p95_deg | 4248 | 95.7835% |
| heading_cog_abs_median_deg | 4298 | 96.9109% |

## Distributions

### `segments_per_track`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 22 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 2.0 |

### `segment_duration_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 23 | 0 | 0.0 | 1080.0 | 36187.5 | 84275.0 | 86046.5 | 86234.0 | 86297.0 |

### `observations_per_segment`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 23 | 0 | 0.0 | 4.0 | 243.0 | 463.0 | 477.5 | 527.5 | 590.0 |

### `windows_per_track`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 22 | 0 | 0.0 | 5.0 | 125.0 | 278.0 | 281.0 | 282.0 | 282.0 |

### `windows_per_segment`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 23 | 0 | 0.0 | 0.0 | 115.5 | 275.0 | 281.0 | 282.0 | 282.0 |

### `max_gap_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 0 | 0.0 | 70.0 | 180.0 | 181.0 | 184.0 | 360.0 | 541.0 |

### `input_sog_knots`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8385 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.10000000149011612 | 9.399999618530273 | 19.799999237060547 |

### `course_change_abs_sum_deg`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 4248 | 0.9578354002254792 | 0.100006103515625 | 50.450016021728516 | 80.20003509521484 | 100.60001373291016 | 156.08999677896495 | 276.70003509521484 |

### `course_change_abs_p95_deg`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 4248 | 0.9578354002254792 | 0.09500579833984374 | 8.739996337890624 | 11.600000381469727 | 15.830014038085931 | 24.07500278472899 | 50.65000534057617 |

### `path_distance_m`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 755 | 0.17023675310033823 | 0.0 | 20.74864580981703 | 39.34943791270213 | 76.65680958972803 | 425.3785853438718 | 13819.739516151156 |

### `displacement_m`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 755 | 0.17023675310033823 | 0.0 | 2.21985161063682 | 5.730851205277535 | 30.121006987298724 | 353.18065395828575 | 13284.205918164222 |

### `path_displacement_ratio`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 3727 | 0.8403607666290868 | 1.0001461562573746 | 1.0497294529021017 | 1.1284660069355537 | 1.391051362022363 | 2.08216271164437 | 6.630724770320019 |

### `low_speed_fraction`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 755 | 0.17023675310033823 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

### `low_speed_duration_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4435 | 755 | 0.17023675310033823 | 0.0 | 1620.0 | 1620.0 | 1620.0 | 1701.3999999999978 | 1799.0 |

## Phase 3 gate

B. EXPAND DATA BEFORE MODELING

Acquire at least two additional separately approved dates as independent calibration and test partitions, then reassess vessel diversity and feature coverage. The additional dates require separate approval and are not acquired in Phase 2.

# Trajectory Feature QA Report

Measured from the existing Phase 1 processed observations. Values describe data quality and movement distributions; statistical extremes are not labels.

## Counts

| Metric | Value |
|---|---:|
| Input observations | 6651 |
| Input tracks | 16 |
| Segments | 19 |
| Candidate windows | 3785 |
| Accepted windows | 3335 |
| Rejected windows | 450 |

## Planning estimate reconciliation

The 3,216/2,829 planning comparison does not apply to source dataset `noaa-ais-2024-01-02-sf-bay-cargo-smoke`.

## Rejected windows by reason

| Reason | Count |
|---|---:|
| insufficient_observations | 450 |

## Feature missingness

| Feature | Missing | Rate |
|---|---:|---:|
| sog_median_knots | 450 | 11.8890% |
| sog_p95_knots | 450 | 11.8890% |
| low_speed_fraction | 450 | 11.8890% |
| low_speed_duration_seconds | 450 | 11.8890% |
| path_distance_m | 450 | 11.8890% |
| displacement_m | 450 | 11.8890% |
| path_displacement_ratio | 3370 | 89.0357% |
| course_change_abs_sum_deg | 3711 | 98.0449% |
| course_change_abs_p95_deg | 3711 | 98.0449% |
| heading_cog_abs_median_deg | 3738 | 98.7583% |

## Distributions

### `segments_per_track`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 2.0 | 2.0 |

### `segment_duration_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 19 | 0 | 0.0 | 0.0 | 21414.5 | 85500.0 | 86220.0 | 86241.2 | 86324.0 |

### `observations_per_segment`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 19 | 0 | 0.0 | 1.0 | 155.0 | 470.0 | 476.0 | 548.5 | 553.0 |

### `windows_per_track`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 0 | 0.0 | 0.0 | 276.75 | 282.0 | 282.0 | 282.0 | 282.0 |

### `windows_per_segment`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 19 | 0 | 0.0 | 0.0 | 68.0 | 280.0 | 282.0 | 282.0 | 282.0 |

### `max_gap_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 0 | 0.0 | 70.0 | 180.0 | 181.0 | 183.0 | 360.0 | 540.0 |

### `input_sog_knots`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 6651 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 | 16.799999237060547 |

### `course_change_abs_sum_deg`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 3711 | 0.980449141347424 | 5.199981689453125 | 51.14997863769531 | 77.79997634887695 | 116.74998760223389 | 146.7 | 167.0 |

### `course_change_abs_p95_deg`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 3711 | 0.980449141347424 | 2.100006103515625 | 8.355011749267575 | 10.989999771118155 | 13.119996261596679 | 23.845999450683582 | 29.930001831054685 |

### `path_distance_m`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 450 | 0.11889035667107001 | 0.0 | 17.064067388272637 | 29.36472212960058 | 48.9347369159181 | 217.75931325989401 | 13236.292584232386 |

### `displacement_m`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 450 | 0.11889035667107001 | 0.0 | 2.2198518307857906 | 5.284509823132714 | 17.946388144538986 | 186.56532366288158 | 12810.073474595105 |

### `path_displacement_ratio`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 3370 | 0.8903566710700133 | 1.0008902055316293 | 1.0381392912397092 | 1.0819821177535887 | 1.173448279657397 | 1.5781952282477987 | 31.967704048019137 |

### `low_speed_fraction`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 450 | 0.11889035667107001 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

### `low_speed_duration_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3785 | 450 | 0.11889035667107001 | 0.0 | 1620.0 | 1620.0 | 1620.0 | 1624.0 | 1799.0 |

## Phase 3 gate

B. EXPAND DATA BEFORE MODELING

Acquire at least two additional separately approved dates as independent calibration and test partitions, then reassess vessel diversity and feature coverage. The additional dates require separate approval and are not acquired in Phase 2.

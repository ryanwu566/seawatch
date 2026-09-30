# Trajectory Feature QA Report

Measured from the existing Phase 1 processed observations. Values describe data quality and movement distributions; statistical extremes are not labels.

## Counts

| Metric | Value |
|---|---:|
| Input observations | 5581 |
| Input tracks | 15 |
| Segments | 15 |
| Candidate windows | 3216 |
| Accepted windows | 2829 |
| Rejected windows | 387 |

## Planning estimate reconciliation

The implemented pipeline independently reproduced the planning values: 3,216 candidate windows and 2,829 accepted windows. There is no count difference to explain or force; 387 windows were measured as rejected for insufficient observations.

## Rejected windows by reason

| Reason | Count |
|---|---:|
| insufficient_observations | 387 |

## Feature missingness

| Feature | Missing | Rate |
|---|---:|---:|
| sog_median_knots | 387 | 12.0336% |
| sog_p95_knots | 387 | 12.0336% |
| low_speed_fraction | 387 | 12.0336% |
| low_speed_duration_seconds | 387 | 12.0336% |
| path_distance_m | 387 | 12.0336% |
| displacement_m | 387 | 12.0336% |
| path_displacement_ratio | 3004 | 93.4080% |
| course_change_abs_sum_deg | 3183 | 98.9739% |
| course_change_abs_p95_deg | 3183 | 98.9739% |
| heading_cog_abs_median_deg | 3192 | 99.2537% |

## Distributions

### `segments_per_track`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

### `segment_duration_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0 | 0.0 | 1049.0 | 61230.5 | 86220.0 | 86220.5 | 86223.2 | 86226.0 |

### `observations_per_segment`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0 | 0.0 | 17.0 | 368.0 | 476.0 | 477.5 | 487.99999999999994 | 509.0 |

### `windows_per_track`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0 | 0.0 | 0.0 | 198.5 | 282.0 | 282.0 | 282.0 | 282.0 |

### `windows_per_segment`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0 | 0.0 | 0.0 | 198.5 | 282.0 | 282.0 | 282.0 | 282.0 |

### `max_gap_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 0 | 0.0 | 67.0 | 180.0 | 181.0 | 184.0 | 360.0 | 364.0 |

### `input_sog_knots`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5581 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.30000001192092896 | 17.200000762939453 |

### `course_change_abs_sum_deg`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 3183 | 0.9897388059701493 | 11.0 | 58.29997253417969 | 85.5999984741211 | 102.0 | 110.23999938964843 | 116.0 |

### `course_change_abs_p95_deg`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 3183 | 0.9897388059701493 | 6.680003356933586 | 9.6550048828125 | 12.599999999999994 | 14.0 | 15.184003601074217 | 15.5 |

### `path_distance_m`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 387 | 0.12033582089552239 | 0.0 | 14.693775841929048 | 25.959631358159946 | 42.616170748565615 | 128.97758879897808 | 14032.897717834268 |

### `displacement_m`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 387 | 0.12033582089552239 | 0.0 | 2.08173288150605 | 4.526223793443764 | 11.66074174866992 | 97.13022437156226 | 13516.90517209429 |

### `path_displacement_ratio`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 3004 | 0.9340796019900498 | 1.0010792840479634 | 1.0363763243668296 | 1.0656017091986083 | 1.1175049131264327 | 1.5149212649011377 | 5.524681142180362 |

### `low_speed_fraction`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 387 | 0.12033582089552239 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

### `low_speed_duration_seconds`

| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3216 | 387 | 0.12033582089552239 | 0.0 | 1620.0 | 1620.0 | 1620.0 | 1624.0 | 1799.0 |

## Phase 3 gate

B. EXPAND DATA BEFORE MODELING

Acquire at least two additional separately approved dates as independent calibration and test partitions, then reassess vessel diversity and feature coverage. The additional dates require separate approval and are not acquired in Phase 2.

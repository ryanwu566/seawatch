# Phase 3A NOAA AIS Data Expansion Report

The three dates were processed independently with fixed roles. Counts and movement summaries are descriptive QA, not anomaly scores.

## Daily cohort

| Date | Role | Observations | Tracks | Segments | Candidate windows | Accepted | Rejected | Approx. non-overlap | Max track share |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-01-01 | train | 5581 | 15 | 15 | 3216 | 2829 | 387 | 471 | 0.097561 |
| 2024-01-02 | calibration | 6651 | 16 | 19 | 3785 | 3335 | 450 | 555 | 0.0812594 |
| 2024-01-03 | test | 8385 | 22 | 23 | 4435 | 3680 | 755 | 613 | 0.0733696 |

## Feature missingness

| Feature | 2024-01-01 | 2024-01-02 | 2024-01-03 |
|---|---:|---:|---:|
| `sog_median_knots` | 12.0336% | 11.8890% | 17.0237% |
| `sog_p95_knots` | 12.0336% | 11.8890% | 17.0237% |
| `low_speed_fraction` | 12.0336% | 11.8890% | 17.0237% |
| `low_speed_duration_seconds` | 12.0336% | 11.8890% | 17.0237% |
| `path_distance_m` | 12.0336% | 11.8890% | 17.0237% |
| `displacement_m` | 12.0336% | 11.8890% | 17.0237% |
| `path_displacement_ratio` | 93.4080% | 89.0357% | 84.0361% |
| `course_change_abs_sum_deg` | 98.9739% | 98.0449% | 95.7835% |
| `course_change_abs_p95_deg` | 98.9739% | 98.0449% | 95.7835% |
| `heading_cog_abs_median_deg` | 99.2537% | 98.7583% | 96.9109% |

## SOG, path, turning, and quality distributions

| Distribution | Date | Min | P25 | Median | P75 | P95 | Max |
|---|---|---:|---:|---:|---:|---:|---:|
| `input_sog_knots` | 2024-01-01 | 0 | 0 | 0 | 0 | 0.3 | 17.2 |
| `input_sog_knots` | 2024-01-02 | 0 | 0 | 0 | 0 | 0.5 | 16.8 |
| `input_sog_knots` | 2024-01-03 | 0 | 0 | 0 | 0.1 | 9.4 | 19.8 |
| `path_distance_m` | 2024-01-01 | 0 | 14.6938 | 25.9596 | 42.6162 | 128.978 | 14032.9 |
| `path_distance_m` | 2024-01-02 | 0 | 17.0641 | 29.3647 | 48.9347 | 217.759 | 13236.3 |
| `path_distance_m` | 2024-01-03 | 0 | 20.7486 | 39.3494 | 76.6568 | 425.379 | 13819.7 |
| `displacement_m` | 2024-01-01 | 0 | 2.08173 | 4.52622 | 11.6607 | 97.1302 | 13516.9 |
| `displacement_m` | 2024-01-02 | 0 | 2.21985 | 5.28451 | 17.9464 | 186.565 | 12810.1 |
| `displacement_m` | 2024-01-03 | 0 | 2.21985 | 5.73085 | 30.121 | 353.181 | 13284.2 |
| `path_displacement_ratio` | 2024-01-01 | 1.00108 | 1.03638 | 1.0656 | 1.1175 | 1.51492 | 5.52468 |
| `path_displacement_ratio` | 2024-01-02 | 1.00089 | 1.03814 | 1.08198 | 1.17345 | 1.5782 | 31.9677 |
| `path_displacement_ratio` | 2024-01-03 | 1.00015 | 1.04973 | 1.12847 | 1.39105 | 2.08216 | 6.63072 |
| `course_change_abs_sum_deg` | 2024-01-01 | 11 | 58.3 | 85.6 | 102 | 110.24 | 116 |
| `course_change_abs_sum_deg` | 2024-01-02 | 5.19998 | 51.15 | 77.8 | 116.75 | 146.7 | 167 |
| `course_change_abs_sum_deg` | 2024-01-03 | 0.100006 | 50.45 | 80.2 | 100.6 | 156.09 | 276.7 |
| `course_change_abs_p95_deg` | 2024-01-01 | 6.68 | 9.655 | 12.6 | 14 | 15.184 | 15.5 |
| `course_change_abs_p95_deg` | 2024-01-02 | 2.10001 | 8.35501 | 10.99 | 13.12 | 23.846 | 29.93 |
| `course_change_abs_p95_deg` | 2024-01-03 | 0.0950058 | 8.74 | 11.6 | 15.83 | 24.075 | 50.65 |
| `low_speed_fraction` | 2024-01-01 | 0 | 1 | 1 | 1 | 1 | 1 |
| `low_speed_fraction` | 2024-01-02 | 0 | 1 | 1 | 1 | 1 | 1 |
| `low_speed_fraction` | 2024-01-03 | 0 | 1 | 1 | 1 | 1 | 1 |
| `max_gap_seconds` | 2024-01-01 | 67 | 180 | 181 | 184 | 360 | 364 |
| `max_gap_seconds` | 2024-01-02 | 70 | 180 | 181 | 183 | 360 | 540 |
| `max_gap_seconds` | 2024-01-03 | 70 | 180 | 181 | 184 | 360 | 541 |

Null distribution values mean the feature was unsupported, not zero. Angular and path/displacement-ratio support remains sparse and must not be zero-filled.

## Data-quality comparison

| Date | Out-of-order pairs | Invalid SOG | Invalid COG | Invalid heading | Rejections | Windows/track min | median | max |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| 2024-01-01 | 0 | 0 | 0 | 0 | {"insufficient_observations": 387} | 0 | 282 | 282 |
| 2024-01-02 | 0 | 0 | 0 | 0 | {"insufficient_observations": 450} | 0 | 282 | 282 |
| 2024-01-03 | 0 | 0 | 0 | 0 | {"insufficient_observations": 755} | 5 | 278 | 282 |

## Phase 3B readiness

A. DATA SUFFICIENT FOR BASELINE ANOMALY EXPERIMENTS

- All Phase 3B readiness criteria passed.

Overlapping windows are dependent, and date-scoped track surrogates do not provide anonymization.

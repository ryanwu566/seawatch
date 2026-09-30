# Phase 3B Explainable Behavioral Review-Ranking Report

SeaWatch prioritizes behavioral patterns for human review. Scores are not probabilities, confidence values, labels, or findings about intent or legality.

## Frozen data roles

- 2024-01-01: background/reference fit
- 2024-01-02: calibration and method comparison
- 2024-01-03: held-out temporal evaluation

No random window split was used.

## Feature policy

Active features: sog_median_knots, sog_p95_knots, low_speed_fraction, low_speed_duration_seconds, path_distance_m, displacement_m.
Disabled conditional features: course_change_abs_p95_deg, course_change_abs_sum_deg, heading_cog_abs_median_deg, path_displacement_ratio.

## Calibration comparison

| Method | Eligible | Median top-20 Jaccard | Tracks | Max track share | Reason coverage |
|---|---:|---:|---:|---:|---:|
| rule | False | 1.0 | 2 | 0.950 | 1.000 |
| empirical_percentile | True | 1.0 | 3 | 0.400 | 1.000 |
| robust_mad | False | 0.8614718614718615 | 2 | 0.800 | 1.000 |
| isolation_forest | False | 0.14285714285714285 | 2 | 0.700 | 1.000 |

Primary demo candidate: **empirical_percentile**. Eligibility gate passed: **True**.

## Calibration robustness

| Method | Minimum top-20 overlap | Minimum rank correlation |
|---|---:|---:|
| rule | 1.000 | 0.860 |
| empirical_percentile | 1.000 | 1.000 |
| robust_mad | 0.600 | 1.000 |
| isolation_forest | 0.000 | 0.992 |

The fixed calibration perturbations cover reference clipping, rule boundaries, Isolation Forest seeds, and Isolation Forest tree counts. They do not use January 3.

## Held-out temporal evaluation

| Method | Review workload | Cutoff exceedances | Tracks | Max track share | Reason coverage |
|---|---:|---:|---:|---:|---:|
| rule | 20 | 83 | 2 | 0.650 | 1.000 |
| empirical_percentile | 20 | 58 | 9 | 0.300 | 1.000 |
| robust_mad | 20 | 180 | 2 | 0.950 | 1.000 |
| isolation_forest | 20 | 158 | 3 | 0.900 | 1.000 |

## Interpretation limits

- Rankings identify deviations from the January 1 background for human review only.
- No ground-truth event labels, accuracy, precision, recall, or inferred intent are reported.
- Overlapping windows and repeated vessel tracks are dependent.
- January 3 aggregate QA was known from Phase 3A, so this is not a pristine blind evaluation.
- Isolation Forest reasons are supporting feature evidence, not model attribution.

# SeaWatch Phase 3B Explainable Behavioral Review Ranking Design

**Status:** Proposed for review; design and planning only

**Date:** 2026-09-30

**Base:** `feat/multiday-data-expansion` at
`5200b4d` (`feat: expand multi-day AIS cohort`)

## 1. Purpose and boundaries

Phase 3B designs an offline baseline system that ranks AIS trajectory windows
for human review. It converts the existing Phase 2 feature tables into
deterministic review-priority scores, concise evidence reasons, data-quality
context, and a calibration/evaluation report.

SeaWatch remains an explainable maritime decision-support system. A high rank
means only that a window differs from the January 1 reference under a named
method and may merit human review. It does not establish intent, legality,
danger, identity, or a confirmed anomaly event.

Allowed product language includes:

- `behavioral pattern requiring human review`;
- `review-priority score`;
- `deviation from the background reference`;
- `supporting feature evidence`;
- `relevant`, `false positive`, and `keep monitoring` as human review choices.

The implementation and generated output must not call a vessel hostile,
illegal, dangerous, suspicious, malicious, or a confirmed anomaly. It must
not infer why a behavior occurred.

Phase 3B includes:

- a pre-model feature-selection analysis;
- a transparent rule baseline;
- empirical-percentile and robust-MAD statistical baselines;
- an Isolation Forest comparison;
- leakage-safe calibration and held-out ranking;
- explanation generation for every shortlisted window;
- label-free stability, robustness, temporal-transfer, and workload analysis;
- aggregate reports and a local ranked-window artifact suitable for a future
  API adapter.

Phase 3B excludes API endpoints, UI implementation, a review database,
automatic alert dispatch, model-serving infrastructure, deployment, new AIS
dates, raw-identity linkage, supervised accuracy claims, deep learning,
Transformers, LSTMs, GNNs, autoencoders, embeddings, and LLM reasoning.

## 2. Authoritative data and split contract

The only inputs are the three validated Phase 2 window artifacts referenced by
the Phase 3A cohort manifest:

| Date | Role | Candidate windows | Accepted windows |
|---|---|---:|---:|
| 2024-01-01 | background/reference | 3,216 | 2,829 |
| 2024-01-02 | calibration | 3,785 | 3,335 |
| 2024-01-03 | held-out evaluation | 4,435 | 3,680 |

Only windows whose existing `window_quality_status` is `sufficient` may be
scored. Rejected windows remain in aggregate counts but never receive a
review-priority score. Phase 3B does not change Phase 1 selection, Phase 2
segmentation, windowing, feature definitions, or the configuration hash
`70aa8dd26c6f438c5122b48a497aad426fc5e4661829ff54611a266048f92a02`.

The split roles are immutable:

```text
fit reference distributions and models     = 2024-01-01 only
choose thresholds and demo method           = 2024-01-02 only
run one frozen evaluation                    = 2024-01-03 only
```

January 3 is held out from Phase 3B fitting, feature gating, normalization,
threshold selection, and method selection. It is not a pristine blind test:
Phase 3A already published aggregate January 3 counts, missingness, and
quantiles. Phase 3B must record this limitation and must not claim a blinded
or unbiased estimate of detection performance.

## 3. Considered approaches

### 3.1 Recommended architecture: shared reference profile, independent scorers

Fit one immutable January 1 reference profile containing feature support,
clipping bounds, empirical distributions, medians, IQRs, and MADs. Pass the
same eligible rows and frozen feature policy to independent rule,
statistical, and Isolation Forest scorers. Normalize each method's continuous
score to a training-reference percentile for presentation, then rank with one
shared deterministic sorter and explanation schema.

This makes leakage checks, method comparison, and future API integration
straightforward. A model can be replaced without changing the review record
contract.

### 3.2 Rejected: one opaque ensemble score

Blending rules, statistics, and Isolation Forest into one score would hide
method disagreement and make explanations ambiguous. Phase 3B compares
methods and selects one demo method; it does not ensemble them.

### 3.3 Rejected: per-date normalization

Fitting a scaler or percentile distribution separately on calibration or test
would erase temporal shifts and leak later-date information into scores. All
learned transformations come from January 1 and are applied unchanged.

### 3.4 Rejected: point-level random train/test splits

Overlapping windows share observations, and windows from a date-scoped track
are strongly dependent. Random window splits would produce severe leakage and
inflated stability. The date split remains authoritative; resampling for
uncertainty operates on whole tracks.

## 4. Component architecture and data flow

```text
Phase 3A cohort manifest
        |
        v
strict split/artifact loader
        |
        +--> train accepted windows ------> feature policy + reference profile
        |                                         |
        |                                         +--> rule scorer
        |                                         +--> percentile scorer
        |                                         +--> robust-MAD scorer
        |                                         +--> Isolation Forest
        |
        +--> calibration accepted windows --> score, calibrate, compare, select
        |                                         |
        |                                         v
        |                                  frozen protocol JSON
        |
        +--> held-out accepted windows ----> frozen scoring and evaluation
                                                  |
                                                  v
                                      ranked review records + aggregate report
```

The workflow has explicit stages:

1. `select-features` reads January 1 and January 2 only, freezes feature tiers,
   and writes a hashed policy artifact.
2. `calibrate` fits only January 1, evaluates stability and workload only on
   January 2, selects the demo method, and writes a frozen protocol artifact.
3. `evaluate` requires the frozen protocol hash before opening January 3 and
   produces local rankings plus aggregate evaluation metadata.
4. `report` renders aggregate, identifier-free documentation.

The process does not serialize or commit a fitted estimator. Deterministic
evaluation refits from the hashed January 1 artifact, pinned configuration,
and fixed random seed, then verifies that the recomputed reference/protocol
hash matches the frozen metadata.

## 5. Feature-selection policy

Feature availability is assessed among `sufficient` windows, not among the
candidate windows rejected by Phase 2. Feature tiers are declared in committed
configuration, then validated using January 1 and January 2 only.

### 5.1 Tier A: default scoring features

The initial core is:

- `sog_median_knots`;
- `sog_p95_knots`;
- `low_speed_fraction`;
- `low_speed_duration_seconds`;
- `path_distance_m`;
- `displacement_m`.

A Tier A feature must have at least 95% finite support among accepted windows
on both train and calibration, a declared unit, a declared scoring direction,
and at least two distinct finite training values. A Tier A window with any
missing core feature is not imputed: it is excluded as `missing_core_feature`
and counted in QA.

### 5.2 Tier B: conditional features

The conditional candidates are:

- `path_displacement_ratio`;
- `course_change_abs_sum_deg`;
- `course_change_abs_p95_deg`.

A Tier B feature may enter a scorer only when both train and calibration have:

- at least 80% finite support among accepted windows;
- support from at least 200 windows and 10 tracks;
- no more than a 10 percentage-point train/calibration support difference;
- finite values inside its Phase 2 semantic range.

The measured Phase 3A missingness indicates these features are unlikely to
pass. A failing Tier B feature is excluded from scores and reasons. It may be
shown as unscored diagnostic context when present, clearly labeled
`not used in ranking`.

### 5.3 Tier C: initially excluded

`heading_cog_abs_median_deg` is Tier C because support is extremely sparse. It
is neither imputed nor used by any Phase 3B scorer or explanation.

### 5.4 Correlation and duplicate-evidence control

Tier A features are grouped by behavioral concept so correlated measurements
do not receive accidental extra weight:

| Group | Features |
|---|---|
| speed | `sog_median_knots`, `sog_p95_knots` |
| low-speed persistence | `low_speed_fraction`, `low_speed_duration_seconds` |
| movement/progress | `path_distance_m`, `displacement_m` |

Each scorer first reduces features to group evidence, normally by the maximum
within-group severity. Composite scores operate on groups, not on six
independent votes.

## 6. Reference transformations and missing values

The January 1 reference profile records, per active feature:

- finite count and track count;
- 1st and 99th percentile clipping bounds;
- empirical sorted values for percentile lookup;
- median, IQR, and MAD;
- selected scale and any inactive/constant-feature reason.

All bounds and statistics are learned from January 1 only. Calibration and
evaluation values are clipped to the frozen 1st/99th percentile bounds for
robust-MAD and Isolation Forest input. Their original values are retained for
display and evidence messages.

The robust scale is chosen in this order:

1. `IQR / 1.349` when IQR is positive;
2. `1.4826 * MAD` when MAD is positive;
3. otherwise mark the feature constant and inactive.

No missing value is converted to zero. Tier A missingness makes a window
unscorable. Tier B missingness makes that conditional feature unavailable and,
because all methods must use a consistent default surface, Tier B is included
only if its support gate passes and its configured missing policy is
`exclude_window`. Phase 3B v1 does not implement learned imputation.

Isolation Forest does not mathematically require standardized units, but it
receives the same clipped, robust-scaled active feature matrix (Tier A plus any
Tier B feature that passes the gate) to keep preprocessing auditable and
comparable across methods. An extreme raw value therefore cannot dominate
simply because of units, and later dates cannot alter scaling.

## 7. Baseline 0: transparent rule scoring

The rule baseline converts January 1 empirical percentiles into explicit
review patterns:

| Rule code | Evidence | Tail |
|---|---|---|
| `persistent_low_speed` | low-speed fraction or duration | high |
| `limited_movement` | path distance or displacement | low |
| `unusually_low_speed` | median or p95 SOG | low |
| `unusual_turning` | eligible Tier B course change | high |
| `movement_irregularity` | eligible Tier B path/displacement ratio | high |

A feature begins contributing above the 95th training percentile for a high
tail or below the 5th percentile for a low tail. Severity increases linearly
from zero at that boundary to one at the observed training tail. A group's
severity is its maximum feature severity, and the rule score is the maximum
group severity multiplied by 100.

This baseline is directly explainable and requires no distributional
assumption. Its limitations are threshold discontinuity, tied scores,
sensitivity to the narrow reference day, and the fact that the chosen rules
reflect review priorities rather than maritime truth.

## 8. Baseline 1: statistical deviation scoring

### 8.1 Empirical-percentile scorer (recommended transparent baseline)

For value `x`, the reference percentile uses a deterministic mid-rank empirical
CDF: `(count(values < x) + 0.5 * count(values == x)) / n`. The two-sided
feature extremeness is `2 * abs(percentile - 0.5)` in `[0, 1]`.

Each behavioral group's score is its maximum feature extremeness. The overall
score is `100 * (0.7 * largest_group + 0.3 * second_largest_group)`. This
allows a single strong deviation to matter while requiring a second signal for
the highest scores and avoiding double-counting correlated features.

Advantages are unit-free output, robustness to skew, exact percentile reasons,
and no normality assumption. Limitations are coarse ranks under heavy ties,
poor extrapolation beyond the observed day, and no modeling of multivariate
interactions.

### 8.2 Robust-MAD scorer

The robust standardized deviation is
`abs(clipped_value - train_median) / train_scale`. Values are converted to
severity with `1 - exp(-deviation)`, then aggregated with the same group rule
as the percentile scorer.

Advantages are smooth scores and interpretable robust distances. Limitations
are zero-dispersion features, sensitivity to the scale fallback, and a weaker
human intuition than percentiles.

### 8.3 Ordinary z-score

Mean/standard-deviation z-scores are documented and measured as a diagnostic
only. They are not a demo candidate because the observed distributions are
zero-heavy, skewed, and contain extreme tails. Including ordinary z-score in
the primary ranking would let a small number of extreme values dominate and
would imply a distributional stability not supported by three dates.

## 9. Baseline 2: Isolation Forest

Isolation Forest is suitable as a multivariate comparison because it is
unsupervised, handles nonlinear feature combinations, and can fit the 2,829
accepted training windows efficiently. It is not treated as ground truth or
as an automatic classifier.

The fixed v1 parameters are:

```text
n_estimators = 256
max_samples = "auto"
max_features = 1.0
bootstrap = false
contamination = "auto"
random_state = 42
n_jobs = 1
```

The implementation uses `-score_samples` as a continuous deviation value and
maps it to a January 1 empirical percentile. It never exposes
`IsolationForest.predict()` labels. `contamination` affects the library's
classification offset, not the meaning or prevalence of real behavior; using
`"auto"` avoids asserting an unsupported anomaly rate. Review thresholds come
from the separate calibration protocol.

Isolation Forest's limitations are central to comparison:

- tree isolation paths are not inherently human explanations;
- overlapping windows and only 15 training tracks reduce effective diversity;
- ranking can vary with seed, track composition, and hyperparameters;
- robust scaling aids consistency but does not make the model causal;
- local evidence features are not exact model attributions.

Every Isolation Forest shortlist item receives `supporting evidence` based on
the largest frozen-reference percentile deviations among its scoring features.
The UI/report must say these reasons describe the window and support review;
they do not claim to decompose or explain the forest's internal score.

Implementation pins `scikit-learn==1.9.1`, which supplies CPython 3.12 Windows
wheels and supports the required deterministic parameters. No fitted binary or
joblib artifact is committed.

## 10. Calibration and method selection

Calibration uses January 2 without labels. It cannot optimize accuracy,
precision, recall, or an assumed anomaly rate.

The primary demo workload is fixed in configuration at 20 windows per date.
For each method, calibration records:

- the score of the 20th-ranked window as a diagnostic transfer cutoff;
- top-20 distinct-track count and maximum single-track share;
- top-20 reason coverage;
- cluster-bootstrap top-20 stability;
- score and reason distributions;
- sensitivity at review budgets 10, 20, and 50.

The official shortlist always contains exactly the top 20 eligible windows,
using deterministic tie-breaking. Applying the calibration score cutoff to
January 3 is a separate temporal-transfer diagnostic and may yield more or
fewer than 20 windows.

A method is demo-eligible only if it has:

- exact deterministic rerun equivalence;
- reasons for 100% of its top 20;
- at least three tracks represented in its top 20;
- no single track contributing more than 50% of its top 20;
- median whole-track-bootstrap top-20 Jaccard of at least 0.50 over 100 fixed
  resamples.

Among eligible methods, choose the highest calibration stability. Differences
below 0.05 are treated as ties, resolved by the transparency preference:
empirical percentile, rule, robust MAD, then Isolation Forest. The selected
method and all thresholds are frozen before January 3 is opened. January 3
results cannot change the selected method.

## 11. Deterministic ranking and output contract

The public/local ranked-window schema version is
`phase3b-review-ranking-v1`. Every scored record contains:

- `source_date` and immutable `split_role`;
- `method_id` and `method_version`;
- `window_id`, date-scoped `track_id`, and `segment_id`;
- window start/end and observation start/end UTC;
- `review_priority_score` in `[0, 100]`;
- `rank_within_date_method`;
- `shortlisted` and `calibration_cutoff_exceeded`;
- structured `evidence_reasons`;
- original supporting feature values and frozen-reference percentiles;
- observation count, observed duration, max gap, zero-duration interval count,
  valid fractions, and feature-missing count;
- `review_status = "unreviewed"` and allowed future actions
  `review`, `relevant`, `false_positive`, `keep_monitoring`.

The sort order is:

1. review-priority score descending;
2. window start UTC ascending;
3. `track_id` ascending;
4. `window_id` ascending.

This makes ties reproducible. Raw source identifiers never enter the schema.
The date-scoped `track_id` remains a display control, not anonymization.

Real ranking Parquet/JSON artifacts are local and ignored. Aggregate reports
must not contain individual track or window identifiers.

## 12. Explanation contract

Each `EvidenceReason` contains:

- stable `reason_code`;
- `feature_group` and `feature_name`;
- observed value and unit;
- reference percentile or robust deviation;
- direction (`higher` or `lower` than background);
- severity in `[0, 1]`;
- factual message rendered from a fixed template;
- `attribution_kind`, either `exact_component` for rule/statistical methods or
  `supporting_evidence` for Isolation Forest.

Examples:

- `Low-speed duration is at the 98th percentile of the January 1 background.`
- `Displacement is below 97% of the January 1 background windows.`
- `Course-change evidence was not used because support did not pass the
  conditional-feature gate.`

Every shortlisted record must have at least one reason. Rule and statistical
alerts list all triggered groups, capped at three reasons by severity. If a
statistical window has no feature beyond the 5th/95th tails but is still in the
top 20, its most deviant group supplies one reason. Isolation Forest lists the
top three supporting feature deviations and explicitly disclaims attribution.

Free-form LLM explanations are forbidden. Messages come only from reviewed
templates, and tests scan output for prohibited accusatory language.

## 13. Evaluation without anomaly labels

No accuracy, precision, recall, F1, ROC-AUC, false-positive rate, or detection
rate is reported. A human review action is feedback, not ground truth about
intent or legality.

### 13.1 Stability

Use 100 fixed whole-track bootstrap resamples of January 1. Refit each method,
rerank January 2, and report top-10/20/50 Jaccard, rank correlation, and score
variation. Windows are never resampled independently.

### 13.2 Explainability

Report top-20 reason coverage, number of reasons per candidate, reason-code
distribution, exact-component versus supporting-evidence coverage, and
examples without identifiers. The minimum required reason coverage is 100%.

### 13.3 Robustness

Recompute rankings under predeclared perturbations:

- clipping bounds 0.5/99.5 and 2/98 instead of 1/99;
- rule boundaries 90/10 and 97.5/2.5 instead of 95/5;
- Isolation Forest seeds 7, 42, and 101;
- Isolation Forest estimators 128, 256, and 512.

Report top-K overlap and rank correlations; do not choose a favorable variant
after reading January 3.

### 13.4 Temporal generalization

Apply the frozen January 1 reference and January 2 protocol once to January 3.
Report score quantiles, number above the calibration cutoff, top-20 track
concentration, reason distribution shift, method agreement, and calibration
versus evaluation top-K stability. Differences are descriptive transfer
evidence, not detection performance.

### 13.5 Review workload

Report the reduction from all accepted windows to review budgets 10, 20, and
50, the number of distinct tracks represented, and concentration per track.
The primary demo presents 20 candidates rather than asking a reviewer to scan
all 3,680 held-out accepted windows.

## 14. Vessel-level dependence

The system never treats 9,844 accepted windows as independent samples.
Overlapping windows share observations, multiple windows belong to one
date-scoped track, and date-scoped surrogates prevent reliable cross-date
vessel linkage. Consequences are:

- fitting is window-based but all uncertainty resampling is track-clustered;
- reports show both window and track counts;
- top-K concentration is a required workload metric;
- no confidence interval assumes independent windows;
- cross-date vessel independence is not claimed;
- the three-day corpus cannot establish population prevalence.

## 15. Error handling and leakage controls

The workflow fails closed when:

- a cohort date, split role, artifact hash, Phase 2 config hash, schema, CRS, or
  timezone differs from Phase 3A;
- a selection/calibration stage is given the January 3 path;
- evaluation begins without a frozen protocol and matching hash;
- any reference statistic is derived from calibration or evaluation;
- a Tier A feature fails its support gate;
- non-finite values reach a scorer;
- a ranked output contains a forbidden source identifier;
- a shortlist record lacks an explanation;
- output language contains a prohibited claim;
- output paths collide or alias inputs without explicit overwrite.

Stage artifacts record input hashes, configuration hash, package versions,
random seeds, feature policy, reference-profile hash, and protocol hash.

## 16. Artifact and repository strategy

Commit-eligible Phase 3B artifacts are limited to source code, pinned
dependencies, configuration, tests, documentation, aggregate identifier-free
JSON under `docs/qa/`, and tiny synthetic fixtures.

Local ignored artifacts include:

```text
data/processed/review_ranking/
  phase3b-feature-policy.json
  phase3b-reference-profile.json
  phase3b-calibration-protocol.json
  2024-01-01-<method>-rankings.parquet
  2024-01-02-<method>-rankings.parquet
  2024-01-03-<method>-rankings.parquet
  phase3b-evaluation.json
```

No raw AIS, real feature Parquet, ranked-window Parquet/JSON, fitted estimator,
joblib/pickle, database, secret, or large artifact is committed. The aggregate
comparison JSON and Markdown report contain counts, distributions, stability,
method selection, limitations, and provenance but no individual identifiers.

## 17. Future demo story and API readiness

The future demo, outside this implementation's UI scope, follows a neutral
review workflow:

1. A map displays existing vessel tracks.
2. SeaWatch shows a ranked list titled `Behavioral patterns requiring review`.
3. A judge opens one candidate window.
4. The detail panel shows review-priority score, method, factual evidence,
   supporting features, observation quality, and the non-accusatory disclaimer.
5. The human chooses `relevant`, `false positive`, or `keep monitoring`.

The ranked record contract is sufficient for a future read-only API. Phase 3B
does not implement routes, persistence, authentication, or feedback learning.

## 18. Test strategy

All automated tests use small synthetic windows and prohibit network access.
They cover:

- exact feature tiers and support gates;
- rejection of low-support conditional features;
- accepted-window-only scoring;
- no missing-to-zero conversion;
- train-only clipping, scaling, percentiles, and model fitting;
- calibration-only cutoff and method selection;
- evaluation-stage isolation and frozen protocol hashes;
- rule, percentile, robust-MAD, and Isolation Forest determinism;
- deterministic feature order and tie-breaking;
- group aggregation without correlated-feature double counting;
- structured explanation generation and 100% shortlist coverage;
- Isolation Forest evidence labeled as supporting, not attribution;
- prohibited-language and forbidden-identifier scans;
- whole-track rather than window bootstrap;
- stability, robustness, temporal-transfer, and workload metrics;
- atomic outputs, collision protection, and offline reproducibility;
- a synthetic three-date end-to-end workflow.

Real Phase 3A artifacts are used only by an explicit offline smoke workflow.
No test invents anomaly labels.

## 19. Completion criteria

Phase 3B is complete only when:

1. the feature-selection report freezes Tier A/B/C decisions before scoring;
2. at least one transparent rule or statistical baseline passes all gates;
3. the Isolation Forest comparison uses the same frozen active feature surface
   as the transparent methods;
4. repeated runs produce byte-stable aggregate output and identical rankings;
5. every top-20 candidate has structured factual evidence;
6. train/calibration/evaluation access boundaries are mechanically enforced;
7. no learned value uses January 2 or January 3 except as explicitly allowed;
8. label-free limitations and vessel/window dependence are prominent;
9. real ranking and model artifacts remain ignored and local;
10. the ranked record schema is ready for a future API adapter;
11. the full offline suite and explicit real-data audit pass;
12. no output makes an intent, legality, danger, or confirmed-anomaly claim.

## 20. Final design decision and implementation order

Implement in this order:

1. **Feature policy and leakage-safe reference profile.** Nothing should score
   until feature support, missingness, transformations, and split access are
   explicit and testable.
2. **Rule baseline.** It establishes the output/explanation contract with the
   simplest review logic and gives humans an interpretable floor.
3. **Empirical-percentile and robust-MAD baselines.** These add smooth,
   train-referenced ranking while retaining exact feature-level evidence.
4. **Isolation Forest comparison.** Add it only after shared preprocessing,
   deterministic output, and explanation safeguards already work.
5. **Calibration-only comparison and demo selection.** Freeze the selected
   method, top-20 workload, and thresholds before evaluation.
6. **One held-out January 3 evaluation and aggregate report.** Run once under
   the frozen protocol, document limitations, and stop before API/UI work.

The empirical-percentile scorer is the recommended default demo candidate
because it matches the skewed data, yields direct percentile explanations, and
does not imply a probability or learned anomaly class. Isolation Forest is a
useful comparison, not the presumed winner. Calibration evidence may select a
different eligible method only under the predeclared stability rubric; January
3 cannot influence that choice.

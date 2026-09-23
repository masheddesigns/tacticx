# TacticX Phase 28 — Production Monitoring & Performance Analysis

Contract: `PRODUCTION_MONITORING_V1` · Metrics: `monitoring_metrics_v1` ·
Buckets: `reliability_buckets_v1`

## 1. Purpose

Observability + analysis over immutable prediction/evaluation records.
Answers: how the system performs, stability over time, calibration,
competition/season differences, data-quality changes, coverage, drift
signs, and whether evidence justifies further research. Measurement
only — no model changes, no rankings, no causality claims.

## 2. Architecture decision: no migration, no scheduler job

- **No migration**: all monitoring is read-only aggregation over
  existing immutable tables (`matches`, `prematch_readiness_certificates`,
  `prediction_feature_snapshots`, `prematch_prediction_snapshots`,
  `match_outcome_snapshots`, `prediction_evaluation_records`,
  `source_health`, `source_activations`, `reconciliation_conflicts`,
  `match_source_mappings`). No persistent monitoring snapshot was
  required, so no schema change exists to migrate. Head stays `0012`.
- **No scheduler job**: monitoring is purely query-based; anomaly rules
  are deterministic computations evaluated on demand by the API. No
  scheduled snapshot is required, so no `PRODUCTION_MONITORING` job was
  added (per §17, documented here instead).

## 3. Metrics: definitions, formulas, denominator rules

Reuses Phase 2 / Phase 27 definitions (`backtesting/metrics.py`,
`prediction_evaluation/aggregation.py`): accuracy (argmax hit),
multiclass log loss (1e-12 clipping), full-vector Brier, goal MAE,
RMSE-from-mean-SE, market accuracies. **Denominator rules**: every rate
uses `safe_rate` — `None` (unknown) on zero denominators, never zero;
every rate response exposes its denominator; `0` and unknown are distinct.

## 4. Calibration: buckets, ECE, MCE

Deterministic equal-width bins over [0,1] (`n_bins=10`, last bin closed
both ends), per 1X2 outcome: bin bounds, mean predicted, empirical
frequency, count, Wilson CI on the frequency. ECE = count-weighted mean
error over non-empty bins; MCE = maximum bin error. Empty samples yield
`ece/mce: null`.

## 5. Drift: baselines, windows, states

Trailing window (default recent 50) vs full baseline (≤5000, same
filters). Reports means, absolute + relative differences, sample sizes,
periods. States: `INSUFFICIENT_DATA` (recent < 20), `WATCH`
(|Δbrier| > 0.05 or |Δaccuracy| > 0.10 or |Δlogloss| > 0.20 with
sufficient samples), else `STABLE`. WATCH = measured movement worth a
look, never a degradation verdict.

## 6. Uncertainty: Wilson + seeded bootstrap

Proportions (accuracy, hit rates, calibration frequencies) use the
Wilson score interval (fixed z=1.96, documented) — valid for small
samples and boundaries; zero trials → `null`. Scalar means (Brier) use
a seeded (`seed=7`, `n_boot=500`) percentile bootstrap — deterministic.
Point estimates are never shown without sample context.

## 7. Data quality: states, provider scope

States: `DATA_VALID` (no issues), `DATA_DEGRADED` (any blocked/degraded/
conflict/gap signal), `DATA_UNAVAILABLE` (nothing to measure),
`DATA_BLOCKED` (all blocked). Provider scope is provider × competition ×
season using actual Phase 24 `get_activation_state`; conflict counts are
global (conflicts carry no provider scope — documented per measurement).

## 8. Coverage funnel + rates

`eligible → ready → predicted → completed → evaluated` from immutable
records; rates `ready/eligible`, `predicted/ready`,
`completed/predicted`, `evaluated/completed`, each with denominator.

## 9. Anomalies: rules, severity, sample requirements

Ten deterministic rules (zero generation, coverage collapses via 30d
windowed funnels, freshness breach >48h, block/cert spikes, execution
gaps, impossible metrics, invalid probabilities, duplicate
match+cutoff snapshots), each with minimum-sample guards (default 10).
Severity INFO/WARNING/CRITICAL; deterministic `anomaly_id` hashes;
evidence attached; no root-cause inference.

## 10. API

`GET /monitoring/{overview,performance,calibration,drift,data-quality,
coverage,providers,anomalies}` — all read-only; common filters
(model/version/competition/season/dates/window); invalid ranges → 422;
empty states explicit. Verified read-only: nine endpoints return 200
without changing any prediction/evaluation/outcome row or hash.

## 11. Scheduler

No job added (see §2). Existing scheduler untouched (`ALL_JOB_TYPES`
still 8; Phase 20 count test unmodified).

## 12. Frontend

`/monitoring` page (nav: Monitoring): filters, performance section
(reused), coverage funnel, anomalies; empty/insufficient-data states.
Match page unaffected except prior phases; system page unchanged.

## 13. Limitations

Monitoring identifies measured patterns with denominators; it does not
establish causality, rank models, or recommend model changes. Small
samples are flagged, never concluded from.

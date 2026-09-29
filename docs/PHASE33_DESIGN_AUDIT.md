# Phase 33 Design Audit — Real-World Performance Evidence

**Date**: 2026-09-23 · **Baseline**: `34ca0c3` (Phase 32 CLOSED/READY) ·
Branch `main`. Alembic head: `0015_shadow_execution`. Docker: unavailable.

## 1. Reusable metric implementations

- Per-observation scoring: `prediction_evaluation/metrics.score_snapshot`
  (1X2 acc/logloss/Brier, goal errors, O/U + BTTS, exact-score).
- Aggregation means: `prediction_evaluation/aggregation._mean`,
  `summarize_evaluations` (Phase 27 record scope).
- Market/goal metric keys shared with shadow evaluations (same dicts).
- No new formulas in Phase 33; calibration reuses stored payloads.

## 2. Existing uncertainty implementations

- `production_monitoring/contracts.wilson_interval` (proportions),
  `bootstrap_mean_ci` (seeded scalar means).
- `evaluation/compare.paired_metric_difference` (paired bootstrap on
  prob triplets; used by Phase 29).
- Phase 33 reuses Wilson + seeded bootstrap on paired difference series
  (no new statistics).

## 3. Existing calibration implementations

- `backtesting/metrics.reliability_curve` + `expected_calibration_error`;
  `production_monitoring/contracts.max_calibration_error`.
- Phase 32 shadow evaluations do NOT store per-observation probabilities,
  so Phase 33 calibration recomputes curves from stored immutable
  payloads (champion Phase 26 payload + challenger shadow output +
  actual outcome). No payload mutation.

## 4/5. Champion / challenger evaluation sources

- Champion: `PredictionEvaluationRecord` (Phase 27) + embedded
  `champion_metrics` in each `ShadowEvaluationRecord`.
- Challenger: `challenger_metrics` embedded in `ShadowEvaluationRecord`.
- Pairing identity: `shadow_id`; outcome identity: `outcome_hash` +
  `MatchOutcomeSnapshot`; feature identity: `feature_snapshot_id/hash`.

## 6. Shadow pair identity

`ShadowPredictionSnapshot` row = the explicit pair (match, both
artifacts, shared snapshot, cutoff, both outputs/hashes). Phase 33
treats evaluated shadow rows as paired observations; no re-pairing by
timestamp.

## 7. Outcome identity

`outcome_snapshot_id` + `outcome_hash` on every evaluation row;
corrections supersede per Phase 27 (new outcome hash ⇒ new evidence
snapshot, old snapshots immutable).

## 8. Monitoring aggregation

Phase 28 `summarize_evaluations`, `calibration_detail`,
`drift_analysis` operate on Phase 27 records; Phase 33 does not alter
them. Evidence exposes its own read-only rollups over paired rows.

## 9. Avoided duplication

No new scoring math, no new bootstrap, no new reliability bins, no new
governance concepts, no new scheduler framework, no second shadow
abstraction. New code: cohort definition, eligibility audit, paired
assembly, evidence states, snapshot persistence, refresh job, API/CLI/
frontend surfaces.

## 10. Threshold policy (existing config)

20-observation minimum is the established convention
(`MIN_WINDOW_SAMPLE`, `MIN_DRIFT_SAMPLE`, `MIN_EVIDENCE_SAMPLE`).
Phase 33 adopts `MIN_PAIRED_EVIDENCE = 20` (inferential) with a
1–19 `DESCRIPTIVE_ONLY` band; 0 ⇒ `NO_DATA`/`INSUFFICIENT_REAL_DATA`.
Documented and versioned in contracts.

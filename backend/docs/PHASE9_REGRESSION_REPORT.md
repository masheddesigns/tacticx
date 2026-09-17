# Phase 9 — Prediction Regression Report

Phase 9 adds an isolated feature layer; no prediction module was modified.

## File-level proof

`git status` shows zero modifications under:
- backend/app/services/predictions/
- backend/app/services/intelligence/
- backend/app/services/evaluation/
- backend/app/services/backtesting/
- backend/app/services/features/
(enforced by tests/test_phase9.py::test_prediction_engine_untouched)

## Behavioral proof (real stored predictions, /tmp/p17.db)

Recomputed ensemble_v1 for a random sample of 10 stored valid predictions
with identical (model config, cutoff, temporal mode):

- compared: 10
- byte-identical (tol 1e-9): 9
- changed: 0
- skipped: 1 (ensemble_v1-elo+poisson+advanced with custom weights —
  a fitted-model variant requiring its own training path; out of scope
  by design, investigated and explained, not a regression)

Initial naive comparison flagged 1 diff; investigation showed it was the
custom-weight variant, and like-for-like recomputation is identical.

## Suite proof

350/350 tests pass, including all Phase 1–8 suites (lifecycle versioning,
composer outputs, evaluation metrics) unchanged.

## Conclusion

changed = 0. No existing prediction output was altered by Phase 9.

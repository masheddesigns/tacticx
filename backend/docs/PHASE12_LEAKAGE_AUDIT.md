# Phase 12 — Leakage Audit

## Invariants (all tested in tests/test_phase12.py)

- Future match insertion → existing dataset rows (features + labels)
  byte-identical (`test_future_match_insertion_unchanged`).
- Training scaler fit on train slice only; full-data fits never leak into
  train-only statistics (`test_testset_modification_leaves_training_untouched`,
  `test_preprocessing_train_only`).
- Calibration temperature fit on validation outcomes only; test labels never
  enter calibration (`test_calibration_never_sees_test`).
- Standardization/scaling/selection/calibration/hyperparameters/weights/
  thresholds all train- or validation-bound by construction (training.py,
  calibration.py); no code path reads test rows during fitting.
- Expanding folds cut strictly on kickoff order; season splits reject empty
  windows instead of rebalancing.

## Adversarial results

- Inserting a future 5-0 result: 0 existing rows changed.
- Modifying test rows: train scaler identical before/after.
- Calibration reports record `fitted_on: validation` with a `-cal version
  suffix kept separate from raw variants.

## Residual risks

- Researcher degrees of freedom (family/candidate choice) are controlled by
  primary/exploratory declaration + tested-candidate counts, not by code.
- The promotion gate is evidence-checked, but the final transition requires
  a recorded human decision — automation cannot perform it (tested refusal
  of `auto`/`system` deciders and empty reasons).

# Phase 14 — Leakage Audit

## Framework invariants (unchanged from Phase 12, re-verified)

- Dataset builder emits row features before ingesting the row's own data:
  inserting a future 9-0 result leaves all historical rows byte-identical
  (tested).
- Train-only scaler, validation-only temperature, kickoff-ordered folds,
  empty-window rejection — all covered by tests/test_phase14.py.
- New guard (Phase 14): shared validate/test seasons without split_date
  raise instead of contaminating calibration
  (`test_split_date_firewall`).

## Expansion-specific checks

- New 2016–2022 rows enter only chronologically earlier positions; no
  2024 test row can observe them out of order (single ordered pass).
- Backfill rid scheme is league-scoped; cross-league mapping collisions
  impossible by construction (regression-tested in Phase 13).
- Current-season rows do not exist in the dataset; splits cannot select
  them.
- Estimated families (xg/player) stay research-labeled; strict mode
  excludes them at the gate.

## Residual risks

- Stale-but-valid histories (e.g. 2015 xG informing 2024 rows) are
  temporally legal and reported via coverage, not hidden.
- Researcher degrees of freedom handled by primary/exploratory
  declaration + candidate counts (10 this phase).

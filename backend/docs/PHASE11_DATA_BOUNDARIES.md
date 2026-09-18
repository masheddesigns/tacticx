# Phase 11 — Data Boundaries

## The four datasets

| Boundary | Kickoff range | Purpose | May contain upcoming data? |
|---|---|---|---|
| historical | < 2024-01-01 | backtests, training, validation ranges | NO |
| validation | 2024 | holdout evaluation | NO |
| test | 2025–now | recent evaluation | NO |
| production | future | readiness, pre-match prediction | YES (only here) |

Cutoffs are explicit arguments (`dataset_boundary`), defaults documented.
Current/upcoming data belongs to production/live readiness and must never
enter historical backtests.

## Adversarial guarantees (tested)

- Future fixture inserted → historical backtest scope unchanged
  (scope_matches filters FINISHED + pre-cutoff by construction).
- Target/future events inserted → historical feature snapshot hash
  unchanged (repository excludes by cutoff + target id).
- New source observation → existing prediction rows byte-identical
  (no import path from acquisition to prediction storage).
- Kickoff update → old observation rows intact (append-only).
- Source removal (observations deleted) → canonical match row intact.

## Historical integrity rules

No source may rewrite historical scores, prediction snapshots, odds
observations, conflicts, or feature snapshots. Disagreement creates a new
observation → reconciliation → conflict → resolution. Canonical Match rows
advance only via the validated sync path with observation history.

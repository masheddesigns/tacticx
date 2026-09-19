# Phase 18 — Temporal Audit (current-season acquisition)

## Timestamp classes

- **Event time** (kickoff): provider-supplied per fixture, normalized to
  UTC, original preserved (`kickoff_source`, `kickoff_timezone`).
- **Effective time**: unknown for acquisition-sourced rows (no provider
  publishes it) → strict gating excludes affected features; estimated only
  where parent-anchored historical semantics apply (unchanged Phase 10 rule).
- **Retrieved time**: acquisition run `started_at`; observation
  `observed_at`.
- **Created time**: row `server_default` timestamps.

## Rules enforced (tested)

- Unknown effective time is never upgraded to known (regression-tested).
- Post-cutoff odds snapshots never enter market age or consensus
  (eligibility filters `timestamp <= cutoff`; leakage-tested).
- Closing snapshots excluded from consensus unless explicitly running a
  benchmark mode (unchanged Phase 6 behavior).
- Cutoff equality: a snapshot stamped exactly at cutoff is eligible
  (`<=`); anything after is not.
- Rescheduled kickoffs append observations; canonical identity follows
  existing resolver evidence (same match where supported).
- Live status transitions (scheduled → live → finished) append; finished
  scores are terminal for prediction snapshots (resolve_predictions
  semantics unchanged).

## Staleness behavior

Current-season rows are fresh by construction (observed this run).
Historical staleness analysis is unchanged from Phase 10; the ~9.6-year
upper bound documented there still stands for legacy rows.

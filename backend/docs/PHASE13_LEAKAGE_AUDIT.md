# Phase 13 — Leakage Audit

## Invariants

- New historical data cannot leak future information: every feature uses
  strictly earlier matches (dataset builder emits before ingesting; tested
  in Phase 12, re-verified after expansion by construction — builder
  unchanged).
- Target match events excluded: repository target-match filter unchanged.
- Future source observations excluded: cutoff-gated reads unchanged.
- Current-season records cannot enter historical tests: dataset builder
  takes only FINISHED matches; splits reject empty windows; no 2026/27
  rows exist to leak.
- Effective timing never fabricated: backfill temporal check counts
  strict/unknown rows; unknown stays unknown (46 season-slots, all
  unknown-timing for new rows).
- Backfill order invariance: reversed row import yields identical canonical
  matches/scores (tested `test_ingestion_order_invariance`).

## Ingestion-order test

Same 3 rows forward vs reversed (different rids): 3 canonical matches with
identical score sets [(0,3),(1,1),(2,0)]; 0 invalid both ways.

## Cross-league rid incident (caught during Phase 13)

A league-blind rid prefix (`fdcuk-<season>-<idx>`) let LA_LIGA rows resolve
through EPL source mappings, recording ~2000 bogus score observations.
Canonical scores were preserved by the conflict system (no overwrites),
but the conflict table was polluted on scratch. Fixed by league-scoped
rids (`fdcuk-<league>-<season>-<idx>`) + a season-window guard (≥90% of
created rows must kick off inside the season, else `imported_with_warning`),
plus a regression test. Production database untouched throughout (all work
on scratch copies).

## Residual risks

- Researcher-supplied season tags: guarded by the window check.
- Midnight kickoffs are date-only evidence (documented, never upgraded).

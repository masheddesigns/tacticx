# Phase 10 — Final Report: Production Data Coverage, Freshness & Temporal Provenance

## Architecture

source → observation (effective/retrieved/created timing) → freshness
(family policies) → temporal confidence (known/unknown/estimated status)
→ cutoff eligibility (match + feature-family gates) → feature availability.
New `app/services/freshness/` (provenance, policies, registry, fixtures,
audit, eligibility) + `match_observations` table. No model touched.

## Temporal provenance

Four timestamps with documented semantics; deterministic status classifier
(equality → pre-cutoff); estimated never shown as known. See
PHASE10_TEMPORAL_PROVENANCE.md.

## Source matrix

Measured-only matrix (see PHASE10_SOURCE_MATRIX.md): football_data_co_uk
(fixtures/results/stats/odds), statsbomb (fixtures/results/stats/events/
lineups/xG). Effective-time quality UNAVAILABLE everywhere it matters;
that single fact gates all strict eligibility.

## Current-season coverage

2026/27: all five leagues UNAVAILABLE (provider_plan_or_source_limit).
Latest stored seasons: EPL 2024, LA_LIGA 2023, SERIE_A 2023, BUNDESLIGA
2023, LIGUE_1 2023. No fixtures fabricated.

## Historical coverage

3272 matches; stats 45k rows; events 10k; lineups 28k; xG 1588; odds 36k
snapshots/7 books. Per-season slots measured per league via CLI.

## Fixture freshness

States fresh/stale/unknown/expired with defined age rules; kickoff/status/
venue changes append immutable observations (idempotent re-observation);
postponement path tested.

## Player freshness

Roster evidence parent-anchored; staleness buckets 0–7d…3+y+unknown.
EPL sample: 12 fresh / 4 recent / 39 >3y / 5 unknown (2015 rows reused for
2024 targets — valid, flagged).

## Event freshness

Statsbomb-only; same bucketing; unknown effective_at throughout.

## Lineup freshness

As player freshness (same rows). Formation present ~60%.

## xG freshness

1588 statsbomb rows, 0 strict-eligible, all estimated-eligible;
Phase 5 conclusion preserved verbatim.

## Strict eligibility

Requires known timing + resolved identity + no critical conflicts +
history. Real-data result: available where history exists, with player/xG
families honestly ineligible. Degraded mode explicit when reduced.

## Estimated eligibility

Research mode with visible estimated labels; never feeds production.

## Degraded cases

Missing xG/player data → degraded (not blocked); expired freshness →
flagged; critical conflicts → blocked (tested); insufficient history →
blocked (tested).

## Prediction regression

changed = 0. File-level gate test (no diffs under predictions/,
intelligence/, evaluation/, backtesting/, features/, player_intelligence/)
plus full suite green including all Phase 7 lifecycle tests (behavior on
clean fixtures unchanged). Eligibility only adds blocks where conflicts
exist — none on clean data.

## Leakage audit

Cutoff equality excludes; post-cutoff snapshots excluded from market age
(bug found and fixed during Phase 10); future match/score injection leaves
eligibility unchanged (tested); closing never enters consensus (Phase 6,
preserved).

## Tests

Previous: 350. New: 14. Total: 364. Passed: 364. Failed: 0. Skipped: 0.

## Performance

Status/coverage/freshness CLI <0.3s per league; eligibility check ~ms
(indexed timestamp/source/competition fields); staleness sampling bounded
(60/league). Targets met.

## Security

No credentials in logs/responses/reports/snapshots/tables (grep-audited,
plus a stored-payload secret scan in `sources validate`, 6/6 PASS).
Raw source strings never executed (ORM only, no shell).

## Limitations

- Effective_at NULL across 45k+ rows: strict player/xG features unavailable.
- Current season unavailable on tested plan; date filter dead on key.
- Staleness up to ~9.6y on reuse (flagged, not capped).
- Market overlap sparse (34 pre-kickoff matches); odds upcoming events
  exist without attachable fixtures.
- SERIE_A/LIGUE_1 lack player data entirely.

## Commit

Phase 10 commit (see git log).

## Status: READY

TacticX now knows exactly what it had, when it had it, and whether it was
eligible for a cutoff — and marks the rest unavailable rather than guessing.

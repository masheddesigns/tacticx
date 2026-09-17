# Phase 7 — Final Report: live pipeline + prediction lifecycle

## Live architecture

source (api-football fixtures / odds-api events) → upcoming discovery
(normalized UTC, original preserved) → canonical resolution (Phase 1.6
resolvers; never by spelling) → idempotent sync (metadata may advance,
predictions untouched) → historical features → eligible market → composer
(ensemble_v1, unchanged) → immutable versioned persistence → refresh on new
information (new version + neutral diff + supersede) → kickoff lock →
post-match evaluation (record only, never mutation) → rolling monitoring
(descriptive, never switching/retraining).

## Upcoming match coverage (actual, not theoretical)

- Providers verified live 2026-09-17 (6 requests total, quota-safe via cache):
  football season pull works (EPL 2024: 380 fixtures, 1 request); provider
  date filter returns 0 rows for current + historical seasons (measured,
  adapted: season fetch + local windowing); current season "2025" returns 0
  (plan/coverage limit, no errors).
- Odds feed: 1 request → 1068 snapshots / 20 upcoming events (EPL teams,
  commence times 2026-09-18/19).
- Canonical resolution of 7 real 2024 fixtures: 6 deduplicated to existing
  canonical matches (6 new api_football mappings, 0 new matches), 1 skipped
  with reason (Forest/Bournemouth name variants unresolved — correctly
  unguessed). Re-sync fully idempotent (0 created).
- Odds events resolve to 0 canonical matches (no future fixtures stored) —
  correctly unmatched, never invented. Upcoming creation from real feeds is
  therefore coverage-blocked, not code-blocked; the pipeline itself is
  validated end-to-end with controlled fixtures.

## Prediction lifecycle (actual sequence, scratch DB match 3273)

v1 generated (partial: xG unavailable, temporal verified) → repeat returns
cached v1 → refresh created v2 + diff (all-zero shifts honestly reported;
no new information existed) → v1 superseded, v1 row byte-identical →
kickoff lock verified on match 3274 → post-kickoff refresh refused →
FINISHED 2-1 → 2 evaluations (accuracy 1, LL 0.813, Brier 0.467) →
re-run idempotent (0 inserted).

## Refresh behavior

Diff payload: absolute/relative probability changes ("probability shifted"),
λ changes, market before/after + changed flag, feature became
available/unavailable/changed lists, cutoffs. v1 never overwritten.

## Market refresh

Append-only snapshots keyed by observation hash; duplicate polls return the
existing row; unknown timestamps refused (strict). Current state: latest
valid snapshot/book, consensus, representative-book overround, timeline
movement, freshness vs ODDS_REFRESH_INTERVAL_MINUTES (stale labeled, never
presented as live). Closing reported separately, excluded from consensus.

## Source health (actual)

DB-backed states + latency/quota/error columns; `record_success/failure`
transitions (healthy → degraded → unavailable); retry helper with
exponential backoff, fail-fast on 401/403 (tested: single attempt).
Per-provider rate limits (API_FOOTBALL_/ODDS_API_RATE_LIMIT_PER_MINUTE)
with global fallback. No secrets accepted, logged, stored, or served
(audited by grep).

## Prediction evaluation

evaluate_completed_predictions: finished-with-scores only; postponed/
cancelled/scheduled skipped; idempotent via unique prediction_id.
Metrics per prediction: accuracy, log-loss, Brier, goal MAE/RMSE.

## Monitoring (sample sizes stated)

Rolling 50/100 (insufficient_sample until filled), drift bands from config
(watch 0.02 / degraded 0.05 Brier delta vs reference), data-drift outcome/
goal distributions labeled diagnostic-only. No auto-switch, no retraining —
by construction (no code path exists for either).

## Tests

Previous: 288. New: 22. Total: 310. Passed: 310. Failed: 0. Skipped: 0.
Covers §48 areas: discovery/normalization/dedup/statuses, lifecycle,
cutoff, market append-only, health/retries/rate-limit, batch isolation,
evaluation, integrity, cache/stale, E2E chain, failure simulation.

## Real provider validation

Requests: 5 football (1 season pull + 4 date/season probes) + 1 odds.
Records: 380 historical fixtures, 0 current-season fixtures, 20 upcoming
odds events. Latency ~0.8–1.9s per call. Errors: none. Quota: not exposed
by providers (no remaining-count headers surfaced); caching bounds repeat
cost. No credentials exposed at any point.

## Temporal audit

Checks: future data into prediction (repo cutoff gating, inherited);
post-kickoff into pre-match (generate/refresh refuse at cutoff ≥ kickoff,
tested); closing into earlier prediction (excluded even when pre-cutoff,
tested); snapshot immutability (versions reference, never rewrite; v1
byte-identical after full chain). Issues found & fixed: naive/aware
datetime comparison in refresh + lock paths. Remaining risk: provider
timestamps are trusted as observed (unknown → refused in strict).

## Data integrity audit

Checks: canonical match uniqueness (dedup tolerance + same-day fallback,
inherited), team uniqueness (no spelling-based creation, tested),
append-only odds (hash dedup, tested), version uniqueness (monotonic
per-match numbers + input-reference cache, tested), evaluation idempotency
(unique constraint + pre-check, tested). No issues open.

## Security audit

Checks: secrets in logs/responses/artifacts (grep: only docstring mentions);
provider keys stay in provider constructors, never enter lifecycle tables,
health rows, API payloads, or CLI output. No betting, staking, or account
functionality anywhere. No issues open.

## Performance

Sync 7 records <1s; single prediction ~0.9s; batch per-match isolated;
evaluation bounded by limit; analogue/composer costs unchanged from Phase 6.
N+1 avoided: season-level fixture fetch, per-batch market reuse via
snapshots_before per match (indexed), shared Elo cache in analogues.

## Limitations

- xG strict-excluded (effective_at unknown); events/lineups unused by v1 math.
- Pre-match market coverage 34 matches; odds upcoming events exist but no
  canonical fixtures to attach them to.
- Fixture date filter dead on this key; current-season fixtures unreturned.
- MiroFish adapter-only (unchanged).
- Monitoring windows unfilled on small samples (honest insufficient_sample).
- Stale cache reused only on source failure, labeled stale.

## PHASE 8 READINESS

READY FOR PHASE 8. The lifecycle preserves an immutable chronological record
of what was known, predicted, shown by the market, and what happened —
with the validated core untouched and all safeguards tested.

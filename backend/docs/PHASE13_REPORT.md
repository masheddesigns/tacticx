# Phase 13 — Final Report: Historical Data Expansion & Feature Coverage

## Sources investigated / accepted / rejected

Investigated: football-data.co.uk (HEAD inventory 50 files), StatsBomb
open data, api-football history, odds-api history, scraping. Accepted:
football-data.co.uk only. Rejected with reasons: statsbomb (no incremental
league coverage), odds-api (no historical depth), scraping (licensing).
api-football: path-tested (32 stats + 12 events, 1 match), bulk deferred
on quota grounds. See PHASE13_SOURCE_INVENTORY.md.

## Incremental coverage

+13,367 matches (5.1×), +13,366 stats/shots populations, +13,367 odds
populations across 37 new season-slots. xG/events/lineups/players/minutes
+0 (honest: source has none of these). See PHASE13_COVERAGE_DELTA.md.

## Historical expansion

EPL 2015–2024 contiguous (10 seasons, first in dataset); LA_LIGA 2015–2023;
SERIE_A/BUNDESLIGA/LIGUE_1 2015–2023. No balanced fabrication; COVID
quirks preserved as measured.

## xG / shots / event / lineup / player-minute expansion

xG: none viable (fdcuk has no xG; api-football untested for xG, not
assumed). Shots: +13,366 populations with source definitions preserved
(HS/AST/HST/etc. via existing aliases). Events/lineups/minutes: no viable
source at quota (api-football deferred, documented).

## Temporal quality

All new rows unknown-timing (D-level); strict/estimated separation intact;
no retroactive stamping. Midnight kickoffs stay date-only evidence.

## Reconciliation / conflicts

0 new match conflicts; 444 pre-existing statistic conflicts untouched.
Cross-league rid incident caught, fixed (league-scoped rids + window
guard + regression test); canonical scores never overwritten (conflict
system proved itself under fire).

## Data quality

Per-source dimensions measured; row sanity 380/380 typical, 2 quarantined
total; pipeline odds idempotency fixed (snapshot + selection dedup).

## Dataset versions

New: research_ds_c544a413d044 (EPL, 3800 rows). Old artifacts persist
(data/research/) for comparison. Availability: EPL 2019 newly evaluable
(team 97%, xg 55%, shots 98%, player 55%); 2024 unchanged.

## Production regression

ensemble_v1, weights, calibration, registry statuses untouched (file gate
test). Existing prediction snapshots unchanged (no production DB writes;
scratch-only expansion). Optional research rerun (EPL 2019 logreg_team):
inconclusive, labeled, gates intact, no promotion.

## Ingestion-order invariance

Forward vs reversed imports produce identical canonical matches/scores
(tested). Only observation ordering metadata may differ.

## Leakage audit

See PHASE13_LEAKAGE_AUDIT.md. Dataset builder unchanged; splits reject
empty windows; no current-season rows exist to leak.

## Tests

Previous: 394. New: 13. Total: 407. Passed: 407. Failed: 0. Skipped: 0.
(Includes 1 updated Phase 16 expectation documenting the odds idempotency
fix: redelivery reuses rows.)

## Performance

Inventory <5s; per-league coverage <10s; season import 40–260s (~15k rows);
37 seasons in batches; indexed candidate generation (no full scans beyond
bounded backfill reads).

## Security/licensing

No keys/tokens/cookies committed; polite fetcher; fdcuk personal-use
license respected (runtime downloads, /tmp only); secret scans clean;
validation gate includes stored-payload scan.

## Limitations

- xG/events/lineups/minutes not expanded (no viable source).
- Current season unavailable; date filter dead on key.
- Midnight kickoffs date-only; import-time odds timestamps documented.
- api-football bulk deferred (quota).
- Expansion lives on scratch; production promotion is a separate decision.

## Commit

Phase 13 commit (see git log).

## Status: READY

More independently useful, correctly identified, semantically defined,
temporally defensible observations: +13,367 matches meeting that bar.

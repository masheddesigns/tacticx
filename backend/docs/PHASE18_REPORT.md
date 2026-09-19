# Phase 18 — Final Report: Live Match Universe & Current-Season Acquisition

## Architecture

`app/services/acquisition/current_season.py` orchestrates the existing
pipeline (discovery → raw observation → normalization → identity →
canonical resolution → validation → append-only observation → universe).
One additive status-map extension in `lifecycle/sync.py` (live/abandoned
no longer collapse to SCHEDULED). No prediction/model code touched.

## Current-season mapping

Versioned table (`SEASON_MAP_VERSION = 1`): api-football "2026" ↔
canonical "2026/27" per competition with validity windows. Provider
numbering never assumed equal; unmapped lookups return None.

## Source matrix

Measured-only matrix documented in PHASE18_SOURCE_MATRIX.md. api-football:
reachable, historical seasons retrievable, 2026/27 empty. Odds API:
reachable, events unattributable to leagues, fixture-source use refused.

## Provider validation

4 quota-safe api-football requests + 1 cached odds request. Real EPL 2024
season-windowed fetch: 380 records, 0 created (all known), 684
observations appended, idempotent rerun. Unresolved teams
(e.g. Nottingham Forest naming) quarantined, never merged.

## EPL / La Liga / Serie A / Bundesliga / Ligue 1

Five-league orchestration with per-league isolation verified by mock
matrix (success/partial/failed) and by real run
(`acquire --season current`: all leagues success, 0 created — no
2026/27 data exists at any source, honestly reported).

## Fixture coverage

Current-season canonical fixtures: 0 (no source provides them).
Historical coverage unchanged (3,272 + Phase 13 expansion intact).

## Status normalization

Extended taxonomy (scheduled/postponed/cancelled/abandoned/live/
finished/unknown) with documented per-source maps; unmapped → unknown.

## Identity resolution

Existing resolvers only; ambiguous identities quarantined (tested);
cross-league ID collisions guarded by league-scoped resolution (tested).

## Temporal provenance

Effective/retrieved/created tracked separately; unknown never upgraded
(see PHASE18_TEMPORAL_AUDIT.md).

## Reconciliation

Phase 8 `reconcile_league` runs per league in validation; conflicts
persist; genuine conflicts never auto-resolved; idempotent reruns create
no duplicate conflicts (tested).

## Match Universe

Existing read-view reused; readiness splits fixture/identity/history/
market/eligibility (tested: fixture present + history insufficient →
explicitly ineligible).

## Prediction eligibility

Phase 10/11/17 rules unchanged and enforced; current fixture availability
does not imply readiness (tested).

## Market linkage

Odds events link only on resolved identity + kickoff tolerance; else
retained unmatched (tested: 0 fabricated mappings in real run).

## Acquisition runs

Append-only `AcquisitionRun` rows with counts + classifications; CLI
`acquire --season current [--competition X] [--source Y]` is deterministic
and scheduler-callable.

## CLI

`tacticx acquire` (new) + existing `readiness` reused for per-match
readiness. Source allowlist rejects arbitrary providers.

## API

`GET /api/v1/matches/current` (competition/status/date/eligible filters,
paginated, no raw payloads) + `GET /api/v1/acquisition/status` (health +
recent runs, no credentials).

## Scheduler readiness

`acquire` is a pure function of (season, competition, source) with
machine-readable outcomes — callable by any external scheduler as-is.

## Leakage audit

Future status updates, post-match scores, post-cutoff odds, provider
reorder, and historical-integrity cases all tested green; intelligence
hashes byte-identical before/after.

## Historical integrity

Match/prediction/odds counts and intelligence hashes unchanged by
acquisition activity (tested).

## Performance

Mock acquisition <0.1s/league; real EPL season fetch 0.9s/380 records;
readiness ~ms per match; reruns faster (dedupe path); no N+1 beyond
existing indexed patterns.

## Security

No credentials in code/logs/API/CLI/tables (audited + tested); endpoints
from trusted config only (CLI allowlist tested); ORM-only writes;
bounded acquisition (league list finite, run-limited queries).

## Tests

Previous: 462. New: 20 (`test_phase18_current_season.py`). Total: 482. Passed: 482. Failed: 0. Skipped: 0.

## Production regression

Prediction/model/feature/odds/history byte-identical (tested); model
versions, backtests, snapshots untouched. The single `sync.py` change is
acquisition-layer status preservation, covered by new + existing tests.

## Documentation

PHASE18_REPORT.md (this file), PHASE18_CURRENT_SEASON.md,
PHASE18_SOURCE_MATRIX.md, PHASE18_TEMPORAL_AUDIT.md.

## Limitations

- No 2026/27 fixtures exist at any configured source (measured, not fatal).
- Odds events unattributable without league context (by design).
- Team-name variants (e.g. Nottingham Forest) quarantine until mapped.
- Scheduler itself out of scope (registry-ready only).

## Commit

(Reported after push.)

## Status: READY

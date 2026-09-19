# Phase 19 — Provider Qualification Matrix (measured 2026-09-19)

Capabilities use measured | documented | unknown | unavailable.
Nothing below is claimed without an actual validating request.

## api_football — REJECTED (authentication_failure, 403 on fixtures)

- Reachable: yes (HTTP 403, not a timeout).
- Fixtures/results/statuses/timestamps/teams for EPL 2026/2024: 0 rows.
- Current season 2026/27: unavailable.
- Note: an earlier environment state returned 200s; the present key/plan
  returns 403 on `/fixtures`. Recorded as measured, not as "broken":
  re-qualify if credentials change. Requests used: ≤3.
- Level: D (rejected). Canonical selection: none.

## odds_api — REJECTED for fixtures (authentication_failure, 401)

- Reachable: yes (HTTP 401 on odds endpoint).
- Events/odds content: unmeasured (auth blocks observation).
- Role assessment: market-only (Level C) even when healthy — the feed
  carries no league attribution and must never become fixture authority.
- Requests used: 1 (+1 cached re-read, no quota cost).

## football_data_co_uk — Level A (standing, from Phase 13 evidence)

- Fixtures/results/statistics/closing odds measured across 5 leagues.
- Closing-only market role; effective timestamps unknown (strict gating).
- Not re-probed live in Phase 19 (bulk CSV path, no quota to spend).

## Theoretical adapters

No speculative adapters implemented. No fake availability claimed.

## Quota accounting

Total live provider requests this phase: ~6 (api-football) + 1 (odds).
No repeated probing of known-bad filters. No quota exhaustion.

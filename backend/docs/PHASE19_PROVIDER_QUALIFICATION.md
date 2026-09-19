# Phase 19 — Provider Qualification Framework

## Levels

- **LEVEL A — canonical fixture source**: competition + season
  identification, stable fixture IDs, home/away teams, kickoff
  timestamps, status, repeatable retrieval, resolvable identity. Temporal
  provenance is *reported*, not gated (fixture kickoffs are event times;
  strict eligibility of derived features is enforced downstream).
- **LEVEL B — supplementary**: stats/events/lineups/players/xG; never
  trusted for canonical fixture creation.
- **LEVEL C — market**: odds only; never fixture authority.
- **LEVEL D — rejected**: inaccessible, unsupported, empty, unstable,
  unlicensed, unattributable, unreliable, or ambiguously mapped.

## Qualification verdict

`status` ∈ qualified / partially_qualified / unavailable / rejected,
plus `reason_codes[]`, coverage counts, temporal buckets, capabilities,
and evidence (request_count ≤ 5, response_count, sample_hash,
measured_at, repeatability flag). Verdicts persist append-only
(`source_qualifications`); re-runs append, never overwrite.

## Field authority (defaults, persisted per plan)

fixture_identity/kickoff/status/result → api_football;
statistics → football_data_co_uk; events/lineups/players → api_football;
odds → odds_api; closing_odds → football_data_co_uk; xG → none.
No global source ranking exists.

## Fallback discipline

Ordered attempts with classified outcomes. Fallback on unavailable /
malformed / rate-limited / partial; optional on empty (plan-gated);
never on auth failure or unsupported axes. Previous observations are
never deleted on switch; conflicts persist; predictions untouched.

## Acquisition plans

Deterministic by (registry, qualification, season, competition); content
hash proves it. Supplementary/market sources never silently promote to
canonical selection.

## Health, freshness, runs

Extended health (HTTP status, consecutive failures, backoff, sizes,
counts, last qualification; new states disabled/unqualified/schema_error;
single failure never auto-disables). Freshness per source/competition
from configured intervals, unknown when unconfigured. Runs log
requests/successes/failures/rate-limits/observations/duplicates/matches/
identity/conflicts/duration with no destructive writes.

# Phase 31 Data Acquisition

## Providers

| Provider | Auth | Role | 2026/27 (measured 2026-09-23) |
|---|---|---|---|
| api_football | `FOOTBALL_API_KEY` (`x-apisports-key`) | fixtures/teams | Reachable; EPL 2024 = 380 rows; 2025/2026 = 0 rows → UNAVAILABLE |
| odds_api | `ODDS_API_KEY` (query) | markets only | Reachable; 1079 soccer_epl market rows; not fixtures |
| football_data_co_uk | none (bulk CSV) | historical + current results | 2627/E0.csv = 50 played, 0 future fixtures |

## Qualification → activation

Verdicts `qualified/partially_qualified/unavailable/rejected`
(8 Level-A requirements). Activation `UNAVAILABLE→…→QUALIFIED→ACTIVE`
(`QUALIFIED ≠ ACTIVE` invariant); only ACTIVE triggers acquisition.
Measured: api_football REJECTED (fixtures), odds_api REJECTED
(fixtures)/Level-C (markets), football_data_co_uk Level-A historical.

## Acquisition jobs (existing, reused)

`fixture_refresh`/`status_refresh` (30m–6h), `result_refresh` (6h),
`source_health` (4h), `freshness_audit` (6h), `qualification` (7d),
`pre_match_prediction` (30m), `post_match_evaluation` (1h). Intervals
are per-job config, environmentally documented; the loop honors them
via `is_due`.

## Rate limits & retries

Global `PROVIDER_MAX_REQUESTS_PER_MINUTE=25` + per-provider overrides;
in-memory token buckets. Retries bounded (`PROVIDER_RETRY_ATTEMPTS=4`,
exponential base 1s, honors `Retry-After`); 4xx fail fast (quota-saving).
Failure codes: `authentication_failure`, `authorization_failure`,
`rate_limited`, `temporary_failure`, `provider_schema_error`,
`validation_failure`, `provider_empty`, `provider_5xx`,
`provider_timeout`, `provider_malformed`. No retry-forever anywhere.

## Failure states & provenance

Every match/observation carries provider, provider IDs, collected/
published/effective timestamps, parser version, temporal quality, job
identity. Raw records append-only; canonical rows resolved by
`uq_match_provider` + conflict-aware scores (never blind overwrite).
Late data cannot mutate executed predictions (hash-pinned snapshots).

## Temporal handling

`kickoff_at` (event time) vs `collected_at`/`retrieved_at` (observed)
vs `effective_at` (true-from). Pre-match path admits only
`kickoff < cutoff` records; `cutoff < kickoff` strictly enforced;
FINISHED-with-future-kickoff counted as suspicious, not used.

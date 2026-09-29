# Phase 31 Operations Guide

## Daily checks

1. `tacticx system status` — env, flags, DB reachable, migration version.
2. `tacticx providers status` — per-provider health + activation per
   competition (expect honest UNAVAILABLE with reasons where applicable).
3. `tacticx jobs status` + `tacticx jobs dashboard` — recent runs,
   failures, locks.
4. `tacticx acquisition status` — season mode, fixture/prediction/blocked
   counts.
5. `tacticx monitoring summary` — coverage, accuracy, anomalies.

## Provider failures

401/403 → check key/plan; system records `authentication_failure` and
backs off (no hammering). 429 → `rate_limited`, honors `Retry-After`.
5xx/timeout → bounded retries. Malformed → `provider_schema_error`,
quarantined raw kept. Recovery: next due cycle retries automatically;
verify via `jobs status`.

## Stale data

`freshness_audit` hourly; `sources freshness` shows staleness
distribution; `monitoring summary` surfaces freshness warnings.
Stale fixtures never block readiness silently — they produce explicit
`STALE_FIXTURE_AWAITING_SYNC` reasons.

## Blocked matches

`tacticx pre-match summary` lists blocking reasons. BLOCKED is a valid
terminal verdict, not an error. Investigate via `pre-match audit
<match_id>`; fix data, re-evaluate (new certificate, old one kept).

## Scheduler failures

`jobs status` shows terminal FAILED rows with error codes; locks expire
by TTL and `jobs locks cleanup` reclaims strays. Restarting the
scheduler container is always safe (idempotent re-runs).

## Database failures

API `/ready` → 503 `unhealthy`; scheduler jobs fail safely without
state corruption; Redis-dependent paths degrade to memory. On recovery:
verify `/ready` ok, run `jobs run-due`, confirm no duplicate counts.

## Backup/restore

Nightly `backup_postgres.sh` (cron example in Phase 22 docs); restore
with `restore_postgres.sh` (sha256-verified, single transaction);
`verify_backup_restore.sh` checks table counts ≥50 and hash stability
of predictions/outcomes/certificates/governance records.

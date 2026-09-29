# Phase 35 Report — Continuous Real-World Observation & Production Soak

## 1. Executive Summary

Phase 35 puts the existing pipeline under continuous-observation
discipline without changing models, governance, or thresholds. The
system honestly reports zero eligible real fixtures, zero real
predictions, and zero paired observations — the correct outcome given
measured provider states. All durability properties (idempotency,
restart recovery, backup/restore, failure handling) verified at the
service level; Docker runtime remains unavailable on this machine.

## 2. Runtime Environment

- Docker: unavailable (boundary carried, not claimed).
- Compose: `docker-compose.local.yml` statically validated (YAML +
  contract tests); existing stacks untouched.
- PostgreSQL: 16.14 native — migration head 0017 verified; backup →
  restore into isolated DB verified (71/71 tables, version intact).
- Redis: architecture unchanged (cache/broker/probe; memory fallback).
- API: healthy; `/ready` reports DB + additive migrations key.
- Scheduler: loop mechanics proven via repeated `run-due` cycles
  (cycle 1 executes due jobs; cycles 2+ correctly report nothing due).
- Frontend: builds; Operations page extended with funnel section.

## 3. Runtime Validation

`jobs run-due --dry-run` across all 10 job types; two consecutive live
cycles with no duplicate writes; lock acquire/block/reclaim/expiry
exercised; `--loop` flag added for the container scheduler.

## 4. Scheduler Validation

Locks (TTL + stale reclamation), terminal append-only records,
dry-run idempotency, unconfigured-challenger skip paths, guarded
manual runs. No new job types.

## 5. Provider Availability (re-checked 2026-09-23)

| Provider | Competition | Season | Qualification | Activation | Fixtures | Results |
|---|---|---|---|---|---|---|
| api_football | EPL | 2024 | reachable (380 rows) | UNAVAILABLE (current) | 2026/27: 0 | n/a |
| api_football | EPL | 2025/2026 | reachable, empty | UNAVAILABLE | 0 | n/a |
| odds_api | soccer_epl | current | reachable (1079 market rows) | n/a (markets only) | n/a | n/a |
| football-data.co.uk | E0 | 2627 | Level-A historical | n/a (CSV) | 0 future | 50 played |

Reachability ≠ fixture availability (verified, not assumed).

## 6. Real Fixture Acquisition

50 real 2026/27 EPL results re-verified present via CSV (played only);
0 upcoming fixtures at every measured source. No synthetic fixtures
created anywhere in production paths.

## 7. Production Prediction Observations

0 real (no eligible fixtures). Pipeline preserved and tested on
isolated fixtures; champion binding unchanged.

## 8. Shadow Observations

0 real. Scheduler `shadow_prediction` without configured challenger
reports clean `skipped`; NO_ELIGIBLE_MATCHES valid end-to-end.

## 9. Outcome Observations

0 new real outcomes (no real predictions to resolve). Finished-state
handling + supersession covered by existing suites.

## 10. Evaluation Observations

0 new real evaluations. Verified-outcome linkage asserted on isolated
lifecycle tests.

## 11. Evidence State

NO_DATA on empty production database (API + CLI verified);
paired/excluded accounting tested with ledger codes.

## 12. Candidate Validation State

INSUFFICIENT_DATA by construction at zero pairs (no thresholds
changed, no candidates altered).

## 13. Soak Results

Session-bounded soak (no multi-day run possible here): provider probes
(<60s provider time, within limits), scheduler cycles, restart
simulations, backup/restore cycle. No duration claimed beyond what ran.

## 14. Restart / Recovery Results

Lock expiry + reclaim, prediction/shadow/evaluation replay identity,
run-due stability across cycles, Redis memory fallback, API 503/healthy
separation — all passing.

## 15. Backup / Restore Results

pg_dump → gzip + sha256 → restore to isolated DB → 71/71 tables,
alembic head 0017 intact. Production data untouched (scratch DBs only).

## 16. Security Results

No `.env` tracked; no secret literals in new code/compose/docs;
`diagnose()` presence-only; log redaction helper tested; existing
security checks untouched.

## 17. Regression Results

Backend 1104 passed / 1 pre-existing (Phase 18). Frontend 43/43 +
build. Ruff: no new debt. Golden values unchanged. One Phase 20 CLI
test needed defensive `getattr` for the new `--loop` flag (no test
logic changed).

## 18. Real-World Observation State

NO_ELIGIBLE_MATCHES (0 real upcoming fixtures) — valid operational
outcome; scheduler healthy and polling.

## 19. Changed Files

- New: `backend/app/services/observation/` (contracts, lifecycle),
  `backend/app/api/routes/operations.py`,
  `backend/tests/test_phase35_soak.py`,
  `docs/PHASE35_REPORT.md`
- Modified: `backend/scripts/tacticx.py` (loop flags, 6 status
  commands), `backend/app/config.py` (flavor + switches),
  `backend/app/api/routes/health.py` (additive migrations key),
  `backend/app/main.py` (operations router),
  `frontend/.../OperationsPage`, api client/queries, tests,
  `.env.example`

## 20. Commit Hash

(to be filled after commit)

## 21. Final Status

- Operational: READY (with Docker runtime boundary)
- Real-world observation: NO_ELIGIBLE_MATCHES
- Evidence: NO_DATA
- Validation: INSUFFICIENT_DATA
- Governance: UNCHANGED

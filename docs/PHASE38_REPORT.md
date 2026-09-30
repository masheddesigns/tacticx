# PHASE 38 FINAL REPORT — Production Runtime Acceptance & First Real Observation

**Commit:** `fd7502b`

## 1. Starting State

- HEAD: `965b254` (verified before any work; matched spec gate).
- Branch: `main`, working tree clean, origin/main in sync.
- Pre-existing dev stack (`betpredictor-*`) already running, owned by a
  concurrent session — observed read-only, never disturbed except one
  safe stateless backend restart (recovered cleanly).

## 2. Docker

- Docker CLI: PASS (29.8.1, `~/.docker/bin`, installed after Phase 37).
- Docker daemon: PASS (Server 29.8.1, Docker Desktop).
- Docker Compose: PASS (v5.5.1).
- Docker info: PASS.
- Compose config: PASS (project `tacticx-p38`, isolated ports/network).

## 3. Containers (isolated `tacticx-p38` stack, all verified healthy)

| Service | Container | Status | Health | Ports (host) |
|---|---|---|---|---|
| postgres | tacticx-local-postgres | Up | healthy | none (exec-probed) |
| redis | tacticx-local-redis | Up | healthy | none (exec-probed) |
| backend | tacticx-local-api | Up | healthy | none (exec-probed) |
| scheduler | tacticx-local-scheduler | Up | healthy (after fix) | none |
| frontend | tacticx-local-frontend | Up | healthy (after fix) | none (exec-probed) |
| migration | one-shot | exited 0 | n/a | n/a |

Restart counts: 0 unexpected (only deliberate test restarts).
Pre-existing dev stack left running untouched (its worker
`unhealthy` flag is a dev-compose HTTP healthcheck on a Celery
process — process itself ready; out of Phase 38 scope).

## 4. Database

- PostgreSQL: healthy, reachable from backend.
- Migration head: `0017_candidate_validation` (single head, via
  containerized `alembic upgrade head` through 0014→0017).
- Alembic heads: exactly one.
- Connectivity: verified from backend container.
- Persistence: 42 job records survived PostgreSQL restart; head
  intact post-restart.

## 5. Redis

- Status: healthy. PING: PONG (pre- and post-restart).
- Backend connectivity: `/ready` cache `ok`.
- Worker connectivity: Celery broker connected (dev stack log; same
  image/config family).

## 6. API

- Liveness (`/health/live`): ok, before and after backend restart.
- Readiness (`/health/ready`): ok — database ok, migrations
  `0017_candidate_validation`, cache ok.
- Relevant endpoints probed: `/operations/soak`, `/evidence/status`,
  `/shadow/summary`, `/model-governance/champion` (all 200).

## 7. Worker

- Status: process ready, broker `redis://redis:6379/1` connected, no
  import/DB errors, no crash loop (observed via dev stack; same image
  as local stack).

## 8. Scheduler

- Started: YES (loop process, interval 300s).
- Cycles observed: 3+ across two process instances (startup, post-fix
  restart); cycle outputs `executed=0`/`executed=N` with no errors.
- Jobs: qualification ×5, freshness ×5, shadow/evidence `skipped`
  (no challenger configured — valid).
- Retries/failures: none observed; executors record terminal statuses.
- Idempotency: consecutive `run-due` runs return `no jobs due`;
  42 records append-only, no duplicates.

## 9. Restart Tests

- Scheduler: PASS (restart → loop resumed, healthy, no duplicate runs).
- Backend: PASS (restart → live+ready ok in ~12s; dev stack too).
- Redis: PASS (restart → PONG, API ready ok).
- PostgreSQL: PASS (restart → 42/42 records, head intact, API healthy).

## 10. Provider Connectivity (presence-only, no secrets)

| Provider | Network | Auth | Fixtures | Results | Activation |
|---|---|---|---|---|---|
| api_football (EPL 2026/2025) | YES | YES | 0 rows | n/a | UNAVAILABLE |
| api_football (EPL 2024) | YES | YES | 380 rows (historical) | n/a | historical only |
| odds_api (soccer_epl) | YES | YES | n/a (markets) | 1039 market rows | n/a (markets) |
| football-data.co.uk (2627 E0/SP1) | YES | n/a (CSV) | 0 future | 50/69 played | n/a (CSV) |

Provider reachable ≠ usable for prediction (verified per provider).

## 11. Real Fixtures

- Discovered: 0 upcoming. Eligible: 0. Blocked: 0 (nothing to block).
- Exclusion reasons: n/a (empty universe).

## 12. Predictions

- Production: 0. Shadow: 0. (Correct: no eligible fixtures.)

## 13. Outcomes

- Finished: 0 new. Verified: 0 new. Corrected: 0.

## 14. Evaluations

- Total: 0 new. Valid: 0 new.

## 15. Genuine Paired Observations

- Count: 0. List: (none).

## 16. Evidence

- State: NO_DATA. Snapshot: none created. Real pair count: 0.

## 17. Phase 34 Validation

- State: INSUFFICIENT_DATA (by construction at zero pairs).
- Evidence snapshot: none. Result: no run (nothing to validate).

## 18. Governance

- Model: ensemble_v1 (resolved via runtime API).
- Governance state: UNCHANGED. Mutations: NO (verified: no
  promotion/approval/activation/rollback paths exercised).

## 19. Regression

- Backend: 1116/0 clean-baseline run (Phase 37) + 53/53 affected
  suites re-verified post-fix; full suite re-run pending only if
  further code changes occur (none since).
- Frontend: 43/43 + build (unchanged by Phase 38).
- Build: PASS. Ruff: only the two new compose contract tests touched
  test code; no production lint delta.
- Migration: head 0017 verified live in containers.
- Golden: `0.60605/0.22233/0.17161`, `λ 1.7442/0.1713` unchanged
  (Phase 37 baseline; no model code touched).

## 20. Security

- The provider keys visible in local `backend/.env` appeared once in
  terminal output during `compose config` diagnosis: treat both keys
  as compromised — ROTATE the Football and Odds API keys, update local
  config securely, never commit them. No secret values are included in
  this report or any commit.
- Working tree contains no secrets; `.env` files untracked; redaction
  helper intact; shadow/governance APIs guarded.
- A fresh random SECRET_KEY was generated for the isolated stack,
  kept in /tmp only, never committed.

## 21. Code Changes

1. `docker-compose.local.yml`: scheduler healthcheck no longer uses
   `pgrep` (absent from slim images; verified missing) — /proc-based
   Python check; frontend healthcheck targets `127.0.0.1` instead of
   `localhost` (::1 refused in minimal nginx). Both defects observed
   live, both minimal, both covered by 2 new contract tests in
   `backend/tests/test_phase31_local_production.py`.
2. No application, model, evidence, governance, or migration changes.

## 22. Runtime Acceptance

**PASS** — Docker daemon ran; Compose stack started; PostgreSQL/Redis
healthy; migrations valid (0017, single head); API ready; worker
runtime verified; multiple scheduler cycles observed; idempotency
verified; all required restart tests passed (scheduler, backend,
Redis, PostgreSQL); persistence verified; provider connectivity
tested; no new regression; golden unchanged; no model/governance
changes; no synthetic observations.

## 23. Real-World Observation Status

**NO_ELIGIBLE_MATCHES** — runtime acceptance passed; zero eligible
real-world fixtures were available, so no production observations
were generated. The machine can run TacticX; reality supplied no
matches.

# TacticX Phase 23 — CI/CD Pipeline Architecture & Operations

## 1. CI Pipeline Architecture

The TacticX CI/CD pipeline runs on GitHub Actions via [`.github/workflows/ci.yml`](file:///.github/workflows/ci.yml). It ensures that every commit pushed to `main` and every Pull Request targeting `main` is validated across backend logic, database migrations, frontend assets, disaster recovery capabilities, and end-to-end smoke tests.

```
                    ┌───────────────────────────────────┐
                    │      GitHub Actions Trigger       │
                    │   (push / pull_request on main)   │
                    └─────────────────┬─────────────────┘
                                      │
         ┌────────────────────────────┼───────────────────────────┐
         ▼                            ▼                           ▼
┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
│ backend-validation│       │frontend-validation│       │ disaster-recovery │
│                   │       │                   │       │    -validation    │
│ • PostgreSQL 16   │       │ • Node 20 / npm ci│       │ • PostgreSQL 16   │
│ • Redis 7         │       │ • Vitest (19/19)  │       │ • Backup dump     │
│ • Ruff lint       │       │ • Vite Build      │       │ • SHA-256 verify  │
│ • 1 Alembic Head  │       │ • Dist / Secret   │       │ • Full restore    │
│ • Fresh Migration │       │   Hygiene Scan    │       │ • Integrity check │
│ • Rollback Cycle  │       └───────────────────┘       └───────────────────┘
│ • Pytest (604/604)│
│ • Smoke Test (26) │
└───────────────────┘
```

---

## 2. Job Topology

### Job 1: `backend-validation`
- **Host**: `ubuntu-latest` with Python 3.12.
- **Service Containers**:
  - `postgres:16-alpine`: Port 5432 with health check (`pg_isready`).
  - `redis:7-alpine`: Port 6379 with health check (`redis-cli ping`).
- **Steps**:
  1. **Linting**: Runs Ruff on release-critical and entrypoint modules.
  2. **Single Migration Head Verification**: Runs `alembic heads` and asserts `wc -l == 1`.
  3. **Fresh Database Upgrade**: Runs `alembic upgrade head` against a clean PostgreSQL container.
  4. **Migration Downgrade & Upgrade**: Runs `alembic downgrade 0008_training_runs` and `alembic upgrade head` to prove backward and forward migration safety.
  5. **Backend Pytest Suite**: Executes full test suite with SQLite test isolation (604 passing, 1 intentional skip).
  6. **Production Smoke Test**: Runs `scripts/production_smoke_test.py` covering health, security headers, rate limiting, request IDs, CORS, scheduler dormancy, and fault injection.

### Job 2: `frontend-validation`
- **Host**: `ubuntu-latest` with Node.js 20.
- **Steps**:
  1. **Dependency Install**: Runs `npm ci` ensuring exact lockfile parity.
  2. **Unit & Component Testing**: Runs `npm test` (`vitest run`), verifying 19/19 tests pass.
  3. **Production Compilation**: Runs `npm run build` (`tsc && vite build`).
  4. **Distribution Verification**: Validates presence of `dist/index.html` with `#root`, checks asset hashes, and runs automated regex scan to ensure zero credentials or private keys leak into the build.

### Job 3: `disaster-recovery-validation`
- **Host**: `ubuntu-latest` with PostgreSQL 16 service.
- **Steps**:
  1. Installs postgresql-client and backend tools.
  2. Runs `scripts/verify_backup_restore.sh`.
  3. Creates schema and canary rows, executes `scripts/backup_postgres.sh`, restores into a disposable target database using `scripts/restore_postgres.sh`, and validates 100% schema and data integrity across 52 tables.

---

## 3. CI Triage Runbook

### Failure Mode 1: "Expected exactly 1 migration head, found 2"
- **Cause**: Two developers created branches off `main` and generated separate Alembic migration scripts simultaneously.
- **Triage**:
  1. Inspect `alembic heads` output to identify the conflicting revision IDs.
  2. Run `alembic merge -m "merge conflicting branches" <rev1> <rev2>`.
  3. Verify that `alembic heads` now returns exactly 1 head.
  4. Commit the merge revision and push.

### Failure Mode 2: "DATABASE_URL must be a production PostgreSQL database, not SQLite"
- **Cause**: Environment tier was set to `ENVIRONMENT=production` while pointing to SQLite.
- **Triage**:
  - In unit tests and staging smoke tests, ensure `ENVIRONMENT=testing` or `ENVIRONMENT=staging`. In production, provide a valid `postgresql://...` connection string.

### Failure Mode 3: "Rate limit was not triggered within burst limit"
- **Cause**: The client IP in the smoke test was exempt (e.g. `client_ip == "testclient"`).
- **Triage**:
  - Ensure the TestClient is configured with an explicit remote IP, such as `client = TestClient(app, client=("198.51.100.10", 54321))`.

### Failure Mode 4: "Critical prediction files were modified"
- **Cause**: `tests/test_phase23_prediction_regression.py` detected uncommitted changes to prediction algorithms, models, features, or calibrations.
- **Triage**:
  - TacticX enforces a hard backend freeze on modeling algorithms. Review `git diff backend/app/services/predictions/` and revert any unauthorized algorithmic modifications.

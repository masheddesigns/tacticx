# TacticX Phase 23 — Production Release & Rollback Runbook

## 1. Release Overview & Versioning

TacticX releases follow Semantic Versioning (`MAJOR.MINOR.PATCH`).

Every production release build embeds non-sensitive metadata accessible via `GET /api/v1/version` and `GET /`:
```json
{
  "service": "tacticx-backend",
  "version": "0.1.0",
  "commit": "6a0bafb",
  "build_date": "2026-09-19T11:00:00Z",
  "environment": "production"
}
```

### Environmental Variables for Build Identification
- `APP_VERSION`: Release version string (default: `0.1.0`)
- `GIT_COMMIT_SHA`: 7-char short commit hash from CI build trigger
- `BUILD_DATE`: ISO 8601 UTC timestamp of container image creation
- `ENVIRONMENT`: Target environment tier (`production`, `staging`, `testing`)

---

## 2. Pre-Release Checklist

Before deploying a release to staging or production:

1. **GitHub Actions CI Status**: All workflow jobs must be green on `main`:
   - `backend-validation` (Ruff, Alembic single head, PostgreSQL migration cycle, pytest, smoke test)
   - `frontend-validation` (npm test, npm run build, secret scan)
   - `disaster-recovery-validation` (backup, restore, integrity verification)
2. **Database Migration Safety Check**:
   - Run `alembic heads` to ensure strictly 1 migration head exists.
   - Run `scripts/backup_postgres.sh` to take a snapshot of the production database prior to release.
3. **Smoke Test Execution**:
   - Run `python scripts/production_smoke_test.py` against the staging deployment before promoting to production.

---

## 3. Production Deployment Procedure

In production, **never** allow application containers to run automatic schema migrations on startup (to prevent replica migration races and lock contention).

### Standard Rollout Sequence

```bash
# 1. Take snapshot backup of production database
./scripts/backup_postgres.sh

# 2. Pull target release container images
docker compose -f docker-compose.prod.yml pull

# 3. Execute database migration job as a dedicated one-off container
docker compose -f docker-compose.prod.yml run --rm migration

# 4. Perform rolling restart of backend replicas
docker compose -f docker-compose.prod.yml up -d --no-deps --scale backend=2 backend

# 5. Verify backend health probes
curl -f http://localhost:8000/health/live
curl -f http://localhost:8000/health/ready

# 6. Update frontend web tier
docker compose -f docker-compose.prod.yml up -d --no-deps web

# 7. Execute production smoke test against the live stack
python scripts/production_smoke_test.py --backend-url http://localhost:8000 --frontend-url http://localhost:3000
```

---

## 4. Application Rollback Runbook

If the application fails health checks, returns elevated HTTP 5xx errors, or smoke tests fail after rollout:

### Fast Application Rollback (Zero Schema Change)

If the database schema has not changed or the migration is backward-compatible:

```bash
# 1. Point deployment to previous container image tag
export IMAGE_TAG="previous-stable-tag"

# 2. Re-deploy application containers
docker compose -f docker-compose.prod.yml up -d --no-deps backend web

# 3. Verify previous version is active
curl http://localhost:8000/api/v1/version
```

### Full Application & Database Schema Rollback

If the release included an Alembic migration that must be rolled back:

```bash
# Option A: Clean Alembic Downgrade (Preferred for non-destructive additive changes)
docker compose -f docker-compose.prod.yml run --rm migration alembic downgrade <target_previous_revision>

# Option B: Restore Pre-Deployment Snapshot (Required for data corruption or catastrophic failure)
# 1. Stop backend application containers to prevent further writes
docker compose -f docker-compose.prod.yml stop backend scheduler

# 2. Execute restore script with pre-deployment backup archive
./scripts/restore_postgres.sh ./data/backups/tacticx_backup_pre_release.sql.gz

# 3. Roll back backend image and restart services
docker compose -f docker-compose.prod.yml up -d
```

---

## 5. Emergency Operational Stop Sequence

If anomalous behavior occurs in acquisition, scheduler, or background jobs:

1. **Stop Scheduler Process Immediately**:
   ```bash
   docker compose -f docker-compose.prod.yml stop scheduler
   ```
2. **Reclaim All Active Locks**:
   If an administrator needs to clear stranded locks without restarting the database:
   ```bash
   docker compose -f docker-compose.prod.yml exec backend python -c "
   from app.db.session import get_session_local
   from app.services.scheduler.store import cleanup_expired_locks
   session = get_session_local()()
   cleaned = cleanup_expired_locks(session)
   print(f'Cleaned {cleaned} locks')
   session.close()
   "
   ```
3. **Enforce Operational Mutation Lockdown**:
   Verify that `ENABLE_OPERATIONAL_ENDPOINTS=false` is set in the production environment. Any manual mutation attempts via HTTP will receive HTTP 403 Forbidden.

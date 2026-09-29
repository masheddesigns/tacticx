# Phase 31 Local Deployment Guide

## 1. Prerequisites

- Docker Engine + Docker Compose v2 (not verified on the build machine;
  install Docker Desktop or engine before proceeding).
- 4 GB RAM, 10 GB disk for volumes.
- Provider API keys (optional; system runs honestly without them).

## 2. .env setup

```bash
cp .env.example .env
# Edit .env: POSTGRES_PASSWORD, SECRET_KEY (>=32 chars), provider keys.
# Never commit .env (gitignored). Never use defaults in production.
```

Required variables: `POSTGRES_USER/PASSWORD/DB`, `SECRET_KEY`,
`DATABASE_URL` is composed by the stack; provider keys
`FOOTBALL_API_KEY`, `ODDS_API_KEY` optional. Phase 31 additions:
`TACTICX_ENV=local-production`, `SCHEDULER_ENABLED`,
`PREDICTION_ENABLED`, `EVALUATION_ENABLED`,
`SCHEDULER_LOOP_INTERVAL_SECONDS=300`.

## 3. Provider credentials

Leave a key empty to run that provider in honest-UNAVAILABLE mode.
`football_data_co_uk` needs no key (bulk CSV over HTTPS).

## 4. Startup

```bash
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml --profile migration run --rm migration
docker compose -f docker-compose.local.yml up -d
```

Order enforced by healthchecks: postgres → redis → migration (manual
one-shot) → api → scheduler/frontend.

## 5. Migrations

Manual one-shot (`migration` profile): `alembic upgrade head`.
Idempotent; safe to re-run. Never destructive; never drops data.
Current head: `0014_model_governance`.

## 6. Health checks

- API: `GET http://127.0.0.1:8000/health/live` (no deps),
  `/health/ready` (DB critical → 503; Redis non-fatal → degraded;
  additive `migrations` key; provider outages never affect API health).
- Compose healthchecks gate startup order; frontend waits for API.

## 7. Frontend access

`http://127.0.0.1:8080` (nginx → API at `tacticx-api:8000`).

## 8. CLI access

```bash
docker compose -f docker-compose.local.yml exec tacticx-scheduler \
  python scripts/tacticx.py <command>
# e.g.: system status | providers status | jobs status |
#       acquisition status | pre-match summary | prediction status |
#       evaluation status | monitoring summary
```

## 9. Scheduler

`tacticx-scheduler` runs `jobs run-due --loop` (default 300s, env
override). Uses existing locks/idempotency; safe to restart; stale
locks reclaimed by TTL + cleanup job.

## 10. Provider configuration

Per-provider keys + `*_RATE_LIMIT_PER_MINUTE` in `.env`; qualification
via `sources qualify`; activation explicit via Phase 24 flow.
`football_data_co_uk` needs no key.

## 11-12. Shutdown / restart

```bash
docker compose -f docker-compose.local.yml down      # keeps volumes
docker compose -f docker-compose.local.yml up -d     # resumes, no duplicates
docker compose -f docker-compose.local.yml down -v   # DESTROYS data (explicit only)
```

## 13-14. Backup / restore

```bash
./scripts/backup_postgres.sh     # pg_dump + gzip + sha256 → data/backups/
./scripts/restore_postgres.sh <file>
./scripts/verify_backup_restore.sh
```
Verify hashes + row counts after restore (predictions, outcomes,
certificates, governance records).

## 15. Troubleshooting

- API 503 `/ready`: check `checks.database`; verify postgres health.
- `degraded`: Redis down → memory fallback; safe.
- Scheduler idle (`no jobs due`): normal when intervals haven't elapsed.
- Provider 401/403: key invalid/revoked → honest UNAVAILABLE, bounded
  retries, no hammering.
- SECRET_KEY default + `ENVIRONMENT=production`: fail-fast on boot.

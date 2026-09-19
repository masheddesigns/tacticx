# TacticX Phase 22 — Operations & Monitoring Runbook

This runbook outlines operational procedures, health probe monitoring, logging, metrics scraping, and disaster recovery workflows for TacticX.

---

## 1. Health Probe Reference

TacticX exposes standard orchestrator endpoints:

| Endpoint | Target | Criticality | Behavior on Failure |
| :--- | :--- | :--- | :--- |
| `/health/live` | FastAPI Process | Critical | If process hangs, orchestrator restarts container. |
| `/health/ready` | PostgreSQL + Redis | DB is Critical | Returns 503 if PostgreSQL is down. Returns 200 with degraded cache state if Redis is down. |
| `/api/v1/health` | Legacy Liveness | Informational | Backward compatibility probe for existing tooling. |
| `/api/v1/ready` | Legacy Readiness | Informational | Backward compatibility probe for existing tooling. |

---

## 2. Structured Logging & Request Correlation

When `LOG_FORMAT=json` is set, all application and access logs are written as single-line JSON objects to standard error:

```json
{
  "timestamp": "2026-09-19T10:30:15.123456+00:00",
  "level": "INFO",
  "logger": "tacticx.access",
  "message": "GET /api/v1/matches/12345/intelligence -> 200 (45.2ms)",
  "request_id": "req_8f1d39a1c02e47b2",
  "path": "/api/v1/matches/12345/intelligence",
  "method": "GET",
  "status_code": 200,
  "duration_ms": 45.2,
  "client_ip": "192.168.1.50"
}
```

### Searching Logs by Correlation ID
Use `grep` or your log aggregator (e.g. Datadog, Grafana Loki, CloudWatch):
```bash
docker compose -f docker-compose.prod.yml logs backend | grep "req_8f1d39a1c02e47b2"
```

---

## 3. Prometheus Metrics Scraping

Prometheus metrics are exposed in text exposition format (v0.0.4) on the backend container at `/metrics`.

### Sample Scraping Configuration (`prometheus.yml`)
```yaml
scrape_configs:
  - job_name: 'tacticx-backend'
    scrape_interval: 15s
    metrics_path: '/metrics'
    static_configs:
      - targets: ['backend:8000']
```

### Key Metrics to Monitor
- `http_requests_total{method, route, status}`: Total traffic volume and HTTP 5xx error rates.
- `http_request_duration_seconds_bucket`: Latency percentiles (p50, p95, p99).
- `tacticx_database_connected`: Binary gauge indicating database health (1 = connected, 0 = disconnected).
- `tacticx_cache_active`: Cache operational backend (1 = redis, 0 = memory fallback).

---

## 4. Operational Mutation Endpoints

In production, all state-changing operational endpoints default to disabled:
- `POST /api/v1/jobs/{job_type}/run`
- `POST /api/v1/jobs/locks/cleanup`
- `POST /api/v1/sources/{source_id}/qualify`

### Temporarily Enabling for Manual Maintenance
If a manual job execution or qualification run is required:
1. Temporarily update `.env`:
   ```dotenv
   ENABLE_OPERATIONAL_ENDPOINTS=true
   ```
2. Reload backend service:
   ```bash
   docker compose -f docker-compose.prod.yml up -d backend
   ```
3. Execute required operations.
4. Revert `ENABLE_OPERATIONAL_ENDPOINTS=false` and reload.

---

## 5. Backup & Disaster Recovery Procedures

### 5.1. Creating a Scheduled Backup
Execute the automated backup script:
```bash
./scripts/backup_postgres.sh
```
- Backups are stored in `./data/backups/tacticx_backup_<database>_<timestamp>.sql.gz`.
- A matching SHA-256 checksum file is generated at `*.sql.gz.sha256`.

Recommended Cron entry for daily backups at 02:00 UTC:
```cron
0 2 * * * cd /opt/tacticx && ./scripts/backup_postgres.sh >> /var/log/tacticx_backup.log 2>&1
```

### 5.2. Restoring from a Backup
1. Identify the desired backup archive:
   ```bash
   ls -la ./data/backups/
   ```
2. Run the restoration script specifying the backup archive and target database:
   ```bash
   ./scripts/restore_postgres.sh ./data/backups/tacticx_backup_betpredictor_20260919_020000Z.sql.gz betpredictor
   ```
3. The restore script automatically verifies the archive's SHA-256 checksum prior to executing the restoration inside a single atomic transaction.

### 5.3. Testing Disaster Recovery
To run the automated 5-step disaster recovery verification on demand:
```bash
./scripts/verify_backup_restore.sh
```

---

## 6. Redis Failure Runbook

### Incident: Redis Container Unreachable / OOM
1. **System Impact**:
   - `/health/live` remains responsive (HTTP 200).
   - `/health/ready` reports `"status": "degraded"` with `checks["cache"]: "memory_fallback"` but continues returning HTTP 200.
   - Database queries continue serving requests normally. Cache entries fall back to single-instance bounded local memory.
2. **Mitigation**:
   - Check Redis container logs:
     ```bash
     docker compose -f docker-compose.prod.yml logs redis
     ```
   - Restart Redis:
     ```bash
     docker compose -f docker-compose.prod.yml restart redis
     ```
   - Verify cache recovery:
     ```bash
     curl http://localhost/health/ready
     ```
     Status should return to `"ok"` with `checks["cache"]: "ok"`.

# TacticX — Football Intelligence & Market Analytics Engine

TacticX is an analytical intelligence platform designed for comprehensive football match modeling, simulated scenario evidence (MiroFish), and market consensus analysis. It does **not** execute bets, place wagers, calculate stakes, or interact with gambling operators.

---

## System Architecture

```
                      Internet / Client
                              │
                              ▼
                 ┌─────────────────────────┐
                 │    Nginx (Frontend)     │
                 │   SPA Routing + Static  │
                 │     Port 80 / 443       │
                 └────────────┬────────────┘
                              │ Reverse Proxy (/api, /health)
                              │ (blocks public /metrics)
                              ▼
                 ┌─────────────────────────┐
                 │     FastAPI Backend     │
                 │   Uvicorn (Non-Root)    │
                 │   RateLimit, Security,  │
                 │   JSON Logs, Metrics    │
                 └──────┬────────────┬─────┘
                        │            │
            SQLAlchemy  ▼            ▼  Redis Client
         ┌─────────────────┐      ┌─────────────────┐
         │   PostgreSQL    │      │      Redis      │
         │   Migrations    │      │  Cache / Broker │
         │   Port 5432     │      │    Port 6379    │
         └─────────────────┘      └─────────────────┘
                  ▲
                  │ alembic upgrade head
         ┌─────────────────┐
         │    Migration    │
         │   Job/Service   │
         └─────────────────┘
```

---

## Phase Status Summary

- **Phase 17**: Canonical Match Intelligence API — **READY**
- **Phase 18**: Current-Season Acquisition — **READY**
- **Phase 19**: Provider Qualification Framework — **READY**
- **Phase 20**: Production Scheduler — **READY**
- **Phase 21**: Match Intelligence Dashboard & Product UI — **READY**
- **Phase 22**: Production Deployment, Observability & Reliability — **READY**

---

## Quickstart: Production Stack (Docker Compose)

### 1. Environment Setup
```bash
cp .env.example .env
# Edit .env to set your database passwords and secure SECRET_KEY
```

### 2. Run Database Migrations
Migrations run via a dedicated migration runner to prevent multi-replica startup races:
```bash
docker compose -f docker-compose.prod.yml run --rm migration
```

### 3. Start Core Services
```bash
docker compose -f docker-compose.prod.yml up -d
```

### 4. Health & Observability Verification
- **Process Liveness**: `curl -i http://localhost/health/live`
- **Dependency Readiness**: `curl -i http://localhost/health/ready`
- **Prometheus Metrics (Internal)**: `curl -i http://127.0.0.1:8000/metrics`
- **Web UI**: Visit `http://localhost/` in your browser

---

## Documentation Links

- **[PHASE22_REPORT.md](file:///Users/sivek/Documents/Bet%20Predictor/PHASE22_REPORT.md)**: Engineering acceptance report, benchmark results, and verification logs.
- **[PHASE22_DEPLOYMENT.md](file:///Users/sivek/Documents/Bet%20Predictor/PHASE22_DEPLOYMENT.md)**: Production deployment guide, migration lifecycle, and rolling update procedures.
- **[PHASE22_OPERATIONS.md](file:///Users/sivek/Documents/Bet%20Predictor/PHASE22_OPERATIONS.md)**: Runbook for health monitoring, log aggregation, and metrics scraping.
- **[PHASE22_SECURITY.md](file:///Users/sivek/Documents/Bet%20Predictor/PHASE22_SECURITY.md)**: Security architecture, non-root containers, CSP, and rate limiting mechanics.
- **[PHASE21_REPORT.md](file:///Users/sivek/Documents/Bet%20Predictor/PHASE21_REPORT.md)**: Frontend dashboard report and integration notes.
- **[PHASE21_UI_ARCHITECTURE.md](file:///Users/sivek/Documents/Bet%20Predictor/PHASE21_UI_ARCHITECTURE.md)**: Frontend technical design and component architecture.

---

## Development & Test Execution

### Backend Tests
```bash
cd backend
DATABASE_URL="sqlite:///./test.db" .venv/bin/pytest -q
```
*Current baseline: 599 passed / 1 intentional skip / 0 failed*

### Frontend Tests & Production Build
```bash
cd frontend
npm test
npm run build
```
*Current baseline: 19 passed / 0 failed, clean Vite build*

### Disaster Recovery Acceptance Test
```bash
./scripts/verify_backup_restore.sh
```
*Automated 5-step verification: backup -> disposable Postgres DB -> restore -> 100% integrity validation.*

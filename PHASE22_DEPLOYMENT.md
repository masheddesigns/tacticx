# TacticX Phase 22 — Production Deployment Guide

This guide outlines the step-by-step procedure for deploying TacticX in production using containerization, PostgreSQL 16, Redis 7, and Nginx.

---

## 1. Prerequisites

- **Docker Engine** (version 24.0+) & **Docker Compose** (version 2.20+)
- **System Memory**: Minimum 2 GB RAM (4 GB recommended for production workloads)
- **Disk Space**: Minimum 10 GB free disk space for PostgreSQL volume and backups
- **Domain & SSL**: Valid domain with TLS termination configured (Nginx / Cloudflare / AWS ALB)

---

## 2. Production Environment Configuration

1. Copy the production environment template:
   ```bash
   cp .env.example .env
   ```

2. Generate a secure `SECRET_KEY`:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. Update `.env` with production parameters:
   ```dotenv
   # Environment mode
   ENVIRONMENT=production
   LOG_LEVEL=INFO
   LOG_FORMAT=json

   # Database credentials (never use default passwords in production)
   POSTGRES_USER=tacticx_admin
   POSTGRES_PASSWORD=your_secure_password_here
   POSTGRES_DB=tacticx_prod

   DATABASE_URL=postgresql+psycopg2://tacticx_admin:your_secure_password_here@postgres:5432/tacticx_prod
   REDIS_URL=redis://redis:6379/0

   # Security settings
   SECRET_KEY=your_generated_token_from_step_2
   ENABLE_OPERATIONAL_ENDPOINTS=false
   RATE_LIMIT_PER_MINUTE=120
   CORS_ORIGINS=https://tacticx.yourdomain.com

   # Observability settings
   METRICS_ENABLED=true
   METRICS_INTERNAL_ONLY=true
   ```

---

## 3. Database Migration Lifecycle

> [!IMPORTANT]
> To prevent multi-replica migration races, the backend containers do **not** run migrations on startup by default. Migrations must be run via the dedicated migration service.

Execute the authoritative migration before launching or updating application services:
```bash
docker compose -f docker-compose.prod.yml run --rm migration
```

This runs `alembic upgrade head` inside an isolated container and exits cleanly upon completion.

---

## 4. Starting the Application Stack

Start the core services in detached mode:
```bash
docker compose -f docker-compose.prod.yml up -d postgres redis backend frontend
```

Verify that all containers are healthy:
```bash
docker compose -f docker-compose.prod.yml ps
```

Expected status:
- `tacticx-postgres`: `Up (healthy)`
- `tacticx-redis`: `Up (healthy)`
- `tacticx-backend`: `Up (healthy)`
- `tacticx-frontend`: `Up (healthy)`

---

## 5. Verification & Health Probes

1. **Process Liveness Probe**:
   ```bash
   curl -i http://localhost/health/live
   ```
   Expected response: `HTTP/200 OK`
   ```json
   {"status": "ok", "live": true, "service": "tacticx-backend"}
   ```

2. **Dependency Readiness Probe**:
   ```bash
   curl -i http://localhost/health/ready
   ```
   Expected response: `HTTP/200 OK`
   ```json
   {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}
   ```

3. **Prometheus Metrics (Internal Only)**:
   - External request through Nginx:
     ```bash
     curl -i http://localhost/metrics
     ```
     Expected response: `HTTP/403 Forbidden` (External access blocked by reverse proxy).
   - Internal request directly to backend:
     ```bash
     curl -i http://127.0.0.1:8000/metrics
     ```
     Expected response: `HTTP/200 OK` with `text/plain` Prometheus metric lines.

---

## 6. Rolling Restarts & Graceful Shutdown

To redeploy or update backend instances without dropping active connections:
```bash
docker compose -f docker-compose.prod.yml restart backend
```

The backend container is configured with `stop_grace_period: 20s` and `--timeout-graceful-shutdown 15`. Uvicorn immediately ceases accepting new TCP connections and drains active in-flight requests before exiting cleanly.

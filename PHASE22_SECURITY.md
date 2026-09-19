# TacticX Phase 22 — Security Architecture & Hardening Document

This document details the security model, secret management, boundary defenses, and runtime isolation mechanisms implemented in Phase 22.

---

## 1. Secret Management & Audit

### 1.1. Zero Committed Secrets Guarantee
- An audit of the git commit history and working tree confirms **zero credentials, API tokens, or secrets** are tracked in the repository.
- The root `.gitignore` explicitly excludes `.env`, `*.db`, and sensitive data caches.
- Both root `.env.example` and `backend/.env.example` contain clean, descriptive placeholder variables only.

### 1.2. Secret Key Fail-Fast Validation
In `app/config.py`:
- When `ENVIRONMENT=production`, the application validates `SECRET_KEY` on startup.
- If `SECRET_KEY` is empty or left as default (`dev-secret-key-change-in-production`, `secret`, `changeme`), application startup immediately halts with a descriptive `ValueError`.

### 1.3. Secret Redaction in Logging
Log messages are passed through a regex-based redaction filter (`_RedactSecretsFilter`) in `backend/app/logging_config.py` that strips API keys and token parameters (`apiKey=***`, `x-apisports-key=***`) before writing to disk or standard error.

---

## 2. Network Boundary & Ingress Protection

### 2.1. Metrics Exposure Policy
- Prometheus metrics (`/metrics`) reveal system internals such as routes, latency distributions, and query volumes.
- Nginx reverse proxy explicitly rejects public external ingress to `/metrics` with `HTTP 403 Forbidden`.
- Internal metrics scraping is permitted only from within the isolated Docker bridge network or localhost via `METRICS_INTERNAL_ONLY`.

### 2.2. CORS Configuration
- In production, wildcard CORS (`*`) with credentials is explicitly forbidden by startup validation.
- Allowed origins must be specified as an explicit comma-delimited allowlist via `CORS_ORIGINS`.

---

## 3. Container Runtime Isolation

### 3.1. Non-Root Execution
- The backend runtime Dockerfile creates a dedicated system group and unprivileged user:
  ```dockerfile
  RUN addgroup --system --gid 10001 appgroup && \
      adduser --system --uid 10001 --ingroup appgroup --home /app --no-create-home appuser
  USER appuser
  ```
- The application processes have zero root privileges and cannot write to system binaries or modify system packages.

### 3.2. Attack Surface Minimization
- The backend container uses a multi-stage build. Compiler tools (`gcc`, `build-essential`) are discarded in Stage 1; Stage 2 contains only minimal runtime libraries (`libpq5`).
- The frontend container uses an unprivileged static Nginx alpine image without Node.js or development dependencies.

---

## 4. HTTP Headers & Browser Security

### 4.1. Modern Security Headers
Every response emitted by the FastAPI backend and Nginx reverse proxy includes:
- **`X-Content-Type-Options: nosniff`**: Prevents MIME-type sniffing.
- **`X-Frame-Options: SAMEORIGIN`**: Protects against clickjacking.
- **`Referrer-Policy: strict-origin-when-cross-origin`**: Prevents referrer leakage to third-party domains.
- **`Permissions-Policy: geolocation=(), camera=(), microphone=()`**: Disables browser hardware APIs.
- **`Strict-Transport-Security: max-age=31536000; includeSubDomains`**: Enforces HTTPS in production.
- **`Content-Security-Policy`**: Restricts resource loading to trusted origins.

### 4.2. Deprecated Header Omission
- **`X-XSS-Protection`** is deliberately omitted in accordance with modern browser security standards (OWASP, MDN), avoiding legacy browser cross-site scripting filter vulnerabilities.

---

## 5. Rate Limiting & DoS Mitigation

### 5.1. Sliding-Window Limiter
- Implemented as an in-memory sliding window tracking requests per client IP.
- Enforces `RATE_LIMIT_PER_MINUTE` (default: 120 req/min).
- Tracked state is bounded with periodic pruning to prevent memory exhaustion attacks.

### 5.2. Multi-Replica Scope Disclosure
- The built-in rate limiter operates per-process in memory.
- For horizontally scaled deployments across multiple container replicas, an upstream distributed rate limiter (such as Cloudflare, Nginx `limit_req_zone`, or an API Gateway) should be deployed at the network edge.

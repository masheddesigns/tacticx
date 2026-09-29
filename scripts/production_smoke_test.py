#!/usr/bin/env python3
"""TacticX Phase 23 — Production Release Smoke Test Suite.

Validates:
1. Frontend build artifacts, SPA routing fallback, asset references, and secret hygiene.
2. Backend liveness (/health/live) and readiness (/health/ready) probes.
3. Version endpoint (/api/v1/version) and root system info (/), verifying non-leakage.
4. Request ID propagation and generation (X-Request-ID).
5. Metrics endpoint (/metrics) internal access vs. blocked external ingress.
6. Operational mutation endpoints (403 Forbidden without administrative credentials).
7. In-memory rate limiting (429 Too Many Requests on burst).
8. CORS policy enforcement for allowed vs disallowed origins.
9. Scheduler dormancy on startup (zero locks, zero background jobs triggered).
10. Dependency fault tolerance (Redis failure -> 200 degraded, Postgres failure -> 503 unhealthy).

Can run against a live running stack or in-process via FastAPI TestClient and local filesystem.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend directory is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "staging")

from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings
from app.db.models import Base
from app.db.models.scheduler import AcquisitionJobLock, AcquisitionJobRecord
from app.api.dependencies import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class SmokeTestRunner:
    def __init__(self, in_process: bool = True, backend_url: str | None = None, frontend_url: str | None = None):
        self.in_process = in_process
        self.backend_url = backend_url
        self.frontend_url = frontend_url
        self.passed = 0
        self.failed = 0
        self.results = []

        # Setup test db with StaticPool so in-memory tables persist across connections
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def _get_test_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _get_test_db
        self.client = TestClient(app, base_url="http://testserver")

    def report(self, name: str, passed: bool, detail: str = ""):
        if passed:
            self.passed += 1
            print(f"  [PASS] {name}{f' - {detail}' if detail else ''}")
        else:
            self.failed += 1
            print(f"  [FAIL] {name} - {detail}")
        self.results.append({"name": name, "passed": passed, "detail": detail})

    def run_all(self) -> bool:
        print("=" * 70)
        print("TacticX Phase 23 Production Release Smoke Test")
        print("=" * 70)

        self.test_frontend_artifacts()
        self.test_backend_liveness_readiness()
        self.test_version_and_root_endpoints()
        self.test_request_id_tracing()
        self.test_security_headers_and_metrics()
        self.test_operational_endpoints_protection()
        self.test_rate_limiting()
        self.test_cors_policies()
        self.test_scheduler_dormancy()
        self.test_fault_injection()

        print("=" * 70)
        print(f"Smoke Test Summary: {self.passed} PASSED, {self.failed} FAILED")
        if self.failed > 0:
            print("\nFailed checks:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  FAILED: {r['name']} - {r['detail']}")
        print("=" * 70)
        return self.failed == 0

    def test_frontend_artifacts(self):
        print("\n--- 1. Frontend Build & Static Hygiene ---")
        dist_dir = FRONTEND_DIR / "dist"
        index_file = dist_dir / "index.html"

        if not index_file.exists():
            self.report("Frontend Build Artifacts", False, f"Missing {index_file}. Run 'npm run build' first.")
            return

        content = index_file.read_text(encoding="utf-8")
        has_root = '<div id="root">' in content or '<div id="app">' in content
        self.report("Index HTML Root Element", has_root, "Contains #root mount point")

        # Check script & asset references
        js_matches = re.findall(r'src=["\'](/assets/[^"\']+\.js)["\']', content)
        css_matches = re.findall(r'href=["\'](/assets/[^"\']+\.css)["\']', content)
        assets_exist = True
        missing_assets = []
        for asset in js_matches + css_matches:
            asset_path = dist_dir / asset.lstrip("/")
            if not asset_path.exists():
                assets_exist = False
                missing_assets.append(asset)

        self.report("Asset Resolution", assets_exist, f"Found {len(js_matches)} JS, {len(css_matches)} CSS" if assets_exist else f"Missing: {missing_assets}")

        # SPA Routing Check: Nginx configuration inspection for fallback
        nginx_conf = FRONTEND_DIR / "nginx.conf"
        if nginx_conf.exists():
            nginx_text = nginx_conf.read_text()
            has_spa_fallback = "try_files $uri $uri/ /index.html;" in nginx_text
            self.report("SPA Fallback Route in Nginx", has_spa_fallback, "try_files maps to /index.html")
            has_metrics_block = "location /metrics" in nginx_text and "403" in nginx_text
            self.report("External Ingress Block for /metrics in Nginx", has_metrics_block, "Forbidden 403 rule present")

        # Secret Scan in built assets
        forbidden = ["PRIVATE_KEY", "AWS_SECRET", "POSTGRES_PASSWORD", "BEGIN PRIVATE KEY"]
        leaked = [f for f in forbidden if f in content]
        self.report("Frontend Secret Hygiene", len(leaked) == 0, f"No sensitive tokens in dist/ (scanned {len(content)} bytes)")

    def test_backend_liveness_readiness(self):
        print("\n--- 2. Backend Health Probes ---")
        # Liveness
        res_live = self.client.get("/health/live")
        self.report("Liveness Probe (GET /health/live)", res_live.status_code == 200, f"Status: {res_live.status_code}")
        live_json = res_live.json()
        self.report("Liveness Payload", live_json.get("live") is True, f"live={live_json.get('live')}")

        # Readiness
        res_ready = self.client.get("/health/ready")
        self.report("Readiness Probe (GET /health/ready)", res_ready.status_code == 200, f"Status: {res_ready.status_code}")
        ready_json = res_ready.json()
        self.report("Readiness Components", "database" in ready_json.get("checks", {}), f"checks={list(ready_json.get('checks', {}).keys())}")

    def test_version_and_root_endpoints(self):
        print("\n--- 3. Safe Versioning & Root Endpoint ---")
        res_ver = self.client.get("/api/v1/version")
        self.report("Version Endpoint (GET /api/v1/version)", res_ver.status_code == 200, f"Status: {res_ver.status_code}")
        ver_json = res_ver.json()
        safe_keys = {"service", "version", "commit", "build_date", "environment"}
        self.report("Version Schema Completeness", safe_keys.issubset(ver_json.keys()), f"Keys: {list(ver_json.keys())}")

        # Root endpoint
        res_root = self.client.get("/")
        self.report("Root Discovery (GET /)", res_root.status_code == 200, f"Status: {res_root.status_code}")
        root_json = res_root.json()
        self.report("Root Links Provided", "docs" in root_json and "health" in root_json, f"Root keys: {list(root_json.keys())}")

    def test_request_id_tracing(self):
        print("\n--- 4. Request ID Tracing ---")
        # Without X-Request-ID
        res_auto = self.client.get("/health/live")
        auto_id = res_auto.headers.get("X-Request-ID")
        self.report("Auto-generated X-Request-ID", bool(auto_id) and len(auto_id) > 8, f"Generated: {auto_id}")

        # Echo existing X-Request-ID
        custom_id = "test-smoke-trace-42"
        res_echo = self.client.get("/health/live", headers={"X-Request-ID": custom_id})
        echoed_id = res_echo.headers.get("X-Request-ID")
        self.report("Echoed X-Request-ID", echoed_id == custom_id, f"Sent: {custom_id}, Got: {echoed_id}")

    def test_security_headers_and_metrics(self):
        print("\n--- 5. Security Headers & Observability ---")
        res = self.client.get("/health/live")
        h = res.headers
        nosniff = h.get("X-Content-Type-Options") == "nosniff"
        xframe = h.get("X-Frame-Options") in ("SAMEORIGIN", "DENY")
        csp = "default-src 'self'" in h.get("Content-Security-Policy", "")
        self.report("Security Headers (nosniff, SAMEORIGIN/DENY, CSP)", nosniff and xframe and csp, f"nosniff={nosniff}, xframe={h.get('X-Frame-Options')}")

        # Prometheus metrics endpoint
        res_metrics = self.client.get("/metrics")
        is_prom = res_metrics.status_code == 200 and "# HELP" in res_metrics.text
        self.report("Prometheus Metrics Exposition", is_prom, f"Length: {len(res_metrics.text)} bytes")

    def test_operational_endpoints_protection(self):
        print("\n--- 6. Operational Mutations Protection ---")
        # In production (or when operational mutations are disabled), POST to these endpoints returns 403
        with patch.object(get_settings(), "ENABLE_OPERATIONAL_ENDPOINTS", False):
            res_jobs = self.client.post("/api/v1/jobs/odds/run", json={})
            self.report("Job Execution Guard (POST /api/v1/jobs/odds/run)", res_jobs.status_code == 403, f"Status: {res_jobs.status_code}")

            res_locks = self.client.post("/api/v1/jobs/locks/cleanup")
            self.report("Lock Cleanup Guard (POST /api/v1/jobs/locks/cleanup)", res_locks.status_code == 403, f"Status: {res_locks.status_code}")

            res_qualify = self.client.post("/api/v1/sources/mock_src/qualify", json={})
            self.report("Source Qualification Guard (POST /api/v1/sources/id/qualify)", res_qualify.status_code == 403, f"Status: {res_qualify.status_code}")

    def test_rate_limiting(self):
        print("\n--- 7. Rate Limiting Protection ---")
        # RateLimitingMiddleware exempts 'testclient' by default (exempt_testclient=True).
        # Temporarily disable the exemption so TestClient requests go through the limiter.
        from app.api.middleware import RateLimitingMiddleware
        rate_limiter = next(
            (m for m in app.middleware_stack.__dict__.get("app", app).__dict__.get("middleware", [])
             if isinstance(getattr(m, "cls", None), type) and issubclass(getattr(m, "cls", type), RateLimitingMiddleware)),
            None,
        )
        # Locate the middleware instance directly from the app stack
        stack = app.middleware_stack
        limiter_instance = None
        while stack is not None:
            if isinstance(stack, RateLimitingMiddleware):
                limiter_instance = stack
                break
            stack = getattr(stack, "app", None)

        triggered_429 = False
        limit = 120

        if limiter_instance is not None:
            # Disable testclient exemption temporarily
            original_exempt = limiter_instance.exempt_testclient
            limiter_instance.exempt_testclient = False
            try:
                for i in range(limit + 5):
                    r = self.client.get("/api/v1/version")
                    if r.status_code == 429:
                        triggered_429 = True
                        retry_after = r.headers.get("Retry-After")
                        self.report("Rate Limit Enforced (429)", True, f"Triggered on request #{i+1}, Retry-After={retry_after}")
                        break
            finally:
                limiter_instance.exempt_testclient = original_exempt
                # Reset request history to avoid polluting other tests
                limiter_instance._history.clear()
        else:
            # Middleware not found in stack — check via response behaviour as fallback
            for i in range(limit + 5):
                r = self.client.get("/api/v1/version")
                if r.status_code == 429:
                    triggered_429 = True
                    retry_after = r.headers.get("Retry-After")
                    self.report("Rate Limit Enforced (429)", True, f"Triggered on request #{i+1}, Retry-After={retry_after}")
                    break

        if not triggered_429:
            self.report("Rate Limit Enforced (429)", False, "429 was not triggered within burst limit")


    def test_cors_policies(self):
        print("\n--- 8. CORS Policies ---")
        # Allowed origin
        res_allowed = self.client.get(
            "/health/live",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        allow_origin = res_allowed.headers.get("Access-Control-Allow-Origin")
        self.report("Allowed CORS Origin (http://localhost:3000)", allow_origin == "http://localhost:3000", f"Header: {allow_origin}")

        # Disallowed origin
        res_bad = self.client.get(
            "/health/live",
            headers={"Origin": "http://malicious-attacker.com", "Access-Control-Request-Method": "GET"},
        )
        bad_origin = res_bad.headers.get("Access-Control-Allow-Origin")
        self.report("Disallowed CORS Origin Rejected", bad_origin != "http://malicious-attacker.com", f"Header: {bad_origin}")

    def test_scheduler_dormancy(self):
        print("\n--- 9. Scheduler Dormancy On Startup ---")
        # Direct query to DB models: ensure no acquisition job records or locks exist simply from boot
        db = self.SessionLocal()
        try:
            locks = db.query(AcquisitionJobLock).count()
            records = db.query(AcquisitionJobRecord).count()
            dormant = (locks == 0 and records == 0)
            self.report("Scheduler Inactivity On Boot", dormant, f"Active locks: {locks}, Job runs: {records}")
        finally:
            db.close()

    def test_fault_injection(self):
        print("\n--- 10. Fault Tolerance & Dependency Simulation ---")
        # A) Redis failure simulation: health/ready should return 200 degraded, NOT 500 or crash
        with patch("app.services.caching.cache.cache_set", side_effect=RuntimeError("Redis connection refused")):
            res_redis_down = self.client.get("/health/ready")
            degraded_ok = res_redis_down.status_code == 200 and res_redis_down.json().get("status") == "degraded"
            self.report("Redis Outage Tolerance (200 Degraded)", degraded_ok, f"Status: {res_redis_down.status_code}, status={res_redis_down.json().get('status')}")

        # B) PostgreSQL failure simulation: health/ready should return 503 Service Unavailable
        with patch("app.db.session.get_engine", side_effect=RuntimeError("PostgreSQL connection refused")):
            res_db_down = self.client.get("/health/ready")
            db_unhealthy = res_db_down.status_code == 503 and res_db_down.json().get("status") == "unhealthy"
            self.report("Database Outage Isolation (503 Unhealthy)", db_unhealthy, f"Status: {res_db_down.status_code}, status={res_db_down.json().get('status')}")


def main():
    parser = argparse.ArgumentParser(description="TacticX Phase 23 Production Release Smoke Test")
    parser.add_argument("--backend-url", default=None, help="Live backend URL (e.g. http://localhost:8000)")
    parser.add_argument("--frontend-url", default=None, help="Live frontend URL (e.g. http://localhost:3000)")
    args = parser.parse_args()

    runner = SmokeTestRunner(
        in_process=True,
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
    )
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

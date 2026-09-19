"""Phase 22 — Production Deployment, Observability & Reliability Tests.

Verifies:
- Liveness (/health/live) and readiness (/health/ready) probes.
- Graceful non-fatal cache degradation semantics.
- Backward compatibility of /api/v1/health and /api/v1/ready.
- Request correlation (X-Request-ID).
- Security headers (and omission of obsolete X-XSS-Protection).
- Rate limiting middleware (429 Too Many Requests).
- Operational mutation endpoint disablement (ENABLE_OPERATIONAL_ENDPOINTS).
- Prometheus /metrics exposition with bounded route templates.
- Production environment fail-fast validation.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.config import Settings
from app.main import app
from app.observability.metrics import collector


@pytest.fixture
def test_client():
    return TestClient(app)


# --- 1. Health and Readiness Probes ---

def test_liveness_probe_root_and_prefix(test_client):
    """Liveness probe must return 200 without requiring external dependencies."""
    r1 = test_client.get("/health/live")
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["status"] == "ok"
    assert data1["live"] is True
    assert data1["service"] == "tacticx-backend"

    # Legacy /health alias
    r2 = test_client.get("/health")
    assert r2.status_code == 200
    assert r2.json()["status"] == "ok"

    # API v1 prefix alias
    r3 = test_client.get("/api/v1/health")
    assert r3.status_code == 200
    assert r3.json()["status"] == "ok"


def test_readiness_probe_healthy(test_client):
    """Readiness probe returns 200 when database is healthy."""
    r = test_client.get("/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["checks"]["database"] == "ok"
    assert data["status"] in ("ok", "degraded")


def test_readiness_probe_database_failure(test_client):
    """Readiness probe MUST return 503 when the critical database connection fails."""
    with patch("app.db.session.get_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_conn.connect.side_effect = Exception("DB Connection Refused")
        mock_engine.return_value = mock_conn

        r = test_client.get("/health/ready")
        assert r.status_code == 503
        data = r.json()
        assert data["status"] == "unhealthy"
        assert "error" in data["checks"]["database"]


def test_readiness_probe_non_fatal_cache_degradation(test_client):
    """Redis outage must NOT bring down readiness probe if database is healthy."""
    with patch("app.services.caching.cache.cache_set", side_effect=Exception("Redis connection timeout")):
        r = test_client.get("/health/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["checks"]["database"] == "ok"
        assert "error" in data["checks"]["cache"]
        assert data["status"] == "degraded"


def test_legacy_health_and_ready_backward_compatibility(test_client):
    """Existing tests and consumers rely on /api/v1/health and /api/v1/ready schemas."""
    r_health = test_client.get("/api/v1/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_ready = test_client.get("/api/v1/ready")
    assert r_ready.status_code == 200
    data = r_ready.json()
    assert "checks" in data
    assert data["checks"]["database"] == "ok"


# --- 2. Request Correlation (X-Request-ID) ---

def test_request_id_generation(test_client):
    """Missing X-Request-ID generates a new UUID header on response."""
    r = test_client.get("/health/live")
    assert "X-Request-ID" in r.headers
    assert r.headers["X-Request-ID"].startswith("req_")


def test_request_id_echo(test_client):
    """Provided X-Request-ID is echoed back on response."""
    custom_id = "test-req-correlation-12345"
    r = test_client.get("/health/live", headers={"X-Request-ID": custom_id})
    assert r.headers.get("X-Request-ID") == custom_id


# --- 3. Security Headers ---

def test_security_headers_present(test_client):
    """Responses include modern security headers and omit obsolete ones."""
    r = test_client.get("/health/live")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in r.headers
    assert "Content-Security-Policy" in r.headers

    # Obsolete header check
    assert "X-XSS-Protection" not in r.headers


# --- 4. Rate Limiting Middleware ---

def test_rate_limiting_enforcement():
    """In-memory rate limiter returns 429 when threshold exceeded."""
    from app.api.middleware import RateLimitingMiddleware
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    limiter_app = FastAPI()
    limiter_app.add_middleware(RateLimitingMiddleware, max_requests_per_minute=3, exempt_testclient=False)

    @limiter_app.get("/test-rate")
    def rate_endpoint():
        return {"ok": True}

    client = TestClient(limiter_app)
    # First 3 requests succeed
    for _ in range(3):
        res = client.get("/test-rate")
        assert res.status_code == 200
        assert "X-RateLimit-Remaining" in res.headers

    # 4th request exceeds rate limit
    res4 = client.get("/test-rate")
    assert res4.status_code == 429
    data = res4.json()
    assert data["error"] == "rate_limit_exceeded"
    assert "Retry-After" in res4.headers


# --- 5. Operational Mutation Protection ---

def test_operational_mutation_endpoints_disabled_by_default(test_client):
    """Mutations return 403 Forbidden when operational endpoints are disabled."""
    with patch("app.config.Settings.operational_endpoints_enabled", False):
        # 1. Trigger job run
        r1 = test_client.post("/api/v1/jobs/sync/run")
        assert r1.status_code == 403
        assert "Operational mutation endpoints are disabled" in r1.json()["detail"]

        # 2. Cleanup locks
        r2 = test_client.post("/api/v1/jobs/locks/cleanup")
        assert r2.status_code == 403
        assert "Operational mutation endpoints are disabled" in r2.json()["detail"]

        # 3. Qualify source
        r3 = test_client.post("/api/v1/sources/api_football/qualify", json={})
        assert r3.status_code == 403
        assert "Operational mutation endpoints are disabled" in r3.json()["detail"]


# --- 6. Prometheus Metrics Exposition ---

def test_metrics_exposition(test_client):
    """Metrics endpoint exposes valid Prometheus text format with normalized routes."""
    # Generate some traffic
    test_client.get("/health/live")
    test_client.get("/api/v1/matches")

    r = test_client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    text = r.text

    assert "# HELP http_requests_total" in text
    assert "# TYPE http_requests_total counter"
    assert "http_requests_total{" in text
    assert "tacticx_database_connected" in text
    assert "tacticx_cache_active" in text


def test_metrics_cardinality_route_normalization():
    """Dynamic identifiers must be normalized to prevent unbounded cardinality."""
    from app.observability.metrics import MetricsCollector

    test_coll = MetricsCollector()
    test_coll.record_http_request("GET", "/api/v1/matches/99999/intelligence", 200, 0.05)
    test_coll.record_http_request("GET", "/api/v1/matches/88888/intelligence", 200, 0.04)
    test_coll.record_http_request("GET", "/api/v1/intelligence/77777", 404, 0.02)
    test_coll.record_http_request("GET", "/api/v1/intelligence/snapshots/intel_abc12345", 200, 0.01)

    text = test_coll.generate_prometheus_text()
    # Should contain template, not raw match IDs
    assert 'route="/api/v1/matches/{match_id}/intelligence"' in text
    assert 'route="/api/v1/intelligence/{id}"' in text
    assert 'route="/api/v1/intelligence/snapshots/{snapshot_id}"' in text
    assert "99999" not in text
    assert "88888" not in text
    assert "77777" not in text
    assert "intel_abc12345" not in text


# --- 7. Production Configuration Fail-Fast ---

def test_production_fail_fast_on_sqlite():
    """Production environment must disallow SQLite database."""
    s = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="sqlite:///./prod.db",
        SECRET_KEY="secure-production-secret-key-abcdef123456",
        CORS_ORIGINS="http://localhost:80",
    )
    with pytest.raises(ValueError, match="must be a production PostgreSQL database"):
        s.validate_production()


def test_production_fail_fast_on_default_secret():
    """Production environment must disallow default or empty SECRET_KEY."""
    s = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+psycopg2://u:p@localhost:5432/db",
        SECRET_KEY="dev-secret-key-change-in-production",
        CORS_ORIGINS="http://localhost:80",
    )
    with pytest.raises(ValueError, match="SECRET_KEY must be set to a secure, non-default value"):
        s.validate_production()


def test_production_fail_fast_on_wildcard_cors():
    """Production environment must disallow wildcard CORS origins."""
    s = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+psycopg2://u:p@localhost:5432/db",
        SECRET_KEY="secure-production-secret-key-abcdef123456",
        CORS_ORIGINS="*",
    )
    with pytest.raises(ValueError, match="CORS_ORIGINS cannot contain wildcard"):
        s.validate_production()

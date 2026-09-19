"""Production middleware suite: Request ID correlation, modern Security Headers,
single-instance in-memory Rate Limiting, and Prometheus Metrics instrumentation.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Callable, Dict, List

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.observability.metrics import collector
from app.observability.request_context import reset_request_id, set_request_id

logger = logging.getLogger("tacticx.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Correlation ID middleware: extracts or generates X-Request-ID, attaches it to
    contextvars, response headers, and log messages."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = f"req_{uuid.uuid4().hex[:16]}"

        token = set_request_id(req_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            reset_request_id(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects modern HTTP security headers on all responses.

    Note: Obsolete headers like X-XSS-Protection are omitted per current security standards.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        settings = get_settings()

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        # HSTS in production or when serving over HTTPS
        if settings.ENVIRONMENT.lower() == "production" or request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy (allows Vite static SPA assets and local API communication)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        return response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window rate limiter per client IP.

    NOTE: This is a single-instance rate limiter. In a multi-replica deployment,
    each backend replica enforces its own local limit independently. It does
    not provide cluster-wide distributed coordination (for cluster-wide rate
    limiting, an external gateway or distributed token bucket should be used).
    """

    def __init__(self, app, max_requests_per_minute: int = 120, exempt_testclient: bool = True):
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        self.exempt_testclient = exempt_testclient
        # client_ip -> list of timestamps
        self._history: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()
        # Endpoints exempt from rate limits (orchestrator health/liveness probes)
        self._exempt_paths = frozenset({
            "/health/live",
            "/health/ready",
            "/health",
            "/ready",
            "/api/v1/health",
            "/api/v1/ready",
            "/metrics",
        })

    def _cleanup_old_entries(self, now: float) -> None:
        if now - self._last_cleanup < 60.0:
            return
        self._last_cleanup = now
        window_start = now - 60.0
        # Prune IPs with no active timestamps
        dead_keys = []
        for ip, timestamps in self._history.items():
            valid = [ts for ts in timestamps if ts > window_start]
            if not valid:
                dead_keys.append(ip)
            else:
                self._history[ip] = valid
        for k in dead_keys:
            self._history.pop(k, None)

        # Enforce hard ceiling on tracked IP table
        if len(self._history) > 10000:
            self._history.clear()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in self._exempt_paths:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if self.exempt_testclient and client_ip == "testclient":
            return await call_next(request)
        now = time.time()
        self._cleanup_old_entries(now)

        window_start = now - 60.0
        timestamps = self._history.setdefault(client_ip, [])
        valid_timestamps = [ts for ts in timestamps if ts > window_start]
        self._history[client_ip] = valid_timestamps

        if len(valid_timestamps) >= self.max_requests:
            retry_after = int(60.0 - (now - valid_timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": max(1, retry_after),
                },
                headers={
                    "Retry-After": str(max(1, retry_after)),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        valid_timestamps.append(now)
        remaining = self.max_requests - len(valid_timestamps)

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        return response


class MetricsAndAccessLoggingMiddleware(BaseHTTPMiddleware):
    """Instruments Prometheus latency & counts, and logs structured JSON access records."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        response = await call_next(request)

        duration = time.time() - start_time
        status_code = response.status_code

        # Record metrics with route normalization
        collector.record_http_request(method, path, status_code, duration)

        # Structured JSON access logging
        settings = get_settings()
        if settings.LOG_FORMAT.lower() == "json":
            logger.info(
                f"{method} {path} -> {status_code} ({duration * 1000:.1f}ms)",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                    "client_ip": client_ip,
                },
            )

        return response

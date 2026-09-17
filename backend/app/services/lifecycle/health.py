"""Source health + bounded retries (Phase 7).

Health states: healthy | degraded | unavailable | rate_limited |
authentication_error. Secrets never touch this subsystem (no keys, tokens
or headers are accepted, logged or stored here).

Retry policy: transient failures retry with exponential backoff up to
PROVIDER_RETRY_ATTEMPTS; 401/403/invalid-auth fail fast with no retry.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.lifecycle import SourceHealth

HEALTHY, DEGRADED, UNAVAILABLE = "healthy", "degraded", "unavailable"
RATE_LIMITED, AUTH_ERROR = "rate_limited", "authentication_error"


def _classify(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}".lower()
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    if status in (401, 403) or "unauthorized" in message or "forbidden" in message \
            or "invalid api key" in message or "invalid_api_key" in message:
        return AUTH_ERROR
    if status == 429 or "rate limit" in message or "rate_limit" in message \
            or "quota" in message:
        return RATE_LIMITED
    return "transient"


def record_success(db: Session, source: str, records: int = 0,
                   latency_ms: Optional[float] = None,
                   quota_remaining: Optional[int] = None) -> SourceHealth:
    row = db.query(SourceHealth).filter_by(source=source).first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = SourceHealth(source=source)
        db.add(row)
    row.state = HEALTHY
    row.last_success = now
    row.failure_count = 0
    row.records_received = (row.records_received or 0) + max(0, records)
    if latency_ms is not None:
        row.latency_ms = latency_ms
    if quota_remaining is not None:
        row.quota_remaining = quota_remaining
    row.last_error = ""
    row.updated_at = now
    db.commit()
    return row


def record_failure(db: Session, source: str, error: str,
                   latency_ms: Optional[float] = None) -> SourceHealth:
    row = db.query(SourceHealth).filter_by(source=source).first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = SourceHealth(source=source)
        db.add(row)
    failures = (row.failure_count or 0) + 1
    row.failure_count = failures
    row.last_failure = now
    row.last_error = str(error)[:500]
    if latency_ms is not None:
        row.latency_ms = latency_ms
    row.state = DEGRADED if failures < 3 else UNAVAILABLE
    row.updated_at = now
    db.commit()
    return row


def get_health(db: Session, source: Optional[str] = None) -> Dict:
    query = db.query(SourceHealth)
    if source:
        query = query.filter_by(source=source)
    out = {}
    for row in query.all():
        out[row.source] = {
            "state": row.state, "last_success": str(row.last_success),
            "last_failure": str(row.last_failure),
            "failure_count": row.failure_count,
            "records_received": row.records_received,
            "latency_ms": row.latency_ms,
            "quota_remaining": row.quota_remaining,
            "last_error": row.last_error,
            "updated_at": str(row.updated_at),
        }
    return out


async def run_with_retries(label: str, func: Callable, *args,
                           attempts: Optional[int] = None,
                           base_seconds: Optional[float] = None,
                           **kwargs):
    """Bounded retries with exponential backoff. Auth errors fail fast."""
    settings = get_settings()
    max_attempts = max(1, attempts or settings.PROVIDER_RETRY_ATTEMPTS)
    base = base_seconds if base_seconds is not None else settings.PROVIDER_RETRY_BASE_SECONDS
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return result, {"attempts": attempt, "retried": attempt > 1}
        except Exception as exc:
            last_exc = exc
            kind = _classify(exc)
            if kind == AUTH_ERROR:
                raise
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(base * (2 ** (attempt - 1)))
    raise last_exc  # pragma: no cover - loop always raises first

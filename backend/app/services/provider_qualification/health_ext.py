"""Extended source-health recording (Phase 19).

Builds on lifecycle/health.py states without duplicating them. Adds HTTP
status, consecutive failures, backoff deadlines, response sizes, fixture
counts and last qualification. New states: disabled, unqualified,
schema_error. Health is operational telemetry — never a prediction
confidence score.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.lifecycle import SourceHealth
from app.services.lifecycle import health as base_health

DISABLED = "disabled"
UNQUALIFIED = "unqualified"
SCHEMA_ERROR = "schema_error"


def record_request(db: Session, source: str, *,
                   http_status: Optional[int] = None,
                   response_bytes: Optional[int] = None,
                   fixture_count: Optional[int] = None,
                   latency_ms: Optional[float] = None,
                   quota_remaining: Optional[int] = None) -> SourceHealth:
    """Record one completed provider request (success orHTTP-level failure
    is decided by the caller via record_success/record_result below)."""
    row = db.query(SourceHealth).filter_by(source=source).first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = SourceHealth(source=source)
        db.add(row)
    if http_status is not None:
        row.last_http_status = http_status
    if response_bytes is not None:
        row.last_response_bytes = response_bytes
    if fixture_count is not None:
        row.last_fixture_count = fixture_count
    if latency_ms is not None:
        row.latency_ms = latency_ms
    if quota_remaining is not None:
        row.quota_remaining = quota_remaining
    row.updated_at = now
    db.commit()
    return row


def record_result(db: Session, source: str, ok: bool, error: str = "",
                  backoff_seconds: Optional[int] = None) -> SourceHealth:
    """Success resets the failure streak; failure extends it and may set a
    backoff deadline. A single failure never auto-disables a source."""
    if ok:
        row = base_health.record_success(db, source)
        row.consecutive_failures = 0
        row.backoff_until = None
        db.commit()
        return row
    row = base_health.record_failure(db, source, error)
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
    if backoff_seconds:
        row.backoff_until = datetime.now(timezone.utc) + timedelta(
            seconds=backoff_seconds)
    db.commit()
    return row


def set_state(db: Session, source: str, state: str) -> SourceHealth:
    allowed = {"healthy", "degraded", "unavailable", "rate_limited",
               "authentication_error", DISABLED, UNQUALIFIED, SCHEMA_ERROR}
    if state not in allowed:
        raise ValueError(f"unknown health state: {state}")
    row = db.query(SourceHealth).filter_by(source=source).first()
    if row is None:
        row = SourceHealth(source=source)
        db.add(row)
    row.state = state
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return row


def record_qualification(db: Session, source: str, status: str) -> SourceHealth:
    row = db.query(SourceHealth).filter_by(source=source).first()
    if row is None:
        row = SourceHealth(source=source)
        db.add(row)
    row.last_qualification = status
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return row


def describe(db: Session, source: Optional[str] = None) -> Dict:
    base = base_health.get_health(db, source)
    query = db.query(SourceHealth)
    if source:
        query = query.filter_by(source=source)
    for row in query.all():
        entry = base.setdefault(row.source, {})
        entry.update({
            "last_http_status": row.last_http_status,
            "consecutive_failures": row.consecutive_failures or 0,
            "backoff_until": str(row.backoff_until)
            if row.backoff_until else None,
            "last_response_bytes": row.last_response_bytes,
            "last_fixture_count": row.last_fixture_count,
            "last_qualification": row.last_qualification or "",
        })
    return base

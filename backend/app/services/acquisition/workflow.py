"""Acquisition workflow: discovery → validation → persistence (Phase 11).

Prediction never triggers acquisition: this workflow only maintains the
match universe. Failures classify (auth/rate-limit/temporary/empty/schema/
validation) and partial success persists (successful records kept, failure
recorded, retry stays idempotent). An empty provider response is NOT
interpreted as 'no fixtures' unless the source contract proves it.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.acquisition import AcquisitionRun
from app.services.freshness import fixtures as fixture_svc
from app.services.lifecycle import sync as sync_svc
from app.services.lifecycle.health import record_failure, record_success
from app.services.lifecycle.upcoming import UpcomingMatch

FAIL_AUTH = "authentication_failure"
FAIL_AUTHZ = "authorization_failure"
FAIL_RATE = "rate_limited"
FAIL_TEMP = "temporary_failure"
FAIL_EMPTY = "provider_empty"
FAIL_SCHEMA = "provider_schema_error"
FAIL_VALIDATION = "validation_failure"


def classify_failure(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}".lower()
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    if status == 401:
        return FAIL_AUTH
    if status == 403:
        return FAIL_AUTHZ
    if status == 429:
        return FAIL_RATE
    if status is not None and status >= 500:
        return FAIL_TEMP
    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return FAIL_TEMP
    if "schema" in message or "unexpected" in message or "invalid payload" in message:
        return FAIL_SCHEMA
    return FAIL_TEMP


def content_hash(records: List[UpcomingMatch]) -> str:
    canonical = sorted(
        f"{r.source}|{r.source_match_id}|{r.home_team}|{r.away_team}|"
        f"{r.kickoff_utc}|{r.status}" for r in records)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]


def run_acquisition(db: Session, source_name: str, records: List[UpcomingMatch],
                    job: str = "fixture_discovery",
                    requested_scope: Optional[Dict] = None,
                    failure: Optional[Exception] = None) -> Dict:
    """Execute one acquisition: persist records (partial-safe), log the run.
    Identical re-runs create nothing new (content hash + sync idempotency)."""
    started = datetime.now(timezone.utc)
    run_id = f"{source_name}-{int(started.timestamp())}"
    row = AcquisitionRun(run_id=run_id, source=source_name, job=job,
                         status="running",
                         requested_scope=requested_scope or {})
    db.add(row)
    db.commit()
    outcome: Dict = {"run_id": run_id, "source": source_name}
    if failure is not None:
        kind = classify_failure(failure)
        record_failure(db, source_name, f"{kind}: {str(failure)[:200]}")
        row.status = "failed" if kind not in (FAIL_RATE,) else "rate_limited"
        row.finished_at = datetime.now(timezone.utc)
        row.errors = {"classification": kind, "error": str(failure)[:500]}
        db.commit()
        outcome.update({"status": row.status, "classification": kind})
        return outcome
    if not records:
        # Empty response is reported as empty, never as proof of no fixtures.
        row.status = "empty"
        row.finished_at = datetime.now(timezone.utc)
        row.errors = {"classification": FAIL_EMPTY,
                      "note": "empty response recorded; not proof of no fixtures"}
        db.commit()
        record_success(db, source_name, records=0)
        outcome.update({"status": "empty", "classification": FAIL_EMPTY})
        return outcome
    digest = content_hash(records)
    stats = sync_svc.sync_upcoming_matches(db, records)
    # Fixture observations for canonical matches (append-only, idempotent).
    from app.db.models.core import League, Match

    observed = 0
    for record in records:
        league = db.query(League).filter_by(code=record.league_code).first() \
            if record.league_code else None
        match = None
        if league is not None:
            from app.services.identity.matches import MatchResolver

            home = away = None
            from app.services.identity.teams import TeamIdentityResolver

            tresolver = TeamIdentityResolver(db)
            home, _ = tresolver.resolve(record.source, provider_team_name=record.home_team,
                                        league=record.league_code)
            away, _ = tresolver.resolve(record.source, provider_team_name=record.away_team,
                                        league=record.league_code)
            if home and away:
                mid = MatchResolver(db).resolve(
                    record.source, record.source_match_id, league.id, home, away,
                    record.kickoff_utc)
                match = db.get(Match, mid) if mid else None
        if match is not None:
            result = fixture_svc.observe_fixture(
                db, match.id, record.source,
                {"kickoff_at": record.kickoff_utc, "status": record.status},
                raw_reference=f"{record.source}:{record.source_match_id}")
            observed += len(result.get("appended", []))
    record_success(db, source_name, records=stats.received)
    row.status = "partial_success" if stats.errors else "success"
    row.finished_at = datetime.now(timezone.utc)
    row.records_seen = stats.received
    row.records_created = stats.inserted
    row.records_updated = stats.updated
    row.records_rejected = stats.skipped
    row.records_quarantined = 0
    row.errors = {"sync_errors": stats.errors[:10], "content_hash": digest,
                  "observations_appended": observed}
    db.commit()
    outcome.update({"status": row.status, "seen": stats.received,
                    "created": stats.inserted, "updated": stats.updated,
                    "rejected": stats.skipped, "content_hash": digest,
                    "observations_appended": observed})
    return outcome

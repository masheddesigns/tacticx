"""Append-only qualification evidence snapshots (Phase 19).

Stores verdict summaries (counts + hashes + reason codes), never secrets
and never raw provider payloads.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.db.models.qualification import SourceQualification


def store_qualification(db: Session, source: str, competition: str,
                        season: str, request_count: int, response_count: int,
                        verdict: Dict[str, Any]) -> SourceQualification:
    """Persist one qualification evidence row. Never raises on storage
    failure callers already handle verdicts without persistence."""
    import json

    coverage = verdict.get("coverage", {}) or {}
    capabilities = verdict.get("capabilities", {}) or {}
    capability_hash = hashlib.sha256(
        json.dumps(capabilities, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    evidence = verdict.get("evidence", {}) or {}
    row = SourceQualification(
        qualification_run_id=f"qual-{uuid.uuid4().hex[:12]}",
        source=source, competition=competition or "",
        season=season or "",
        retrieved_at=datetime.now(timezone.utc),
        request_count=request_count, response_count=response_count,
        fixture_count=int(coverage.get("fixtures", 0) or 0),
        resolved_count=0, unresolved_count=0, conflict_count=0,
        status=verdict.get("status", "unqualified"),
        reason_codes=list(verdict.get("reason_codes", []) or []),
        capability_hash=capability_hash,
        sample_hash=str(evidence.get("sample_hash", ""))[:64],
    )
    db.add(row)
    db.commit()
    return row


def latest_for(db: Session, source: str,
               competition: str = "", season: str = "") -> Dict[str, Any]:
    query = db.query(SourceQualification).filter_by(source=source)
    if competition:
        query = query.filter_by(competition=competition)
    if season:
        query = query.filter_by(season=season)
    row = query.order_by(SourceQualification.id.desc()).first()
    if row is None:
        return {"status": "unqualified", "reason": "no qualification recorded"}
    return {
        "qualification_run_id": row.qualification_run_id,
        "source": row.source, "competition": row.competition,
        "season": row.season, "status": row.status,
        "reason_codes": row.reason_codes or [],
        "fixture_count": row.fixture_count,
        "capability_hash": row.capability_hash,
        "sample_hash": row.sample_hash,
        "retrieved_at": str(row.retrieved_at),
    }

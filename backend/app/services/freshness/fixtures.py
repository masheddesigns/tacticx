"""Fixture freshness + append-only match observations (Phase 10).

Fixture states: fresh | stale | unknown | expired (per-source definitions:
a fixture is fresh when its source observation is recent relative to the
fixture's distance; kickoff in the past without a result is expired).
Kickoff/status/venue changes append MatchObservation rows — old source
observations are never mutated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.freshness import MatchObservation
from app.services.features.temporal import as_naive_utc

TRACKED_FIELDS = ("kickoff_at", "status", "venue", "home_team_id",
                  "away_team_id", "league_id")


def observe_fixture(db: Session, match_id: int, source: str,
                    observed: Dict, raw_reference: str = "",
                    effective_at: Optional[datetime] = None,
                    retrieved_at: Optional[datetime] = None,
                    dry_run: bool = False) -> Dict:
    """Record one source observation; changed tracked fields append history
    rows. Idempotent: identical re-observation appends nothing."""
    match = db.get(Match, match_id)
    if match is None:
        return {"error": "match missing"}
    now = datetime.now(timezone.utc)
    appended, unchanged = [], []
    for field in TRACKED_FIELDS:
        if field not in observed:
            continue
        new_value = observed[field]
        current = getattr(match, field, None)
        new_str = "" if new_value is None else str(new_value)
        cur_str = "" if current is None else str(current)
        if new_str == cur_str:
            unchanged.append(field)
            continue
        # Deduplicate against the latest observation for this field.
        latest = db.query(MatchObservation).filter_by(
            match_id=match_id, source=source, field=field).order_by(
                MatchObservation.id.desc()).first()
        if latest is not None and (latest.new_value or "") == new_str:
            unchanged.append(field)
            continue
        appended.append(field)
        if not dry_run:
            db.add(MatchObservation(
                match_id=match_id, source=source or "",
                raw_reference=raw_reference,
                observed_at=now, field=field,
                previous_value=cur_str or None, new_value=new_str or None,
                effective_at=effective_at, retrieved_at=retrieved_at,
                payload={"source_match_id": observed.get("source_match_id", "")}))
    if appended and not dry_run:
        db.commit()
    return {"match_id": match_id, "source": source, "appended": appended,
            "unchanged": unchanged, "dry_run": dry_run}


def observation_history(db: Session, match_id: int,
                        field: Optional[str] = None) -> List[Dict]:
    query = db.query(MatchObservation).filter_by(match_id=match_id)
    if field:
        query = query.filter_by(field=field)
    return [{
        "id": r.id, "source": r.source, "raw_reference": r.raw_reference,
        "observed_at": str(r.observed_at), "field": r.field,
        "previous_value": r.previous_value, "new_value": r.new_value,
        "effective_at": str(r.effective_at) if r.effective_at else None,
        "retrieved_at": str(r.retrieved_at) if r.retrieved_at else None,
    } for r in query.order_by(MatchObservation.id.asc()).all()]


def fixture_freshness(db: Session, match_id: int,
                      now: Optional[datetime] = None) -> Dict:
    """fresh | stale | unknown | expired for one fixture.

    Definitions: unknown (no kickoff or no observation); expired (kickoff
    passed without completion, or observation older than 30 days for a
    future fixture); stale (observation older than 7 days); else fresh.
    """
    match = db.get(Match, match_id)
    if match is None:
        return {"state": "unknown", "reason": "match missing"}
    now_naive = as_naive_utc(now or datetime.now(timezone.utc))
    latest = db.query(MatchObservation).filter_by(match_id=match_id).order_by(
        MatchObservation.id.desc()).first()
    if match.kickoff_at is None:
        return {"state": "unknown", "reason": "kickoff unknown",
                "observations": len(observation_history(db, match_id))}
    kickoff = as_naive_utc(match.kickoff_at)
    if match.status not in ("SCHEDULED", "PRE_MATCH", "POSTPONED") \
            or (kickoff is not None and now_naive is not None and kickoff < now_naive):
        if match.status in ("SCHEDULED", "PRE_MATCH", "POSTPONED"):
            return {"state": "expired",
                    "reason": "kickoff passed without completion",
                    "observations": len(observation_history(db, match_id))}
        return {"state": "expired", "reason": f"status {match.status}",
                "observations": len(observation_history(db, match_id))}
    if latest is None:
        return {"state": "unknown", "reason": "no source observation",
                "observations": 0}
    observed = as_naive_utc(latest.observed_at)
    age_days = (now_naive - observed).total_seconds() / 86400.0 \
        if observed and now_naive else None
    if age_days is None:
        return {"state": "unknown", "reason": "observation time unknown",
                "observations": len(observation_history(db, match_id))}
    if age_days > 30:
        state = "expired"
    elif age_days > 7:
        state = "stale"
    else:
        state = "fresh"
    return {"state": state, "age_days": round(age_days, 2),
            "observations": len(observation_history(db, match_id))}

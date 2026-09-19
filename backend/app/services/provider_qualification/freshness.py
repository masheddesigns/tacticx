"""Per-source freshness monitoring (Phase 19).

Freshness states per source/competition/season: fresh | aging | stale |
expired | unknown. Expected intervals come from configuration only —
unknown intervals yield unknown, never an invented threshold.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.config import get_settings

FRESH, AGING, STALE, EXPIRED, UNKNOWN = (
    "fresh", "aging", "stale", "expired", "unknown")


def _expected_interval_hours(source: str, competition: str) -> Optional[float]:
    settings = get_settings()
    raw = getattr(settings, "SOURCE_FRESHNESS_HOURS", "") or ""
    for chunk in raw.split(","):
        if ":" not in chunk:
            continue
        key, _, value = chunk.partition(":")
        if key.strip().lower() == f"{source}:{competition}".lower():
            try:
                return float(value)
            except ValueError:
                return None
    return None


def freshness_for(db: Session, source: str, competition: str = "",
                  season: str = "") -> Dict:
    """Freshness of one source slice from its latest observed fixture."""
    from app.db.models.core import Match

    query = db.query(Match).filter(Match.provider == source)
    if competition:
        from app.db.models.core import League

        league = db.query(League).filter_by(code=competition).first()
        if league is None:
            return {"source": source, "competition": competition,
                    "season": season, "state": UNKNOWN,
                    "reason": "unknown competition"}
        query = query.filter(Match.league_id == league.id)
    latest = query.order_by(Match.kickoff_at.desc()).first()
    now = datetime.now(timezone.utc)
    if latest is None or latest.kickoff_at is None:
        return {"source": source, "competition": competition,
                "season": season, "state": UNKNOWN,
                "reason": "no observed fixtures"}
    kickoff = latest.kickoff_at
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    age_hours = (now - kickoff).total_seconds() / 3600.0
    expected = _expected_interval_hours(source, competition)
    if expected is None:
        return {"source": source, "competition": competition,
                "season": season, "state": UNKNOWN,
                "reason": "no configured expected interval",
                "last_observed_fixture": str(latest.kickoff_at),
                "age_hours": round(age_hours, 1)}
    ratio = age_hours / expected if expected > 0 else float("inf")
    if ratio <= 1:
        state = FRESH
    elif ratio <= 2:
        state = AGING
    elif ratio <= 4:
        state = STALE
    else:
        state = EXPIRED
    return {"source": source, "competition": competition, "season": season,
            "state": state, "age_hours": round(age_hours, 1),
            "expected_hours": expected,
            "last_observed_fixture": str(latest.kickoff_at)}

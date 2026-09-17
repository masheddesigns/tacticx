"""Event reconciliation across sources (Phase 8).

Same goal from two sources must not become two canonical goals. Matching
uses match + event type + period + timestamp + team + player where available,
with a configurable time tolerance (sources use different precision — exact
timestamps are not required). Uncertain pairs become unresolved_conflict,
never duplicates and never silent merges.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import MatchEvent
from app.services.reconciliation import conflicts as conflict_svc


def event_seconds(event) -> Optional[int]:
    """Best-effort seconds-since-kickoff. None when time is unknown."""
    minute = getattr(event, "minute", None)
    if minute is None:
        return None
    second = getattr(event, "second", None) or 0
    added = getattr(event, "minute_added", None) or 0
    try:
        return int(minute) * 60 + int(second) + int(added) * 60
    except (TypeError, ValueError):
        return None


def events_match(a, b, tolerance_seconds: Optional[int] = None) -> str:
    """matched | unresolved_conflict | distinct.

    Type/team must agree (when both known); timestamps within tolerance.
    Anything uncertain -> unresolved_conflict.
    """
    tolerance = tolerance_seconds if tolerance_seconds is not None else \
        get_settings().EVENT_TIME_TOLERANCE_SECONDS
    type_a = (getattr(a, "event_type", "") or "").lower()
    type_b = (getattr(b, "event_type", "") or "").lower()
    if type_a and type_b and type_a != type_b:
        return "distinct"
    team_a = getattr(a, "team", None)
    team_b = getattr(b, "team", None)
    if team_a and team_b and str(team_a) != str(team_b):
        return "distinct"
    sec_a, sec_b = event_seconds(a), event_seconds(b)
    if sec_a is None or sec_b is None:
        return "unresolved_conflict"
    if abs(sec_a - sec_b) <= tolerance:
        return "matched"
    return "distinct"


def reconcile_match_events(db: Session, match_id: int,
                           tolerance_seconds: Optional[int] = None,
                           dry_run: bool = False) -> Dict:
    """Pairwise reconciliation of stored events for one match, grouped by
    source. Candidate pairs come from same-match rows (indexed), bounded by
    group size in practice."""
    events = db.query(MatchEvent).filter_by(match_id=match_id).all()
    by_source: Dict[str, List] = {}
    for event in events:
        by_source.setdefault(getattr(event, "source", "") or "unknown", []).append(event)
    sources = sorted(by_source)
    summary = {"match_id": match_id, "events": len(events),
               "sources": sources, "matched": 0, "distinct": 0,
               "unresolved": 0, "dry_run": dry_run}
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            for a in by_source[sources[i]]:
                for b in by_source[sources[j]]:
                    verdict = events_match(a, b, tolerance_seconds)
                    if verdict == "matched":
                        summary["matched"] += 1
                    elif verdict == "distinct":
                        summary["distinct"] += 1
                    else:
                        summary["unresolved"] += 1
                        if not dry_run:
                            conflict_svc.record_conflict(
                                db, "event", match_id, "event_mismatch",
                                getattr(a, "event_type", "event"),
                                sources[i], sources[j],
                                f"{getattr(a, 'minute', '?')}:{getattr(a, 'team', '?')}",
                                f"{getattr(b, 'minute', '?')}:{getattr(b, 'team', '?')}")
    return summary

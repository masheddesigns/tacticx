"""Canonical field resolvers + version history (Phase 8).

One explicit resolver per field kind — no generic resolver that assumes all
fields behave identically. Every canonical change preserves old/new/source/
reason/timestamp in CanonicalFieldVersion. Reconciliation never touches
prediction tables: prediction snapshots stay isolated by construction (this
module has no import path to prediction storage).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Match
from app.db.models.reconciliation import CanonicalFieldVersion


def field_priority(field: str) -> Optional[str]:
    """Authoritative source for a field from explicit configuration."""
    for chunk in get_settings().FIELD_SOURCE_PRIORITY.split(";"):
        if ":" not in chunk:
            continue
        name, source = chunk.split(":", 1)
        if name.strip() == field:
            return source.strip()
    return None


def _record_version(db: Session, entity_type: str, canonical_id: int,
                    field: str, old_value, new_value, source: str,
                    reason: str) -> None:
    db.add(CanonicalFieldVersion(
        entity_type=entity_type, canonical_entity_id=canonical_id, field=field,
        old_value=None if old_value is None else str(old_value)[:500],
        new_value=None if new_value is None else str(new_value)[:500],
        source=source or "", reason=reason[:500]))


def resolve_match_score(db: Session, match_id: int, home: int, away: int,
                        source: str, dry_run: bool = False) -> Dict:
    """Scores change only from FINISHED observations or the authoritative
    score source; any overwrite of a recorded score is versioned."""
    match = db.get(Match, match_id)
    if match is None:
        return {"status": "unknown_match"}
    current = (match.home_score, match.away_score)
    if current == (home, away):
        return {"status": "unchanged", "score": f"{home}-{away}"}
    if match.home_score is not None and match.away_score is not None:
        reason = (f"score overwrite {match.home_score}-{match.away_score} -> "
                  f"{home}-{away} by {source} (authoritative: {field_priority('score')})")
        if not dry_run:
            _record_version(db, "match", match_id, "score",
                            f"{match.home_score}-{match.away_score}",
                            f"{home}-{away}", source, reason)
            match.home_score, match.away_score = home, away
            db.commit()
        return {"status": "recorded_overwrite" if not dry_run else "would_overwrite",
                "reason": reason}
    reason = f"score set by {source}"
    if not dry_run:
        _record_version(db, "match", match_id, "score", None, f"{home}-{away}",
                        source, reason)
        match.home_score, match.away_score = home, away
        db.commit()
    return {"status": "recorded" if not dry_run else "would_record",
            "score": f"{home}-{away}"}


def resolve_kickoff(db: Session, match_id: int, kickoff_at: datetime,
                    source: str, dry_run: bool = False) -> Dict:
    """Kickoff moves only within tolerance or from the authoritative source;
    finished matches never move. All moves versioned."""
    match = db.get(Match, match_id)
    if match is None:
        return {"status": "unknown_match"}
    if match.kickoff_at is not None and match.kickoff_at == kickoff_at:
        return {"status": "unchanged"}
    if match.status == "FINISHED":
        return {"status": "refused", "reason": "finished matches never move kickoff"}
    try:
        delta_min = abs((match.kickoff_at.replace(tzinfo=None)
                         - kickoff_at.replace(tzinfo=None)).total_seconds()) / 60.0 \
            if match.kickoff_at is not None else 0.0
    except Exception:
        return {"status": "refused", "reason": "incomparable timestamps"}
    tolerance = get_settings().MATCH_KICKOFF_TOLERANCE_MINUTES
    authoritative = field_priority("kickoff")
    if delta_min > tolerance and source != authoritative:
        return {"status": "refused",
                "reason": f"{delta_min:.1f}min exceeds tolerance {tolerance}min "
                          f"and {source} is not authoritative ({authoritative})"}
    reason = f"kickoff {match.kickoff_at} -> {kickoff_at} by {source}"
    if not dry_run:
        _record_version(db, "match", match_id, "kickoff_at",
                        str(match.kickoff_at), str(kickoff_at), source, reason)
        match.kickoff_at = kickoff_at
        db.commit()
    return {"status": "recorded" if not dry_run else "would_record", "reason": reason}


def resolve_match_status(db: Session, match_id: int, status: str,
                         source: str, dry_run: bool = False) -> Dict:
    """Status advances forward only (scheduled -> ... -> finished); finished
    is terminal and never regresses. All transitions versioned."""
    order = ["SCHEDULED", "PRE_MATCH", "LIVE", "HALFTIME", "POSTPONED",
             "CANCELLED", "FINISHED"]
    match = db.get(Match, match_id)
    if match is None:
        return {"status": "unknown_match"}
    if match.status == status:
        return {"status": "unchanged"}
    if match.status == "FINISHED":
        return {"status": "refused", "reason": "FINISHED is terminal"}
    try:
        if order.index(status) < order.index(match.status) and status != "POSTPONED" \
                and status != "CANCELLED":
            return {"status": "refused",
                    "reason": f"status regression {match.status} -> {status} refused"}
    except ValueError:
        return {"status": "refused", "reason": f"unknown status {status!r}"}
    reason = f"status {match.status} -> {status} by {source}"
    if not dry_run:
        _record_version(db, "match", match_id, "status", match.status, status,
                        source, reason)
        match.status = status
        db.commit()
    return {"status": "recorded" if not dry_run else "would_record", "reason": reason}


def resolve_statistic(db: Session, match_id: int, team: str, stat_name: str,
                      period: str, value: str, source: str,
                      dry_run: bool = False) -> Dict:
    """Ingest-time reconciliation for source statistics.

    Schema reality: match_statistics is UNIQUE on (match, team, stat, period)
    with NO source in the key, so two sources cannot co-store one stat. The
    second source therefore reconciles against the stored row BEFORE any
    write: same value -> unchanged; different value -> classify, persist a
    true_conflict, version the change, and apply the authoritative source
    (field priority) or keep the existing value with the conflict open.
    Nothing is ever silently overwritten.
    """
    from app.db.models.core import MatchStatistic
    from app.services.reconciliation import statistics as stats_svc

    existing = db.query(MatchStatistic).filter_by(
        match_id=match_id, team=team, stat_name=stat_name, period=period).first()
    if existing is None:
        if dry_run:
            return {"status": "would_create"}
        row = MatchStatistic(match_id=match_id, team=team, stat_name=stat_name,
                             period=period, stat_value=value, source=source)
        db.add(row)
        db.commit()
        return {"status": "recorded", "row_id": row.id}
    if existing.stat_value == value:
        return {"status": "unchanged", "row_id": existing.id}
    try:
        classification = stats_svc.classify_stat_difference(
            db, stat_name, existing.source or "unknown",
            float(str(existing.stat_value).rstrip("%")),
            source, float(str(value).rstrip("%")))
    except (TypeError, ValueError):
        classification = "unknown"
    authority = field_priority(stat_name)
    if dry_run:
        return {"status": "would_reconcile", "classification": classification,
                "stored": {"value": existing.stat_value,
                           "source": existing.source},
                "incoming": {"value": value, "source": source},
                "authoritative": authority}
    from app.services.reconciliation import conflicts as conflict_svc

    if classification == conflict_svc.CLASS_TRUE_CONFLICT:
        conflict_svc.record_conflict(
            db, "statistic", match_id, "statistic_mismatch",
            f"{team}:{stat_name}:{period}", existing.source or "unknown",
            source, existing.stat_value, value, classification=classification)
    reason = (f"statistic {stat_name} {existing.stat_value} "
              f"({existing.source}) vs {value} ({source}): {classification}; "
              f"authoritative={authority}")
    if authority is not None and authority == source:
        _record_version(db, "statistic", existing.id, stat_name,
                        existing.stat_value, value, source, reason)
        existing.stat_value = value
        existing.source = source
        db.commit()
        return {"status": "recorded_authoritative", "row_id": existing.id,
                "classification": classification, "reason": reason}
    _record_version(db, "statistic", existing.id, stat_name,
                    existing.stat_value, existing.stat_value,
                    existing.source or "",
                    reason + "; kept stored value, conflict open")
    db.commit()
    return {"status": "kept_stored_conflict_open", "row_id": existing.id,
            "classification": classification, "reason": reason}


def resolve_event(db: Session, match_id: int, event: Dict, source: str,
                  dry_run: bool = False) -> Dict:
    """Store a source event row (source-namespaced); dedup happens in the
    reconciliation pass, never by dropping the observation."""
    from app.db.models.core import MatchEvent

    kwargs = {k: event.get(k) for k in ("minute", "minute_added", "second",
                                        "event_type", "detail", "team",
                                        "player_name", "assist_player")
              if event.get(k) is not None}
    kwargs.setdefault("event_type", event.get("event_type", ""))
    if dry_run:
        return {"status": "would_create"}
    row = MatchEvent(match_id=match_id, source=source,
                     source_record_id=str(event.get("source_record_id", "")), **kwargs)
    db.add(row)
    db.commit()
    return {"status": "recorded", "row_id": row.id}

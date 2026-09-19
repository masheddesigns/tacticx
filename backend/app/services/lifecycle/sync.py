"""Idempotent upcoming-match sync (Phase 7).

Canonical resolution reuses the Phase 1.6 identity architecture:
source team -> TeamResolver (mapping, legacy columns, deterministic
normalized-name, aliases — never a new canonical team from spelling alone);
source match -> MatchResolver (mapping, canonical tuple with kickoff
tolerance, same-day fallback). Fixture metadata (kickoff/status/minute) may
advance on re-sync; stored prediction snapshots are never touched here.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.enums import MatchStatus
from app.services.ingestion import SyncStats, _log_sync
from app.services.lifecycle.upcoming import UpcomingMatch, UpcomingMatchSource

STATUS_TO_MATCH = {
    "scheduled": MatchStatus.SCHEDULED.value,
    "postponed": MatchStatus.POSTPONED.value,
    "cancelled": MatchStatus.CANCELLED.value,
    "abandoned": MatchStatus.CANCELLED.value,
    "live": MatchStatus.LIVE.value,
    "finished": MatchStatus.FINISHED.value,
    "unknown": MatchStatus.SCHEDULED.value,
}


def sync_upcoming_matches(db: Session, records: List[UpcomingMatch],
                          operation: str = "sync_upcoming") -> SyncStats:
    """Resolve + upsert canonical matches. Idempotent: re-running the same
    records updates metadata in place and creates nothing new."""
    from app.services.identity.matches import MatchResolver
    from app.services.identity.teams import TeamIdentityResolver as TeamResolver

    stats, start = SyncStats(), time.monotonic()
    match_resolver = MatchResolver(db)
    team_resolver = TeamResolver(db)
    by_source: Dict[str, SyncStats] = {}
    for record in records:
        stats.received += 1
        src_stats = by_source.setdefault(record.source or "unknown", SyncStats())
        src_stats.received += 1
        try:
            league_id = None
            league_code = ""
            if record.league_code:
                league = db.query(League).filter_by(code=record.league_code).first()
                if league is None:
                    stats.skipped += 1
                    src_stats.skipped += 1
                    continue
                league_id, league_code = league.id, league.code
            home_id, _ = team_resolver.resolve(
                record.source, provider_team_name=record.home_team,
                league=league_code)
            away_id, _ = team_resolver.resolve(
                record.source, provider_team_name=record.away_team,
                league=league_code)
            if home_id is None or away_id is None:
                stats.skipped += 1
                src_stats.skipped += 1
                stats.errors.append(
                    f"unresolved teams: {record.home_team} vs {record.away_team}")
                continue
            status = STATUS_TO_MATCH.get(record.status, MatchStatus.SCHEDULED.value)
            match_id, created = match_resolver.ensure(
                record.source, source_match_id=record.source_match_id,
                league_id=league_id, home_team_id=home_id, away_team_id=away_id,
                kickoff_at=record.kickoff_utc, status=status,
                home_score=record.home_score, away_score=record.away_score)
            if created:
                stats.inserted += 1
                src_stats.inserted += 1
            else:
                changed = _refresh_metadata(
                    db, match_id, record.kickoff_utc, status, league_code)
                if changed:
                    stats.updated += 1
                    src_stats.updated += 1
                else:
                    stats.skipped += 1
                    src_stats.skipped += 1
        except Exception as exc:
            db.rollback()
            stats.errors.append(str(exc)[:300])
            src_stats.errors.append(str(exc)[:300])
    duration = time.monotonic() - start
    for source, src_stats in by_source.items():
        _log_sync(db, source, operation, src_stats, duration=duration / max(1, len(by_source)))
    return stats


def _refresh_metadata(db: Session, match_id: int, kickoff_utc,
                      status: str, league_code: str) -> bool:
    """Advance kickoff/status/minute on the canonical row. Returns True when
    anything changed. Finished matches keep their recorded scores; an update
    never rewrites a finished score to a different value silently — score
    conflicts are left for reconciliation (recorded, not merged)."""
    match = db.get(Match, match_id)
    if match is None:
        return False
    changed = False
    if kickoff_utc is not None and match.kickoff_at != kickoff_utc:
        # Never move a finished match's kickoff (historical record).
        if match.status != MatchStatus.FINISHED.value:
            match.kickoff_at = kickoff_utc
            changed = True
    if status and match.status != status:
        # Finished is terminal for scores, but status itself may still
        # advance (e.g. scheduled -> finished discovered late).
        if match.status == MatchStatus.FINISHED.value and status != MatchStatus.FINISHED.value:
            pass
        else:
            match.status = status
            changed = True
    if changed:
        db.commit()
    return changed


def upcoming_window(hours: Optional[int] = None) -> tuple:
    """(from_time, to_time) for discovery. Lookahead comes from config."""
    from app.config import get_settings

    span = hours if hours is not None else get_settings().NEXT_MATCH_LOOKAHEAD_HOURS
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    return now, now + timedelta(hours=max(1, span))

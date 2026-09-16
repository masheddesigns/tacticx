"""Background jobs: fixture sync, live refresh, odds snapshots.

Each job is idempotent (ingestion layer) and emits DataSyncLog rows.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.db.models.core import League, Match
from app.db.models.enums import MatchStatus
from app.db.session import get_session_local
from app.logging_config import get_logger
from app.services import ingestion
from app.services.providers import get_football_provider, get_odds_provider
from app.workers.celery_app import celery_app

log = get_logger(__name__)

LIVE_STATUSES = {MatchStatus.LIVE.value, MatchStatus.HALFTIME.value}


def _db():
    return get_session_local()()


@celery_app.task(name="app.workers.tasks.sync_fixtures_task")
def sync_fixtures_task() -> dict:
    from app.config import get_settings

    db = _db()
    try:
        provider = get_football_provider(db_session_factory=get_session_local)
        total = {"received": 0, "inserted": 0}
        for entry in get_settings().supported_leagues_parsed():
            lg, _ = ingestion.upsert_league(
                db, code=entry["code"], name=entry["code"], provider=provider.provider_name,
                provider_league_id=entry["provider_id"], season=entry["season"])
            fixtures = asyncio.run(provider.get_fixtures(entry["provider_id"], entry["season"]))
            stats = ingestion.sync_fixtures(db, fixtures, league_code=entry["code"], league_id=lg.id)
            total["received"] += stats.received
            total["inserted"] += stats.inserted
        log.info("sync_fixtures_task done received=%d inserted=%d", total["received"], total["inserted"])
        return total
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.sync_live_task")
def sync_live_task() -> dict:
    """Refresh only matches that are live/halftime or kicking off within the near window."""
    from app.config import get_settings

    db = _db()
    try:
        provider = get_football_provider(db_session_factory=get_session_local)
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=get_settings().NEAR_KICKOFF_HOURS)
        matches = (
            db.query(Match)
            .filter(
                (Match.status.in_(list(LIVE_STATUSES)))
                | ((Match.status.in_([MatchStatus.SCHEDULED.value, MatchStatus.PRE_MATCH.value]))
                   & (Match.kickoff_at <= horizon))
            ).all()
        )
        refreshed = 0
        for m in matches:
            fx = asyncio.run(provider.get_match(m.provider_match_id))
            if fx:
                ingestion.upsert_match(db, fx, m.league_id, m.home_team_id, m.away_team_id)
                refreshed += 1
            if m.status in LIVE_STATUSES:
                asyncio.run(ingestion._async_sync_details(db, m, provider))
        return {"checked": len(matches), "refreshed": refreshed}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.sync_odds_task")
def sync_odds_task() -> dict:
    db = _db()
    try:
        odds_provider = get_odds_provider(db_session_factory=get_session_local)
        now = datetime.now(timezone.utc)
        matches = (
            db.query(Match)
            .filter(Match.kickoff_at >= now - timedelta(hours=3),
                    Match.kickoff_at <= now + timedelta(hours=48))
            .all()
        )
        stored = 0
        for m in matches[:50]:  # quota guard: bounded batch per run
            snaps = asyncio.run(odds_provider.get_odds())
            stats = ingestion.store_odds_snapshots(
                db, m.id, snaps, odds_provider.provider_name,
                is_live=(m.status in LIVE_STATUSES))
            stored += stats.inserted
        return {"matches": len(matches), "selections_stored": stored}
    finally:
        db.close()

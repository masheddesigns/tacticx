"""Idempotent ingestion: same fixture fetched 5x -> ONE match row.

All writes keyed on (provider, provider_*_id) unique constraints; re-runs only
update mutable fields (score, minute, status). Every run emits a DataSyncLog.
"""
from __future__ import annotations

from typing import Optional

import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.core import (
    League, Lineup, Match, MatchEvent, MatchStatistic, Standing, Team,
)
from app.db.models.logs import DataSyncLog
from app.db.models.odds import Bookmaker, Market, OddsSelection, OddsSnapshot
from app.logging_config import get_logger
from app.services.base import FootballDataProvider, OddsProvider
from app.services.dtos import FixtureDTO

log = get_logger(__name__)


class SyncStats:
    def __init__(self):
        self.received = 0
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.errors: list[str] = []


def _log_sync(db: Session, provider: str, operation: str, stats: SyncStats,
              league: str = "", match_id: Optional[int] = None, duration: float = 0.0) -> None:
    db.add(DataSyncLog(
        provider=provider, operation=operation, league=league, match_id=match_id,
        records_received=stats.received, records_inserted=stats.inserted,
        records_updated=stats.updated, records_skipped=stats.skipped,
        duration_seconds=duration, errors="; ".join(stats.errors)[:1000],
    ))
    db.commit()


def upsert_league(db: Session, *, code: str, name: str, provider: str,
                  provider_league_id: str, season: str, country: Optional[str] = None) -> tuple[League, bool]:
    row = db.query(League).filter_by(code=code).first()
    if row:
        row.name = name
        row.provider = provider
        row.provider_league_id = provider_league_id
        row.season = season
        if country:
            row.country = country
        db.commit()
        return row, False
    row = League(code=code, name=name, provider=provider,
                 provider_league_id=provider_league_id, season=season, country=country)
    db.add(row)
    db.commit()
    return row, True


def upsert_team(db: Session, *, provider: str, provider_team_id: str, name: str,
                league_id: Optional[int] = None, short_name: Optional[str] = None,
                country: Optional[str] = None) -> tuple[Team, bool]:
    row = db.query(Team).filter_by(provider=provider, provider_team_id=provider_team_id).first()
    if row:
        touched = False
        if row.name != name:
            row.name = name
            touched = True
        if league_id and row.league_id != league_id:
            row.league_id = league_id
            touched = True
        db.commit()
        return row, False
    row = Team(provider=provider, provider_team_id=provider_team_id, name=name,
               league_id=league_id, short_name=short_name, country=country)
    db.add(row)
    db.commit()
    return row, True


def _norm_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def find_match_for_odds_event(db: Session, home_team: Optional[str], away_team: Optional[str],
                              commence_time=None) -> Optional[Match]:
    """Link a provider odds event to our Match via team names.

    Conservative: both names must match (case-insensitive exact). When several
    candidates exist, prefer one kicking off near commence_time. Returns None
    when ambiguous or unmatched — never guess, odds without a match stay
    unstored and are reported as such.
    """
    home, away = _norm_name(home_team), _norm_name(away_team)
    if not home or not away:
        return None
    candidates = []
    for m in db.query(Match).all():
        h = db.get(Team, m.home_team_id) if m.home_team_id else None
        a = db.get(Team, m.away_team_id) if m.away_team_id else None
        if h and a and _norm_name(h.name) == home and _norm_name(a.name) == away:
            candidates.append(m)
    if not candidates:
        return None
    if len(candidates) == 1 or commence_time is None:
        return candidates[0] if len(candidates) == 1 else None
    try:
        from datetime import timedelta
        within = [m for m in candidates
                  if m.kickoff_at and abs(m.kickoff_at - commence_time) <= timedelta(hours=36)]
        return within[0] if len(within) == 1 else None
    except Exception:  # noqa: BLE001 — timezone-naive comparisons etc: stay safe
        return None


def upsert_match(db: Session, fx: FixtureDTO, league_id: Optional[int],
                 home_id: Optional[int], away_id: Optional[int]) -> tuple[Match, bool]:
    row = db.query(Match).filter_by(provider=fx.provider, provider_match_id=fx.provider_match_id).first()
    if row:
        changed = False
        for attr in ("status", "minute", "home_score", "away_score", "kickoff_at"):
            new = getattr(fx, attr)
            if getattr(row, attr) != new:
                setattr(row, attr, new)
                changed = True
        if league_id and row.league_id != league_id:
            row.league_id = league_id
            changed = True
        if home_id and row.home_team_id != home_id:
            row.home_team_id = home_id
            changed = True
        if away_id and row.away_team_id != away_id:
            row.away_team_id = away_id
            changed = True
        db.commit()
        return row, False
    row = Match(league_id=league_id, home_team_id=home_id, away_team_id=away_id,
                kickoff_at=fx.kickoff_at, status=fx.status, minute=fx.minute,
                home_score=fx.home_score, away_score=fx.away_score,
                provider=fx.provider, provider_match_id=fx.provider_match_id)
    db.add(row)
    db.commit()
    return row, True


def sync_leagues(db: Session, leagues: list, provider_name: str) -> SyncStats:
    stats, start = SyncStats(), time.monotonic()
    for dto in leagues:
        stats.received += 1
        try:
            _, created = upsert_league(
                db, code=dto.code, name=dto.name, provider=dto.provider or provider_name,
                provider_league_id=dto.provider_league_id, season=dto.season, country=dto.country)
            stats.inserted += created
            stats.updated += (not created)
        except Exception as exc:  # noqa: BLE001 — recorded in sync log, run continues
            db.rollback()
            stats.errors.append(str(exc)[:300])
            log.warning("league sync failed: %s", exc)
    _log_sync(db, provider_name, "sync_leagues", stats, duration=time.monotonic() - start)
    return stats


def sync_fixtures(db: Session, fixtures: list[FixtureDTO], league_code: str = "",
                  league_id: Optional[int] = None) -> SyncStats:
    stats, start = SyncStats(), time.monotonic()
    for fx in fixtures:
        stats.received += 1
        try:
            home, h_created = upsert_team(db, provider=fx.provider, provider_team_id=fx.home_team_id,
                                          name=fx.home_team_name, league_id=league_id)
            away, a_created = upsert_team(db, provider=fx.provider, provider_team_id=fx.away_team_id,
                                          name=fx.away_team_name, league_id=league_id)
            stats.inserted += h_created + a_created
            _, m_created = upsert_match(db, fx, league_id, home.id, away.id)
            if m_created:
                stats.inserted += 1
            else:
                stats.updated += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            stats.errors.append(str(exc)[:300])
            log.warning("fixture sync failed: %s", exc)
    provider = fixtures[0].provider if fixtures else ""
    _log_sync(db, provider, "sync_fixtures", stats, league=league_code, duration=time.monotonic() - start)
    return stats


def sync_match_details(db: Session, match: Match, provider: FootballDataProvider) -> SyncStats:
    """Fetch + store statistics, events, lineups for one match (async provider)."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(_async_sync_details(db, match, provider))


async def _async_sync_details(db: Session, match: Match, provider: FootballDataProvider) -> SyncStats:
    stats, start = SyncStats(), time.monotonic()
    pid = match.provider_match_id
    try:
        for s in await provider.get_match_statistics(pid):
            stats.received += 1
            row = db.query(MatchStatistic).filter_by(
                match_id=match.id, team=s.team, stat_name=s.stat_name, period=s.period).first()
            if row:
                if row.stat_value != s.stat_value:
                    row.stat_value = s.stat_value
                    stats.updated += 1
                else:
                    stats.skipped += 1
            else:
                db.add(MatchStatistic(match_id=match.id, team=s.team, stat_name=s.stat_name,
                                      stat_value=s.stat_value, period=s.period))
                stats.inserted += 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        stats.errors.append(f"statistics: {exc}"[:300])
    try:
        for e in await provider.get_match_events(pid):
            stats.received += 1
            exists = db.query(MatchEvent).filter_by(
                provider=e.provider, provider_event_id=e.provider_event_id).first()
            if exists:
                stats.skipped += 1
            else:
                db.add(MatchEvent(match_id=match.id, minute=e.minute, event_type=e.event_type,
                                  detail=e.detail, team=e.team, player_name=e.player_name,
                                  provider=e.provider, provider_event_id=e.provider_event_id))
                stats.inserted += 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        stats.errors.append(f"events: {exc}"[:300])
    try:
        for lu in await provider.get_lineups(pid):
            stats.received += 1
            exists = db.query(Lineup).filter_by(
                match_id=match.id, team=lu.team, player_name=lu.player_name).first()
            if exists:
                stats.skipped += 1
            else:
                db.add(Lineup(match_id=match.id, team=lu.team, player_name=lu.player_name,
                              position=lu.position, is_starting=lu.is_starting))
                stats.inserted += 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        stats.errors.append(f"lineups: {exc}"[:300])
    _log_sync(db, match.provider or "unknown", "sync_match_details", stats,
              match_id=match.id, duration=time.monotonic() - start)
    return stats


def sync_standings(db: Session, league_id: int, season: str, rows: list,
                   provider_name: str, league_code: str = "") -> SyncStats:
    stats, start = SyncStats(), time.monotonic()
    for dto in rows:
        stats.received += 1
        try:
            team, t_created = upsert_team(db, provider=provider_name,
                                          provider_team_id=dto.team_provider_id,
                                          name=dto.team_name or dto.team_provider_id,
                                          league_id=league_id)
            stats.inserted += t_created
            row = db.query(Standing).filter_by(
                league_id=league_id, team_id=team.id, season=season).first()
            if row:
                row.position, row.played = dto.position, dto.played
                row.won, row.drawn, row.lost, row.points = dto.won, dto.drawn, dto.lost, dto.points
                stats.updated += 1
            else:
                db.add(Standing(league_id=league_id, team_id=team.id, season=season,
                                position=dto.position, played=dto.played, won=dto.won,
                                drawn=dto.drawn, lost=dto.lost, points=dto.points))
                stats.inserted += 1
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            stats.errors.append(str(exc)[:300])
    _log_sync(db, provider_name, "sync_standings", stats, league=league_code,
              duration=time.monotonic() - start)
    return stats


def _dedup_hash(match_id: int, bookmaker: str, market: str, selection: str,
                odds: float, ts) -> str:
    raw = f"{match_id}|{bookmaker}|{market}|{selection}|{odds}|{ts}"
    return hashlib.sha256(raw.encode()).hexdigest()


# Public alias for the source-agnostic pipeline (same dedup domain).
dedup_hash = _dedup_hash


def store_odds_snapshots(db: Session, match_id: int, snapshots: list,
                         provider_name: str, is_live: bool = False) -> SyncStats:
    """Append-only: identical re-delivery is skipped via dedup_hash, price moves
    always create NEW rows (history is never overwritten)."""
    stats, start = SyncStats(), time.monotonic()
    for snap in snapshots:
        stats.received += 1
        try:
            bm = db.query(Bookmaker).filter_by(
                provider=provider_name, provider_bookmaker_id=snap.bookmaker_provider_id).first()
            if not bm:
                bm = Bookmaker(name=snap.bookmaker, provider=provider_name,
                               provider_bookmaker_id=snap.bookmaker_provider_id)
                db.add(bm)
                db.flush()
            if not db.query(Market).filter_by(market_key=snap.market_type).first():
                db.add(Market(market_key=snap.market_type))
                db.flush()
            ts = snap.timestamp or datetime.now(timezone.utc)
            shot = OddsSnapshot(match_id=match_id, bookmaker_id=bm.id,
                                market_type=snap.market_type, timestamp=ts,
                                source=provider_name, is_live=is_live or snap.is_live)
            db.add(shot)
            db.flush()
            for sel in snap.selections:
                dh = _dedup_hash(match_id, snap.bookmaker_provider_id, snap.market_type,
                                 sel.selection, sel.odds, ts.isoformat())
                if db.query(OddsSelection).filter_by(dedup_hash=dh).first():
                    stats.skipped += 1
                    continue
                db.add(OddsSelection(snapshot_id=shot.id, selection=sel.selection,
                                     odds=sel.odds, point=sel.point, dedup_hash=dh))
                stats.inserted += 1
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            stats.errors.append(str(exc)[:300])
    _log_sync(db, provider_name, "store_odds", stats, match_id=match_id,
              duration=time.monotonic() - start)
    return stats

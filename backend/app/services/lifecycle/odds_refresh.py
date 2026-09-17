"""Odds refresh: append-only snapshots + current market state (Phase 7).

Every newly observed odds state is appended, never rewritten. Identity of an
observation is its dedup hash (match, bookmaker, market, timestamp,
selections, prices); re-polling the same state creates nothing new.
Corrections are recorded as new rows, never edits.

Current market state = latest valid snapshot per book/market at now, with
consensus/overround/movement from the Phase 3 services. Current ≠ closing:
closing snapshots are labeled and reported separately, never merged.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Match
from app.db.models.odds import Bookmaker, OddsSelection, OddsSnapshot
from app.services.dtos import OddsSnapshotDTO
from app.services.ingestion import SyncStats, _log_sync


def observation_hash(match_id: int, bookmaker: str, market_type: str,
                     timestamp, selections: list) -> str:
    canonical = json.dumps({
        "match_id": match_id, "bookmaker": bookmaker, "market": market_type,
        "timestamp": str(timestamp),
        "selections": sorted((s.selection, s.odds, s.point) for s in selections),
    }, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def store_snapshot(db: Session, match_id: int, dto: OddsSnapshotDTO,
                   source: str = "odds_api") -> tuple:
    """Append one snapshot + selections. Returns (snapshot_id, created).

    Idempotent on the observation hash: identical re-polls return the
    existing row. Timestamp unknown -> refused (strict) since an undated
    observation cannot be placed before any cutoff.
    """
    if dto.timestamp is None:
        return None, False, "timestamp unknown: observation refused"
    naive = dto.timestamp if dto.timestamp.tzinfo is None else \
        dto.timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    book = db.query(Bookmaker).filter_by(
        provider="odds_api", provider_bookmaker_id=dto.bookmaker_provider_id or dto.bookmaker).first()
    if book is None:
        book = db.query(Bookmaker).filter_by(name=dto.bookmaker).first()
    if book is None:
        book = Bookmaker(name=dto.bookmaker or dto.bookmaker_provider_id,
                         provider="odds_api",
                         provider_bookmaker_id=dto.bookmaker_provider_id or dto.bookmaker)
        db.add(book)
        db.flush()
    digest = observation_hash(match_id, book.name, dto.market_type, naive,
                              dto.selections)
    # Exact-duplicate check: same match/book/market/timestamp already stored.
    dupe = db.query(OddsSnapshot).filter_by(
        match_id=match_id, bookmaker_id=book.id, market_type=dto.market_type,
        timestamp=naive).first()
    if dupe is not None:
        have = {(r.selection, r.odds) for r in
                db.query(OddsSelection).filter_by(snapshot_id=dupe.id).all()}
        want = {(s.selection, s.odds) for s in dto.selections}
        if have == want:
            return dupe.id, False, "duplicate observation"
    snap = OddsSnapshot(match_id=match_id, bookmaker_id=book.id,
                        market_type=dto.market_type, timestamp=naive,
                        source=source, is_live=bool(dto.is_live))
    db.add(snap)
    db.flush()
    for selection in dto.selections:
        db.add(OddsSelection(
            snapshot_id=snap.id, selection=selection.selection,
            odds=selection.odds, point=selection.point,
            dedup_hash=f"{digest}-{selection.selection}"))
    db.commit()
    return snap.id, True, ""


def resolve_match_for_event(db: Session, home_team: Optional[str],
                            away_team: Optional[str],
                            commence_time) -> Optional[int]:
    """Match an odds event to a canonical match. Teams resolve via the
    identity layer; commence time must fall within kickoff tolerance.
    Unresolvable events return None (never guessed)."""
    from app.services.identity.matches import KICKOFF_TOLERANCE
    from app.services.identity.teams import TeamIdentityResolver as TeamResolver

    if not home_team or not away_team:
        return None
    resolver = TeamResolver(db)
    home_id, _ = resolver.resolve("odds_api", provider_team_name=home_team)
    away_id, _ = resolver.resolve("odds_api", provider_team_name=away_team)
    if home_id is None or away_id is None:
        return None
    query = db.query(Match).filter(Match.home_team_id == home_id,
                                   Match.away_team_id == away_id)
    if commence_time is not None:
        naive = commence_time if commence_time.tzinfo is None else \
            commence_time.astimezone(timezone.utc).replace(tzinfo=None)
        candidates = [m for m in query.all()
                      if m.kickoff_at is not None
                      and abs((m.kickoff_at - naive).total_seconds()) <=
                      KICKOFF_TOLERANCE.total_seconds()]
        if len(candidates) == 1:
            return candidates[0].id
        return None
    rows = query.all()
    return rows[0].id if len(rows) == 1 else None


def refresh_odds(db: Session, dtos: List[OddsSnapshotDTO],
                 source: str = "odds_api") -> SyncStats:
    """Store a poll of odds DTOs (append-only). Unmatched events are skipped
    with reasons; per-event failures never abort the batch."""
    stats, start = SyncStats(), time.monotonic()
    for dto in dtos:
        stats.received += 1
        try:
            match_id = resolve_match_for_event(db, dto.home_team, dto.away_team,
                                               dto.commence_time)
            if match_id is None:
                stats.skipped += 1
                stats.errors.append(
                    f"unmatched event: {dto.home_team} vs {dto.away_team}")
                continue
            _, created, note = store_snapshot(db, match_id, dto, source=source)
            if created:
                stats.inserted += 1
            else:
                stats.skipped += 1
                if note and note != "duplicate observation":
                    stats.errors.append(note)
        except Exception as exc:
            db.rollback()
            stats.errors.append(str(exc)[:300])
    _log_sync(db, source, "refresh_odds", stats, duration=time.monotonic() - start)
    return stats


def get_current_market_state(db: Session, match_id: int,
                             market: str = "h2h") -> Dict:
    """Latest valid snapshot per bookmaker + consensus + overround + movement.

    Closing snapshots are reported under `closing` and excluded from the
    current consensus. Stale/fresh status derives from snapshot age vs the
    configured refresh interval.
    """
    from app.services.market.consensus import consensus
    from app.services.market.probabilities import (
        market_completeness,
        no_vig_probabilities,
        overround,
    )
    from app.services.market.repository import snapshots_before
    from app.services.market.timeline import timeline

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    snaps = snapshots_before(db, match_id, datetime.now(timezone.utc), market)
    latest: Dict = {}
    for snap in snaps:
        key = snap.bookmaker_id
        if key not in latest or (snap.timestamp, snap.id) >= (
                latest[key].timestamp, latest[key].id):
            latest[key] = snap
    books, per_book, raw_complete, closing = [], {}, [], None
    for bookmaker_id, snap in latest.items():
        rows = db.query(OddsSelection).filter_by(snapshot_id=snap.id).all()
        selections = {r.selection: r.odds for r in rows if r.selection}
        if not selections:
            continue
        market_id = snap.source_market_id or ""
        is_closing = (":" in market_id and len(market_id.split(":", 1)[0]) > 1
                      and market_id.split(":", 1)[0].endswith("C"))
        book = db.get(Bookmaker, bookmaker_id) if bookmaker_id else None
        entry = {"bookmaker": book.name if book and book.name else str(bookmaker_id),
                 "timestamp": str(snap.timestamp), "is_closing": is_closing,
                 "completeness": market_completeness(market, list(selections)),
                 "selections": selections}
        books.append(entry)
        if is_closing:
            continue
        if entry["completeness"] != "complete":
            continue
        raw_complete.append(selections)
        probs, _ = no_vig_probabilities(selections)
        if probs:
            per_book[entry["bookmaker"]] = probs
    agreed = consensus(per_book) if per_book else {"values": {}, "bookmakers_used": 0}
    over, over_pct, _ = overround(raw_complete[0]) if raw_complete else (None, None, None)
    movement = {}
    if match_id is not None:
        points = []
        for snap in sorted(snaps, key=lambda s: (s.timestamp, s.id)):
            rows = db.query(OddsSelection).filter_by(snapshot_id=snap.id).all()
            home = next((r.odds for r in rows if r.selection == "home"), None)
            if home:
                points.append((snap.timestamp, home))
        if len(points) >= 2:
            movement = timeline(points)
    interval = get_settings().ODDS_REFRESH_INTERVAL_MINUTES * 60
    ages = [(now - s.timestamp).total_seconds() for s in latest.values()
            if s.timestamp]
    freshness = "fresh" if ages and max(ages) <= interval else (
        "stale" if ages else "unknown")
    return {
        "match_id": match_id, "market": market,
        "bookmakers": books, "consensus": agreed,
        "overround": {"probability": over, "percent": over_pct},
        "movement": movement, "freshness": freshness,
        "stale": freshness == "stale",
        "as_of": str(now),
    }

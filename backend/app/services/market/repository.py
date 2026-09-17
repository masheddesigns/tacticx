"""Historical market reconstruction (Phase 3).

get_market_state(match_id, cutoff, market) returns the latest valid market
state at the cutoff — NEVER a later observation. Enforcement lives here, in
the repository layer, so no caller can accidentally use future odds.

Completeness: complete | partial | insufficient (+ unknown for unmapped
markets). Standard 1X2 overround is only computed from complete markets.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Match
from app.db.models.odds import Bookmaker, OddsSelection, OddsSnapshot
from app.services.features.temporal import as_naive_utc
from app.services.market.probabilities import (
    MARKET_PROBABILITY_V1,
    market_completeness,
    validate_price,
)


def _is_closing(snapshot: OddsSnapshot) -> bool:
    """Closing lines carry a C-suffixed bookmaker prefix in source_market_id
    (e.g. B365C:h2h, PSC:h2h) — built deterministically by our own pipeline.
    Foreign rows without such IDs are never labeled closing."""
    market_id = snapshot.source_market_id or ""
    if ":" not in market_id:
        return False
    prefix = market_id.split(":", 1)[0]
    return len(prefix) > 1 and prefix.endswith("C")


def snapshots_before(db: Session, match_id: int, cutoff: datetime,
                     market: Optional[str] = None) -> List[OddsSnapshot]:
    """All snapshots with timestamp <= cutoff. Bounded per match — never the
    whole table (uses the composite match/market/time index)."""
    naive_cutoff = as_naive_utc(cutoff)
    query = db.query(OddsSnapshot).filter(
        OddsSnapshot.match_id == match_id,
        OddsSnapshot.timestamp <= naive_cutoff,
    )
    if market:
        query = query.filter(OddsSnapshot.market_type == market)
    return query.order_by(OddsSnapshot.timestamp.asc(), OddsSnapshot.id.asc()).all()


def _selections(db: Session, snapshot_id: int) -> Dict[str, Dict]:
    rows = db.query(OddsSelection).filter_by(snapshot_id=snapshot_id).all()
    out = {}
    for row in rows:
        ok, _ = validate_price(row.odds)
        if ok:
            out[row.selection] = {"price": row.odds, "point": row.point}
    return out


def get_market_state(db: Session, match_id: int, cutoff: datetime,
                     market: str = "h2h") -> Dict:
    """Latest valid market state available at cutoff for one market."""
    match = db.get(Match, match_id)
    if match is None:
        return {"error": "match not found", "market": market}
    window_minutes = get_settings().ODDS_CONSENSUS_TIME_WINDOW_MINUTES
    snaps = snapshots_before(db, match_id, cutoff, market)
    # Latest snapshot per bookmaker at or before the cutoff.
    latest: Dict[Optional[int], OddsSnapshot] = {}
    for snap in snaps:
        latest[snap.bookmaker_id] = snap
    bookmakers = []
    timestamps = []
    complete_books = 0
    partial_books = 0
    for bookmaker_id, snap in latest.items():
        bookmaker = db.get(Bookmaker, bookmaker_id) if bookmaker_id else None
        selections = _selections(db, snap.id)
        completeness = market_completeness(market, list(selections))
        if completeness == "complete":
            complete_books += 1
        elif completeness == "partial":
            partial_books += 1
        timestamps.append(snap.timestamp)
        bookmakers.append({
            "bookmaker": bookmaker.name if bookmaker else "",
            "bookmaker_id": bookmaker.provider_bookmaker_id if bookmaker else "",
            "selections": selections,
            "completeness": completeness,
            "timestamp": str(snap.timestamp),
            "is_closing": _is_closing(snap),
        })
    if complete_books >= 1:
        state_completeness = "complete"
    elif partial_books > 0:
        state_completeness = "partial"
    else:
        state_completeness = "insufficient"
    naive_times = [as_naive_utc(t) for t in timestamps if t is not None]
    if len(naive_times) > 1:
        spread_minutes = (max(naive_times) - min(naive_times)).total_seconds() / 60.0
        timestamp_quality = "simultaneous" if spread_minutes <= window_minutes else "spread"
    elif naive_times:
        timestamp_quality = "simultaneous"
    else:
        timestamp_quality = "unknown"
    return {
        "match_id": match_id,
        "market": market,
        "cutoff": str(as_naive_utc(cutoff)),
        "bookmakers_available": len(bookmakers),
        "selections_available": sorted({s for b in bookmakers for s in b["selections"]}),
        "timestamp": str(max(timestamps)) if timestamps else None,
        "timestamp_quality": timestamp_quality,
        "market_completeness": state_completeness,
        "bookmakers": sorted(bookmakers, key=lambda b: b["bookmaker"]),
        "calculation_version": MARKET_PROBABILITY_V1,
    }


def closing_state(db: Session, match_id: int, market: str = "h2h") -> Dict:
    """Latest closing-flagged snapshots regardless of time (benchmark only).

    Closing lines must NEVER feed a pre-closing prediction; this helper is
    for comparison display and must be paired with cutoff checks by callers.
    """
    snaps = db.query(OddsSnapshot).filter_by(match_id=match_id, market_type=market).all()
    closing = [s for s in snaps if _is_closing(s)]
    if not closing:
        return {"match_id": match_id, "market": market, "available": False}
    latest: Dict[Optional[int], OddsSnapshot] = {}
    for snap in sorted(closing, key=lambda s: (s.timestamp, s.id)):
        latest[snap.bookmaker_id] = snap
    bookmakers = []
    for bookmaker_id, snap in latest.items():
        bookmaker = db.get(Bookmaker, bookmaker_id) if bookmaker_id else None
        bookmakers.append({
            "bookmaker": bookmaker.name if bookmaker else "",
            "selections": _selections(db, snap.id),
            "timestamp": str(snap.timestamp),
        })
    return {"match_id": match_id, "market": market, "available": True,
            "bookmakers": sorted(bookmakers, key=lambda b: b["bookmaker"]),
            "calculation_version": MARKET_PROBABILITY_V1}

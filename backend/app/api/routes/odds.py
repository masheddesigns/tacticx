"""Odds endpoints: current snapshot, full history, movement summary."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.db.models.odds import Bookmaker, OddsSelection, OddsSnapshot
from app.schemas.schemas import OddsMovementOut, OddsSelectionOut, OddsSnapshotOut
from app.utils.odds_math import movement

router = APIRouter(tags=["odds"])


def _snapshots(match_id: int, db: Session, market: Optional[str], bookmaker: Optional[str]):
    q = db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match_id)
    if market:
        q = q.filter(OddsSnapshot.market_type == market)
    if bookmaker:
        bm_ids = [b.id for b in db.query(Bookmaker).filter(Bookmaker.name.ilike(f"%{bookmaker}%")).all()]
        q = q.filter(OddsSnapshot.bookmaker_id.in_(bm_ids))
    return q.order_by(OddsSnapshot.timestamp)


def _snapshot_out(s: OddsSnapshot, db: Session) -> OddsSnapshotOut:
    bm = db.get(Bookmaker, s.bookmaker_id) if s.bookmaker_id else None
    sels = db.query(OddsSelection).filter_by(snapshot_id=s.id).all()
    return OddsSnapshotOut(
        bookmaker=bm.name if bm else "", market_type=s.market_type, timestamp=s.timestamp,
        is_live=s.is_live,
        selections=[OddsSelectionOut(selection=x.selection, odds=x.odds, point=x.point,
                                      timestamp=s.timestamp) for x in sels],
    )


@router.get("/odds", summary="Latest odds snapshots (filter by match)")
def list_odds(db: Session = Depends(get_db), match_id: Optional[int] = Query(None),
              market: Optional[str] = Query(None)):
    q = db.query(OddsSnapshot).order_by(OddsSnapshot.timestamp.desc())
    if match_id:
        q = q.filter(OddsSnapshot.match_id == match_id)
    if market:
        q = q.filter(OddsSnapshot.market_type == market)
    rows = q.limit(50).all()
    return {"data": [_snapshot_out(s, db) for s in rows]}


@router.get("/odds/{match_id}", summary="Current (latest) odds for a match")
def current_odds(match_id: int, db: Session = Depends(get_db),
                 market: Optional[str] = Query(None), bookmaker: Optional[str] = Query(None)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    # Latest snapshot per (bookmaker, market).
    rows = _snapshots(match_id, db, market, bookmaker).all()
    latest: dict[tuple, OddsSnapshot] = {}
    for s in rows:
        latest[(s.bookmaker_id, s.market_type)] = s
    return {"data": [_snapshot_out(s, db) for s in latest.values()]}


@router.get("/matches/{match_id}/odds", summary="Current odds for a match (alias)")
def match_odds(match_id: int, db: Session = Depends(get_db),
               market: Optional[str] = Query(None), bookmaker: Optional[str] = Query(None)):
    return current_odds(match_id, db, market, bookmaker)


@router.get("/odds/{match_id}/history", summary="Full odds history (append-only snapshots)")
def odds_history(match_id: int, db: Session = Depends(get_db),
                 market: Optional[str] = Query(None), bookmaker: Optional[str] = Query(None),
                 selection: Optional[str] = Query(None)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    out = []
    for s in _snapshots(match_id, db, market, bookmaker).all():
        snap = _snapshot_out(s, db)
        if selection:
            snap.selections = [x for x in snap.selections if x.selection == selection]
            if not snap.selections:
                continue
        out.append(snap)
    return {"data": out}


@router.get("/matches/{match_id}/odds/history", summary="Full odds history (alias)")
def match_odds_history(match_id: int, db: Session = Depends(get_db),
                       market: Optional[str] = Query(None), bookmaker: Optional[str] = Query(None),
                       selection: Optional[str] = Query(None)):
    return odds_history(match_id, db, market, bookmaker, selection)


@router.get("/odds/{match_id}/movement", summary="Opening vs current per bookmaker/market/selection")
def odds_movement(match_id: int, db: Session = Depends(get_db),
                  market: Optional[str] = Query(None), bookmaker: Optional[str] = Query(None)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    snaps = _snapshots(match_id, db, market, bookmaker).all()
    series: dict[tuple, list[tuple]] = {}
    names: dict[tuple, tuple] = {}
    for s in snaps:
        bm = db.get(Bookmaker, s.bookmaker_id) if s.bookmaker_id else None
        for sel in db.query(OddsSelection).filter_by(snapshot_id=s.id).all():
            key = (s.bookmaker_id, s.market_type, sel.selection)
            series.setdefault(key, []).append((s.timestamp, sel.odds))
            names[key] = (bm.name if bm else "", s.market_type, sel.selection)
    out: list[OddsMovementOut] = []
    for key, points in series.items():
        points.sort(key=lambda p: p[0])
        opening, current = points[0][1], points[-1][1]
        mins = None
        if len(points) > 1 and points[0][0] and points[-1][0]:
            mins = (points[-1][0] - points[0][0]).total_seconds() / 60
        m = movement(opening, current, mins)
        bm_name, mk, sel = names[key]
        out.append(OddsMovementOut(bookmaker=bm_name, market_type=mk, selection=sel, **m))
    return {"data": out}

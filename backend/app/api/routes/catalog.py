from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import League, Team
from app.schemas.schemas import LeagueOut, PaginatedMeta, TeamOut

router = APIRouter(tags=["catalog"])


@router.get("/leagues", summary="Supported leagues")
def list_leagues(db: Session = Depends(get_db)):
    rows = db.query(League).order_by(League.code).all()
    return {"data": [LeagueOut(id=r.id, code=r.code, name=r.name, country=r.country,
                               season=r.season) for r in rows]}


@router.get("/teams", summary="List teams (paginated, filter by league)")
def list_teams(db: Session = Depends(get_db), league: Optional[str] = Query(None),
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    q = db.query(Team)
    if league:
        lg = db.query(League).filter(League.code == league).first()
        if not lg:
            raise HTTPException(400, f"unknown league code: {league}")
        q = q.filter(Team.league_id == lg.id)
    total = q.count()
    rows = q.order_by(Team.name).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "data": [TeamOut(id=r.id, name=r.name, short_name=r.short_name, country=r.country)
                 for r in rows],
        "meta": PaginatedMeta(page=page, page_size=page_size, total=total),
    }

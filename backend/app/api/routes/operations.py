"""Operational visibility routes (Phase 35, strictly read-only).

No endpoint here executes jobs, mutates records, or changes authority.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.services.observation import observation_summary

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/soak")
def soak_summary(
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Observation lifecycle funnel + exclusion reasons + last activity."""
    return observation_summary(db, competition=competition, season=season)

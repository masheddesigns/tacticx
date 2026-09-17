"""Prediction lifecycle endpoints (Phase 7).

Version history, latest version, diffs, on-demand predict/refresh,
source health, evaluation runner and monitoring. Analytical only:
no betting, no automatic model switching, no retraining triggers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.db.models.lifecycle import PredictionDiff
from app.services.features.temporal import TemporalMode
from app.services.lifecycle import versions
from app.services.lifecycle.upcoming_predictions import UpcomingPredictionService

router = APIRouter(tags=["lifecycle"])


class PredictRequest(BaseModel):
    cutoff: Optional[str] = None
    model: Optional[str] = None
    seed: Optional[int] = None
    temporal_mode: str = "strict_prematch"


class RefreshRequest(BaseModel):
    model: Optional[str] = None
    seed: Optional[int] = None
    temporal_mode: str = "strict_prematch"


def _mode(value: str) -> TemporalMode:
    try:
        return TemporalMode(value)
    except ValueError:
        raise HTTPException(400, "temporal_mode must be strict_prematch or historical_estimated")


@router.get("/matches/{match_id}/predictions", summary="Prediction version history")
def prediction_history(match_id: int, db: Session = Depends(get_db)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    return {"data": [versions.version_detail(db, v)
                     for v in versions.history(db, match_id)]}


@router.get("/matches/{match_id}/prediction/latest", summary="Latest prediction version")
def prediction_latest(match_id: int, db: Session = Depends(get_db)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    row = versions.latest_version(db, match_id)
    if row is None:
        raise HTTPException(404, "no prediction versions for this match")
    return versions.version_detail(db, row)


@router.get("/matches/{match_id}/prediction/diff", summary="Diff between versions")
def prediction_diff(match_id: int, db: Session = Depends(get_db),
                    from_version: Optional[int] = None,
                    to_version: Optional[int] = None):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    hist = versions.history(db, match_id)
    if not hist:
        raise HTTPException(404, "no prediction versions for this match")
    by_number = {v.version_number: v for v in hist}
    new = by_number.get(to_version, hist[-1]) if to_version is not None else hist[-1]
    if to_version is not None and to_version not in by_number:
        raise HTTPException(404, "to_version not found")
    if from_version is not None:
        if from_version not in by_number:
            raise HTTPException(404, "from_version not found")
        old = by_number[from_version]
    else:
        earlier = [v for v in hist if v.version_number < new.version_number]
        if not earlier:
            raise HTTPException(404, "no earlier version to diff against")
        old = earlier[-1]
    try:
        return versions.compute_diff(db, old.id, new.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/matches/{match_id}/predict", summary="Generate a versioned prediction")
def predict_match(match_id: int, request: PredictRequest,
                  db: Session = Depends(get_db)):
    mode = _mode(request.temporal_mode)
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    try:
        cutoff = datetime.fromisoformat(request.cutoff) if request.cutoff else None
    except ValueError:
        raise HTTPException(400, "cutoff must be ISO format")
    service = UpcomingPredictionService(model=request.model, mode=mode,
                                        seed=request.seed)
    if cutoff is not None:
        # Explicit-cutoff single generation (no "now" semantics).
        try:
            created = versions.generate_version(db, match_id, cutoff, mode,
                                                model=request.model,
                                                seed=request.seed)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"status": "success", "cached": created.get("cached", False),
                "version": created["version"]}
    result = service.predict_one(db, match_id)
    if result["status"] == "failed":
        raise HTTPException(400, result["error"])
    return result


@router.post("/matches/{match_id}/refresh", summary="Refresh into a new version")
def refresh_match(match_id: int, request: RefreshRequest,
                  db: Session = Depends(get_db)):
    mode = _mode(request.temporal_mode)
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    service = UpcomingPredictionService(model=request.model, mode=mode,
                                        seed=request.seed)
    result = service.refresh_one(db, match_id)
    if result["status"] == "failed":
        raise HTTPException(400, result["error"])
    return result


@router.get("/sources/health", summary="Source health (no secrets)")
def sources_health(db: Session = Depends(get_db), source: Optional[str] = None):
    from app.services.lifecycle.health import get_health

    return {"data": get_health(db, source)}


@router.get("/sources/status", summary="Provider configuration status (no secrets)")
def sources_status():
    from app.config import get_settings

    settings = get_settings()
    return {"data": {
        "football_provider": settings.FOOTBALL_PROVIDER,
        "football_configured": settings.is_football_configured,
        "odds_provider": settings.ODDS_PROVIDER,
        "odds_configured": settings.is_odds_configured,
        "lookahead_hours": settings.NEXT_MATCH_LOOKAHEAD_HOURS,
        "odds_refresh_interval_minutes": settings.ODDS_REFRESH_INTERVAL_MINUTES,
    }}


@router.post("/lifecycle/evaluate", summary="Evaluate completed predictions")
def run_evaluation(db: Session = Depends(get_db), limit: int = 500):
    from app.services.lifecycle.evaluate import evaluate_completed_predictions

    stats = evaluate_completed_predictions(db, limit=max(1, min(limit, 5000)))
    return {"received": stats.received, "inserted": stats.inserted,
            "skipped": stats.skipped, "errors": stats.errors[:10]}


@router.get("/lifecycle/monitoring", summary="Rolling metrics + drift status")
def monitoring(db: Session = Depends(get_db), league: Optional[str] = None,
               model_version: Optional[str] = None,
               reference_brier: float = 0.60):
    from app.services.lifecycle import monitoring as monitoring_service

    league_id = None
    if league:
        from app.db.models.core import League

        row = db.query(League).filter_by(code=league).first()
        if row is None:
            raise HTTPException(404, f"unknown league: {league}")
        league_id = row.id
    return {
        "rolling": monitoring_service.rolling_metrics(
            db, league_id=league_id, model_version=model_version),
        "drift": monitoring_service.drift_status(db, reference_brier),
        "data_drift": monitoring_service.data_drift(db, league_id=league_id),
    }


@router.post("/lifecycle/lock", summary="Lock versions past kickoff")
def lock_versions(db: Session = Depends(get_db)):
    locked = versions.lock_due_predictions(db)
    return {"locked": locked}

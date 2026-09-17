"""Prediction + backtesting endpoints (Phase 2).

Probabilities are statistical estimates with honest uncertainty — never
certainties. No betting, staking, guarantees, or "sure win" language exists
anywhere in these responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.db.models.predictions import BacktestRun, Prediction
from app.schemas.schemas import BacktestRunOut, FullPredictionOut, PredictionOut
from app.services.backtesting.runner import run_backtest
from app.services.backtesting.service import resolve_predictions, store_full_prediction
from app.services.features.temporal import TemporalMode

router = APIRouter(tags=["predictions"])


class GenerateRequest(BaseModel):
    model: str = "ensemble"
    temporal_mode: str = "strict_prematch"
    seed: Optional[int] = None
    simulations: int = 10000


class BacktestRequest(BaseModel):
    model: str = "ensemble"
    league: Optional[str] = None
    season: Optional[str] = None
    temporal_mode: str = "strict_prematch"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    seed: Optional[int] = None
    simulations: int = 1000


def _prediction_to_out(row: Prediction) -> PredictionOut:
    return PredictionOut(
        id=row.id, match_id=row.match_id,
        prediction_timestamp=row.prediction_timestamp,
        model_version=row.model_version, prediction_type=row.prediction_type,
        predicted_probability=row.predicted_probability,
        probabilities=row.probabilities, confidence=row.confidence,
        model_name=row.model_name or None, status=row.status or None,
        temporal_mode=row.temporal_mode or None,
        prediction_cutoff=row.prediction_cutoff,
        feature_availability=row.feature_availability,
        model_configuration=row.model_config, random_seed=row.random_seed)


def _build_model(name: str, seed=None, simulations: int = 10000):
    from app.services.predictions.elo import EloModel
    from app.services.predictions.ensemble import BaselineModel, EnsembleModel
    from app.services.predictions.montecarlo import MonteCarloModel
    from app.services.predictions.poisson import PoissonModel, xg_enhanced_config

    if name == "elo":
        return EloModel()
    if name == "poisson":
        return PoissonModel()
    if name == "poisson-xg":
        return PoissonModel(config=xg_enhanced_config())
    if name == "montecarlo":
        return MonteCarloModel(n_simulations=simulations, random_seed=seed)
    if name == "ensemble":
        return EnsembleModel()
    if name == "baseline":
        return BaselineModel()
    raise ValueError(f"unknown model: {name}")


@router.get("/predictions/{match_id}", summary="Stored predictions for a match")
def list_predictions(match_id: int, db: Session = Depends(get_db)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    rows = db.query(Prediction).filter_by(match_id=match_id).order_by(
        Prediction.prediction_timestamp.desc()).all()
    return {"data": [_prediction_to_out(r) for r in rows]}


@router.get("/predictions/{match_id}/history", summary="Full stored history for a match")
def prediction_history(match_id: int, db: Session = Depends(get_db),
                       model: Optional[str] = None):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    query = db.query(Prediction).filter_by(match_id=match_id)
    if model:
        query = query.filter_by(model_name=model)
    rows = query.order_by(Prediction.prediction_timestamp.desc()).all()
    return {"data": [_prediction_to_out(r) for r in rows]}


@router.get("/predictions", summary="List stored predictions")
def list_all_predictions(db: Session = Depends(get_db), model: Optional[str] = None,
                         league: Optional[str] = None, limit: int = 50):
    from app.db.models.core import League

    query = db.query(Prediction).order_by(Prediction.prediction_timestamp.desc())
    if model:
        query = query.filter_by(model_name=model)
    if league:
        league_row = db.query(League).filter_by(code=league).first()
        if league_row is None:
            raise HTTPException(404, f"unknown league: {league}")
        match_ids = [m.id for m in db.query(Match.id).filter_by(league_id=league_row.id).all()]
        if match_ids:
            query = query.filter(Prediction.match_id.in_(match_ids))
        else:
            query = query.filter(Prediction.id < 0)
    rows = query.limit(max(1, min(limit, 500))).all()
    return {"data": [_prediction_to_out(r) for r in rows]}


@router.post("/predictions/{match_id}/generate", summary="Generate and store a prediction",
             response_model=FullPredictionOut)
def generate_prediction(match_id: int, request: GenerateRequest,
                        db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    try:
        mode = TemporalMode(request.temporal_mode)
    except ValueError:
        raise HTTPException(400, "temporal_mode must be strict_prematch or historical_estimated")
    try:
        model = _build_model(request.model, seed=request.seed,
                             simulations=request.simulations)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    cutoff = match.kickoff_at or datetime.now()
    try:
        import inspect

        params = inspect.signature(model.predict).parameters
        if "seed" in params:
            pred = model.predict(db, match_id, cutoff, mode, seed=request.seed)
        else:
            pred = model.predict(db, match_id, cutoff, mode)
    except Exception as exc:
        raise HTTPException(500, f"prediction failed: {exc}")
    config = getattr(getattr(model, "config", None), "as_dict", lambda: None)()
    if callable(getattr(model, "config_dict", None)):
        config = model.config_dict()
    stored = store_full_prediction(db, match_id, pred, model_config=config)
    resolve_predictions(db, match_id)
    out = pred.model_dump()
    out["prediction_id"] = stored.id
    return out


@router.get("/backtesting", summary="Recorded backtest runs")
def list_backtests(db: Session = Depends(get_db), model: Optional[str] = None):
    query = db.query(BacktestRun).order_by(BacktestRun.created_at.desc())
    if model:
        query = query.filter_by(model_name=model)
    rows = query.limit(100).all()
    return {"data": [
        BacktestRunOut(id=r.id, model_name=r.model_name, model_version=r.model_version,
                       league=r.league, season=r.season, temporal_mode=r.temporal_mode,
                       sample_size=r.sample_size,
                       excluded_insufficient=r.excluded_insufficient,
                       excluded_temporal=r.excluded_temporal,
                       metrics=r.metrics, created_at=r.created_at)
        for r in rows
    ]}


@router.post("/backtesting/run", summary="Run a chronological backtest")
def run_backtest_endpoint(request: BacktestRequest, db: Session = Depends(get_db)):
    try:
        mode = TemporalMode(request.temporal_mode)
    except ValueError:
        raise HTTPException(400, "temporal_mode must be strict_prematch or historical_estimated")
    try:
        if request.model == "montecarlo":
            model = _build_model(request.model, seed=request.seed,
                                 simulations=request.simulations)
        else:
            model = _build_model(request.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    try:
        date_from = datetime.fromisoformat(request.date_from) if request.date_from else None
        date_to = datetime.fromisoformat(request.date_to) if request.date_to else None
    except ValueError:
        raise HTTPException(400, "dates must be ISO format")
    try:
        result = run_backtest(db, model, request.league or None, request.season or None,
                              date_from, date_to, mode, persist=True, seed=request.seed)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"backtest failed: {exc}")
    return result

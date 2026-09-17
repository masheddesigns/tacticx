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
    from app.services.predictions.advanced import AdvancedGoalModel, AdvancedModel
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
    if name == "advanced":
        return AdvancedModel()
    if name == "advanced-xg":
        from app.services.predictions.advanced import AdvancedConfig

        return AdvancedModel(config=AdvancedConfig(use_xg=True))
    if name == "advanced_goal":
        return AdvancedGoalModel()
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


@router.get("/features/{match_id}", summary="Pre-match feature snapshot")
def feature_snapshot(match_id: int, db: Session = Depends(get_db),
                     cutoff: Optional[str] = None,
                     temporal_mode: str = "strict_prematch"):
    """Reproducible features with availability, source, as-of and quality."""
    from app.services.features.engineered import build_feature_snapshot

    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    try:
        mode = TemporalMode(temporal_mode)
    except ValueError:
        raise HTTPException(400, "temporal_mode must be strict_prematch or historical_estimated")
    try:
        resolved = datetime.fromisoformat(cutoff) if cutoff else match.kickoff_at
    except ValueError:
        raise HTTPException(400, "cutoff must be ISO format")
    if resolved is None:
        raise HTTPException(400, "match has no kickoff; pass cutoff explicitly")
    try:
        return build_feature_snapshot(db, match_id, resolved, mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/predictions/{match_id}/explain", summary="Explain a stored prediction")
def explain_prediction(match_id: int, db: Session = Depends(get_db),
                       model: Optional[str] = None):
    """Latest stored prediction plus its feature snapshot, availability and
    model versions. Works from stored records only (no recomputation)."""
    from app.services.features.engineered import build_feature_snapshot

    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    query = db.query(Prediction).filter_by(match_id=match_id)
    if model:
        query = query.filter_by(model_name=model)
    row = query.order_by(Prediction.prediction_timestamp.desc()).first()
    if row is None:
        raise HTTPException(404, "no stored prediction for this match")
    snapshot = None
    cutoff = row.prediction_cutoff
    try:
        if cutoff is not None:
            snapshot = build_feature_snapshot(
                db, match_id, cutoff, TemporalMode(row.temporal_mode or "strict_prematch"))
    except ValueError as exc:
        snapshot = {"error": str(exc)}
    return {
        "prediction": _prediction_to_out(row),
        "feature_version": (snapshot or {}).get("feature_version", "features_v1"),
        "cutoff": str(cutoff),
        "features": snapshot,
        "model_versions": {
            "model": row.model_name,
            "model_version": row.model_version,
        },
    }


@router.get("/models", summary="Registered prediction models")
def list_models():
    """Model catalog: names, versions, descriptions. No secrets."""
    from app.services.predictions.advanced import (
        AdvancedGoalModel,
        AdvancedModel,
    )
    from app.services.predictions.ensemble import MODEL_REGISTRY, BaselineModel, EnsembleModel
    from app.services.predictions.elo import EloModel
    from app.services.predictions.montecarlo import MonteCarloModel
    from app.services.predictions.poisson import PoissonModel

    catalog = []
    for cls in (BaselineModel, EloModel, PoissonModel, MonteCarloModel,
                EnsembleModel, AdvancedModel, AdvancedGoalModel):
        instance = cls()
        catalog.append({
            "name": instance.model_name,
            "version": instance.model_version,
            "description": (instance.__doc__ or "").strip().split("\n")[0],
        })
    catalog.append({
        "name": "ensemble_v2",
        "version": "ensemble_v2",
        "description": "Walk-forward learned-weight ensemble (built per evaluation).",
    })
    catalog.append({
        "name": "advanced-xg",
        "version": "advanced_v1-xg",
        "description": "AdvancedModel with xG features (xG-eligible rows only).",
    })
    catalog.append({
        "name": "poisson-xg",
        "version": "poisson_v1-xg",
        "description": "PoissonModel with xG blending where eligible.",
    })
    return {"data": catalog, "registry": sorted(set(list(MODEL_REGISTRY) + [
        "advanced", "advanced_goal", "advanced-xg", "ensemble_v2"]))}


@router.get("/backtesting/models", summary="Models with recorded evaluations")
def list_evaluated_models(db: Session = Depends(get_db)):
    """Distinct models present in backtest runs and evaluations."""
    from app.db.models.predictions import ModelEvaluation

    names = set()
    for (name,) in db.query(BacktestRun.model_name).distinct().all():
        if name:
            names.add(name)
    for (name,) in db.query(ModelEvaluation.model_name).distinct().all():
        if name:
            names.add(name)
    return {"data": sorted(names)}

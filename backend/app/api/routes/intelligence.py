"""Prediction intelligence endpoints (Phase 15, read-only).

Every endpoint rebuilds from cutoff-gated sources; nothing here writes
predictions, models, features, odds or history (snapshot rows only).
Scenario POST validates against a whitelist and returns derived output.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.services.features.temporal import TemporalMode
from app.services.intelligence_v2 import service as intel_service

router = APIRouter(tags=["intelligence"])


def _resolve(match_id: int, db: Session, mode: str, cutoff: Optional[str],
             model: Optional[str] = None):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    try:
        resolved_mode = TemporalMode(mode)
    except ValueError:
        raise HTTPException(400, "mode must be strict_prematch or historical_estimated")
    try:
        resolved_cutoff = datetime.fromisoformat(cutoff) if cutoff else match.kickoff_at
    except ValueError:
        raise HTTPException(400, "cutoff must be ISO format")
    if resolved_cutoff is None:
        raise HTTPException(400, "match has no kickoff; pass cutoff explicitly")
    if model is not None:
        from app.services.intelligence.composer import build_core_model

        try:
            build_core_model(model)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return resolved_cutoff, resolved_mode


def _build(match_id: int, db: Session, mode: str, cutoff: Optional[str],
           model: Optional[str], seed: Optional[int], analogues: bool,
           scenarios: bool):
    resolved_cutoff, resolved_mode = _resolve(match_id, db, mode, cutoff, model)
    try:
        return intel_service.build_intelligence(
            db, match_id, resolved_cutoff, resolved_mode, model=model,
            seed=seed, with_analogues=analogues, with_scenarios=scenarios)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"intelligence failed: {exc}")


@router.get("/intelligence/{match_id}", summary="Full intelligence response")
def full_intelligence(match_id: int, db: Session = Depends(get_db),
                      mode: str = "strict_prematch", cutoff: Optional[str] = None,
                      model: Optional[str] = None, seed: Optional[int] = None):
    return _build(match_id, db, mode, cutoff, model, seed, True, True)


@router.get("/intelligence/{match_id}/summary", summary="Intelligence summary")
def intelligence_summary(match_id: int, db: Session = Depends(get_db),
                         mode: str = "strict_prematch",
                         cutoff: Optional[str] = None,
                         model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, False, False)
    return {"prediction": full["prediction"], "goals": full["goals"],
            "uncertainty": full["uncertainty"], "warnings": full["warnings"],
            "market_comparison": full["market_comparison"],
            "explanation": {"headline": (full.get("explanation") or {}).get(
                "headline", "")},
            "provenance": full["provenance"]}


@router.get("/intelligence/{match_id}/markets", summary="Derived markets")
def intelligence_markets(match_id: int, db: Session = Depends(get_db),
                         mode: str = "strict_prematch",
                         cutoff: Optional[str] = None,
                         model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, False, False)
    return {"markets": full["markets"],
            "score_distribution": full["score_distribution"],
            "provenance": full["provenance"]}


@router.get("/intelligence/{match_id}/uncertainty", summary="Uncertainty")
def intelligence_uncertainty(match_id: int, db: Session = Depends(get_db),
                             mode: str = "strict_prematch",
                             cutoff: Optional[str] = None,
                             model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, False, False)
    return {"uncertainty": full["uncertainty"],
            "model_disagreement": full["model_disagreement"],
            "data_quality": full["data_quality"],
            "provenance": full["provenance"]}


@router.get("/intelligence/{match_id}/analogues", summary="Analogues")
def intelligence_analogues(match_id: int, db: Session = Depends(get_db),
                           mode: str = "strict_prematch",
                           cutoff: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, None, None, True, False)
    return {"analogues": full["analogues"], "provenance": full["provenance"]}


@router.get("/intelligence/{match_id}/scenarios", summary="Scenarios")
def intelligence_scenarios(match_id: int, db: Session = Depends(get_db),
                           mode: str = "strict_prematch",
                           cutoff: Optional[str] = None,
                           model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, False, True)
    return {"scenarios": full["scenarios"], "provenance": full["provenance"]}


@router.get("/intelligence/{match_id}/explanation", summary="Explanation")
def intelligence_explanation(match_id: int, db: Session = Depends(get_db),
                             mode: str = "strict_prematch",
                             cutoff: Optional[str] = None,
                             model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, False, False)
    return {"explanation": full["explanation"],
            "warnings": full["warnings"], "provenance": full["provenance"]}


@router.get("/intelligence/snapshots/{snapshot_id}", summary="Stored snapshot")
def stored_snapshot(snapshot_id: str, db: Session = Depends(get_db)):
    try:
        return intel_service.load_snapshot(db, snapshot_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class ScenarioPost(BaseModel):
    names: Optional[list] = None
    params: Optional[dict] = None
    mode: str = "strict_prematch"
    cutoff: Optional[str] = None
    model: Optional[str] = None


@router.post("/intelligence/{match_id}/scenarios", summary="Derived scenarios")
def post_scenarios(match_id: int, request: ScenarioPost,
                   db: Session = Depends(get_db)):
    """Whitelisted scenario parameters only; derived output, no mutation."""
    from app.services.intelligence import scenarios as scenario_svc

    resolved_cutoff, resolved_mode = _resolve(match_id, db, request.mode,
                                              request.cutoff, request.model)
    try:
        base = intel_service.build_intelligence(
            db, match_id, resolved_cutoff, resolved_mode, model=request.model,
            persist=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    lam_h = (base.get("goals") or {}).get("home_lambda")
    lam_a = (base.get("goals") or {}).get("away_lambda")
    if lam_h is None or lam_a is None:
        raise HTTPException(400, "no goal lambdas available for scenarios")
    baseline_1x2 = {k: base["prediction"][k] for k in ("home", "draw", "away")}
    try:
        if request.params:
            outputs = [scenario_svc.run_scenario(
                baseline_1x2, lam_h, lam_a,
                (request.names or ["baseline"])[0],
                custom_params=request.params)]
        else:
            outputs = scenario_svc.run_all(baseline_1x2, lam_h, lam_a,
                                           names=request.names)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"data": [o.model_dump() for o in outputs],
            "provenance": base["provenance"]}

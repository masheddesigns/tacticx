"""Canonical match-intelligence product endpoints (Phase 17).

Read-only orchestration over Phase 15/16 services. Machine-readable errors,
compact presentation mode, snapshot-hash caching with temporal safety
(immutable finished matches cache indefinitely; scheduled/live matches
rebuild with a short memo). OpenAPI schemas derive from Pydantic models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.services.features.temporal import TemporalMode
from app.services.match_intelligence import service as mi_service
from app.services.match_intelligence.schemas import MatchIntelligence

router = APIRouter(tags=["match-intelligence"])

ERROR_CODES = {
    "match_not_found", "intelligence_unavailable", "prediction_unavailable",
    "invalid_snapshot", "temporal_data_unavailable", "provider_unavailable",
    "malformed_provider_result",
}


def _resolve(match_id: int, db: Session, mode: str, cutoff: Optional[str],
             model: Optional[str] = None):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, {"code": "match_not_found",
                                  "message": f"unknown match: {match_id}"})
    try:
        resolved_mode = TemporalMode(mode)
    except ValueError:
        raise HTTPException(400, {"code": "invalid_snapshot",
                                  "message": "mode must be strict_prematch or "
                                             "historical_estimated"})
    try:
        resolved_cutoff = datetime.fromisoformat(cutoff) if cutoff else match.kickoff_at
    except ValueError:
        raise HTTPException(400, {"code": "invalid_snapshot",
                                  "message": "cutoff must be ISO format"})
    if resolved_cutoff is None:
        raise HTTPException(400, {"code": "temporal_data_unavailable",
                                  "message": "match has no kickoff; pass cutoff "
                                             "explicitly"})
    if model is not None:
        from app.services.intelligence.composer import build_core_model

        try:
            build_core_model(model)
        except ValueError as exc:
            raise HTTPException(400, {"code": "prediction_unavailable",
                                      "message": str(exc)})
    return resolved_cutoff, resolved_mode


def _build(match_id: int, db: Session, mode: str, cutoff: Optional[str],
           model: Optional[str], seed: Optional[int], response_mode: str,
           with_mirofish: bool, mirofish_scenario: str):
    resolved_cutoff, resolved_mode = _resolve(match_id, db, mode, cutoff, model)
    try:
        return mi_service.cached_build(
            db, match_id, resolved_cutoff, resolved_mode, model, seed,
            response_mode, with_mirofish, mirofish_scenario)
    except ValueError as exc:
        raise HTTPException(400, {"code": "intelligence_unavailable",
                                  "message": str(exc)})
    except Exception as exc:
        raise HTTPException(500, {"code": "intelligence_unavailable",
                                  "message": f"intelligence failed: {exc}"})


@router.get("/matches/{match_id}/intelligence",
            summary="Canonical match intelligence",
            response_model=MatchIntelligence)
def match_intelligence(match_id: int, db: Session = Depends(get_db),
                       mode: str = "strict_prematch",
                       cutoff: Optional[str] = None,
                       model: Optional[str] = None,
                       seed: Optional[int] = None,
                       response_mode: str = "standard",
                       mirofish_scenario: str = "baseline"):
    """One complete, self-contained intelligence document."""
    return _build(match_id, db, mode, cutoff, model, seed, response_mode,
                  True, mirofish_scenario)


@router.get("/matches/{match_id}/intelligence/summary",
            summary="Lightweight intelligence summary")
def intelligence_summary(match_id: int, db: Session = Depends(get_db),
                         mode: str = "strict_prematch",
                         cutoff: Optional[str] = None,
                         model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, "compact",
                  False, "baseline")
    return {
        "schema_version": full["schema_version"],
        "match": full["match"],
        "core_prediction": {
            "home": full["core_prediction"]["home"],
            "draw": full["core_prediction"]["draw"],
            "away": full["core_prediction"]["away"],
            "model_version": full["core_prediction"]["model_version"],
        },
        "expected_goals": full["expected_goals"],
        "derived_markets": full["derived_markets"],
        "uncertainty": full["uncertainty"],
        "data_quality": full["data_quality"],
        "market": {
            "consensus": full["market"]["consensus"],
            "divergence": full["market"]["divergence"],
        },
        "major_warnings": [w for w in full["warnings"]
                           if w.get("severity") in ("warning", "error")],
        "provenance": full["provenance"],
    }


@router.get("/matches/{match_id}/intelligence/markets",
            summary="Intelligence markets section")
def intelligence_markets(match_id: int, db: Session = Depends(get_db),
                         mode: str = "strict_prematch",
                         cutoff: Optional[str] = None,
                         model: Optional[str] = None,
                         response_mode: str = "standard"):
    full = _build(match_id, db, mode, cutoff, model, None, response_mode,
                  False, "baseline")
    return {"derived_markets": full["derived_markets"],
            "correct_score": full["correct_score"],
            "expected_goals": full["expected_goals"],
            "provenance": full["provenance"]}


@router.get("/matches/{match_id}/intelligence/uncertainty",
            summary="Intelligence uncertainty section")
def intelligence_uncertainty(match_id: int, db: Session = Depends(get_db),
                             mode: str = "strict_prematch",
                             cutoff: Optional[str] = None,
                             model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, "compact",
                  False, "baseline")
    return {"uncertainty": full["uncertainty"],
            "model_disagreement": full["model_disagreement"],
            "data_quality": full["data_quality"],
            "temporal_quality": full["temporal_quality"],
            "provenance": full["provenance"]}


@router.get("/matches/{match_id}/intelligence/scenarios",
            summary="Intelligence scenarios section")
def intelligence_scenarios(match_id: int, db: Session = Depends(get_db),
                           mode: str = "strict_prematch",
                           cutoff: Optional[str] = None,
                           model: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, model, None, "standard",
                  False, "baseline")
    return {"scenarios": full["scenarios"],
            "core_prediction": {
                "home": full["core_prediction"]["home"],
                "draw": full["core_prediction"]["draw"],
                "away": full["core_prediction"]["away"]},
            "provenance": full["provenance"]}


@router.get("/matches/{match_id}/intelligence/analogues",
            summary="Intelligence analogues section")
def intelligence_analogues(match_id: int, db: Session = Depends(get_db),
                           mode: str = "strict_prematch",
                           cutoff: Optional[str] = None):
    full = _build(match_id, db, mode, cutoff, None, None, "standard",
                  False, "baseline")
    return {"analogues": full["analogues"], "provenance": full["provenance"]}


@router.get("/matches/{match_id}/intelligence/mirofish",
            summary="Intelligence MiroFish section")
def intelligence_mirofish(match_id: int, db: Session = Depends(get_db),
                          mode: str = "strict_prematch",
                          cutoff: Optional[str] = None,
                          model: Optional[str] = None,
                          mirofish_scenario: str = "baseline"):
    full = _build(match_id, db, mode, cutoff, model, None, "compact",
                  True, mirofish_scenario)
    return {"mirofish": full["mirofish"], "provenance": full["provenance"]}

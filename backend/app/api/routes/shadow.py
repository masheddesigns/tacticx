"""Champion/challenger shadow API routes (Phase 32, read-only + guarded).

Reads are open. Execution endpoints require the operational guard.
Nothing here can activate, promote, or modify production.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.services.shadow_execution import (
    ShadowExecutionError,
    ShadowIneligible,
    evaluate_shadow_pair,
    execute_shadow,
    find_eligible_matches,
    shadow_comparison,
    shadow_evaluation_to_dict,
    shadow_summary,
    shadow_to_dict,
    validate_shadow_pair,
)
from app.services.shadow_execution.evaluation import ShadowEvaluationError

router = APIRouter(prefix="/shadow", tags=["shadow"])


def _guard() -> None:
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Shadow execution endpoints are disabled in this environment")


class ExecuteBody(BaseModel):
    match_id: int = 0
    challenger_artifact_id: str = ""
    champion_artifact_id: Optional[str] = None


class StartBody(BaseModel):
    competition: Optional[str] = None
    challenger_artifact_id: str = ""
    limit: int = 50


@router.get("/summary")
def shadow_summary_endpoint(
    challenger_artifact_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return shadow_summary(db, challenger_artifact_id=challenger_artifact_id)


@router.get("/challengers")
def shadow_challengers(db: Session = Depends(get_db)):
    from app.db.models.governance import ShadowPredictionSnapshot

    rows = (db.query(ShadowPredictionSnapshot.challenger_artifact_id)
            .distinct().all())
    return {"challengers": sorted(r[0] for r in rows if r[0])}


@router.get("/matches")
def shadow_matches(
    competition: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return find_eligible_matches(db, competition=competition, limit=limit)


@router.get("/matches/{match_id}")
def shadow_match(match_id: int, db: Session = Depends(get_db)):
    from app.db.models.governance import ShadowPredictionSnapshot

    rows = (db.query(ShadowPredictionSnapshot)
            .filter_by(match_id=match_id)
            .order_by(ShadowPredictionSnapshot.id.desc()).all())
    return {"match_id": match_id, "shadow_count": len(rows),
            "shadows": [shadow_to_dict(r) for r in rows]}


@router.get("/evaluations")
def shadow_evaluations(
    challenger_artifact_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    from app.db.models.governance import ShadowEvaluationRecord

    query = db.query(ShadowEvaluationRecord)
    if challenger_artifact_id:
        query = query.filter_by(challenger_artifact_id=challenger_artifact_id)
    rows = query.order_by(ShadowEvaluationRecord.id.desc()).limit(limit).all()
    return {"evaluation_count": len(rows),
            "evaluations": [shadow_evaluation_to_dict(r) for r in rows]}


@router.get("/comparison/{challenger_id}")
def shadow_comparison_endpoint(challenger_id: str,
                               db: Session = Depends(get_db)):
    return shadow_comparison(db, challenger_id)


@router.post("/execute/{match_id}")
def shadow_execute_endpoint(match_id: int, body: ExecuteBody,
                            db: Session = Depends(get_db)):
    _guard()
    challenger_id = body.challenger_artifact_id
    if not challenger_id:
        raise HTTPException(status_code=422,
                            detail="challenger_artifact_id is required")
    try:
        return execute_shadow(
            db, match_id, challenger_id,
            champion_artifact_id=body.champion_artifact_id)
    except (ShadowExecutionError, ShadowIneligible) as exc:
        raise HTTPException(status_code=422, detail=exc.reason)


@router.post("/start")
def shadow_start_endpoint(body: StartBody, db: Session = Depends(get_db)):
    _guard()
    if not body.challenger_artifact_id:
        raise HTTPException(status_code=422,
                            detail="challenger_artifact_id is required")
    scan = find_eligible_matches(db, competition=body.competition,
                                 limit=body.limit)
    executed = []
    if scan["state"] == "ELIGIBLE":
        for match_id in scan["eligible"]:
            try:
                result = execute_shadow(
                    db, match_id, body.challenger_artifact_id)
                executed.append({"match_id": match_id,
                                 "shadow_id": result["shadow_id"],
                                 "reused": bool(result.get("cache_hit"))})
            except (ShadowExecutionError, ShadowIneligible) as exc:
                executed.append({"match_id": match_id, "error": exc.code})
    return {"state": scan["state"], "executed": executed,
            "skipped": scan.get("skipped", [])}


@router.get("/pairs/{shadow_id}/validate")
def shadow_pair_validate(shadow_id: str, db: Session = Depends(get_db)):
    return validate_shadow_pair(db, shadow_id)


@router.post("/pairs/{shadow_id}/evaluate")
def shadow_pair_evaluate(shadow_id: str, db: Session = Depends(get_db)):
    _guard()
    try:
        return evaluate_shadow_pair(db, shadow_id)
    except ShadowEvaluationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)

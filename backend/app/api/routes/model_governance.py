"""Model governance API routes (Phase 30).

Read endpoints are open. Every mutation endpoint requires the existing
operational guard. Nothing here can auto-promote: activation and rollback
are explicit, actor-attributed operations with optimistic concurrency.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.services.model_governance import (
    activate_production,
    active_champion_view,
    artifact_to_dict,
    audit_trail,
    check_canary_eligibility,
    decide,
    evaluate_shadow,
    full_flow_status,
    get_artifact,
    list_bindings,
    list_requests,
    mark_canary_eligible,
    promote_to_challenger,
    register_candidate_artifact,
    request_promotion,
    rollback,
    run_shadow_pair,
    start_shadow,
    validate_candidate,
    validation_to_dict,
)
from app.services.model_governance.lifecycle import GovernanceError
from app.services.model_governance.promotion import PromotionError
from app.services.model_governance.approval import ApprovalError
from app.services.model_governance.deployment import DeploymentError
from app.services.model_governance.shadow import ShadowError
from app.services.model_governance.validation import ValidationError

router = APIRouter(prefix="/model-governance", tags=["model-governance"])


def _guard() -> None:
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Governance mutation endpoints are disabled in this environment")


def _gov_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "GOVERNANCE_ERROR")
    status = 404 if code in ("UNKNOWN_ARTIFACT", "UNKNOWN_REQUEST",
                             "UNKNOWN_VALIDATION", "UNKNOWN_EXPERIMENT",
                             "UNKNOWN_DATASET", "UNKNOWN_CANDIDATE",
                             "UNKNOWN_OUTCOME", "NO_CHAMPION") else 422
    return HTTPException(status_code=status, detail=exc.reason)


class RegisterArtifactRequest(BaseModel):
    candidate_id: str
    experiment_id: Optional[str] = None
    dataset_id: Optional[str] = None


class ValidateRequest(BaseModel):
    artifact_id: str
    experiment_id: Optional[str] = None
    actor: str = ""


class PromotionRequestBody(BaseModel):
    artifact_id: str
    validation_id: str
    competition: Optional[str] = None
    season: Optional[str] = None
    prediction_mode: str = "PRE_MATCH"
    deployment_mode: str = "SHADOW"
    requester: str = ""
    reason: str = ""


class DecisionBody(BaseModel):
    request_id: str = ""
    decision: str = ""
    actor: str = ""
    reason: str = ""


class ShadowStartBody(BaseModel):
    challenger_artifact_id: str
    champion_artifact_id: str
    actor: str = ""


class ShadowPairBody(BaseModel):
    challenger_artifact_id: str
    champion_artifact_id: str
    match_id: int
    cutoff: str


class CanaryBody(BaseModel):
    artifact_id: str
    actor: str = ""


class ActivateBody(BaseModel):
    artifact_id: str
    actor: str = ""
    expected_champion_artifact_id: str = ""
    reason: str = ""
    competition: Optional[str] = None
    season: Optional[str] = None
    prediction_mode: str = "PRE_MATCH"


class RollbackBody(BaseModel):
    target_artifact_id: str
    actor: str = ""
    reason: str = ""


class ChallengerBody(BaseModel):
    artifact_id: str
    actor: str = ""
    competition: Optional[str] = None
    season: Optional[str] = None
    prediction_mode: str = "PRE_MATCH"


@router.get("/registry")
def registry(role: Optional[str] = Query(None),
             db: Session = Depends(get_db)):
    return {"bindings": list_bindings(db, role=role)}


@router.get("/champion")
def champion(competition: Optional[str] = Query(None),
             season: Optional[str] = Query(None),
             db: Session = Depends(get_db)):
    try:
        return active_champion_view(db, competition=competition, season=season)
    except GovernanceError as exc:
        raise _gov_error(exc)


@router.get("/artifacts/{artifact_id}")
def artifact_detail(artifact_id: str, db: Session = Depends(get_db)):
    try:
        return artifact_to_dict(get_artifact(db, artifact_id))
    except GovernanceError as exc:
        raise _gov_error(exc)


@router.post("/artifacts", status_code=201)
def register_artifact_endpoint(body: RegisterArtifactRequest,
                               db: Session = Depends(get_db)):
    _guard()
    try:
        from app.db.models.research_registry import (
            ResearchDataset,
            ResearchExperiment,
        )
        from app.services.research import get_candidate

        candidate = get_candidate(db, body.candidate_id)
        ds_hash = None
        train_period = None
        eval_period = None
        if body.dataset_id:
            ds_row = db.query(ResearchDataset).filter_by(
                dataset_id=body.dataset_id).first()
            if ds_row is None:
                raise HTTPException(status_code=404,
                                    detail="unknown dataset")
            ds_hash = ds_row.dataset_hash
            train_period = ds_row.train_period
            eval_period = ds_row.test_period
        exp_id = body.experiment_id
        if exp_id is None:
            exp_row = (db.query(ResearchExperiment)
                       .filter_by(candidate_id=candidate.candidate_id)
                       .order_by(ResearchExperiment.id.desc()).first())
            if exp_row is not None:
                exp_id = exp_row.experiment_id
        return register_candidate_artifact(
            db, candidate_id=body.candidate_id, experiment_id=exp_id,
            dataset_id=body.dataset_id, dataset_hash=ds_hash,
            train_period=train_period, evaluation_period=eval_period,
            code_hash=candidate.code_hash)
    except HTTPException:
        raise
    except Exception as exc:
        raise _gov_error(exc)


@router.post("/validate", status_code=201)
def validate_endpoint(body: ValidateRequest, db: Session = Depends(get_db)):
    _guard()
    try:
        return validate_candidate(
            db, body.artifact_id, experiment_id=body.experiment_id,
            actor=body.actor)
    except (GovernanceError, ValidationError) as exc:
        raise _gov_error(exc)


@router.get("/validation/{validation_id}")
def validation_detail(validation_id: str, db: Session = Depends(get_db)):
    from app.db.models.governance import ModelValidationReport

    row = db.query(ModelValidationReport).filter_by(
        validation_id=validation_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown validation")
    return validation_to_dict(row)


@router.post("/challengers", status_code=201)
def challenger_endpoint(body: ChallengerBody, db: Session = Depends(get_db)):
    _guard()
    try:
        return promote_to_challenger(
            db, body.artifact_id, actor=body.actor,
            competition=body.competition, season=body.season,
            prediction_mode=body.prediction_mode)
    except GovernanceError as exc:
        raise _gov_error(exc)


@router.get("/promotion-requests")
def promotion_requests(state: Optional[str] = Query(None),
                       db: Session = Depends(get_db)):
    return {"requests": list_requests(db, state=state)}


@router.post("/promotion-requests", status_code=201)
def promotion_request_endpoint(body: PromotionRequestBody,
                               db: Session = Depends(get_db)):
    _guard()
    try:
        return request_promotion(
            db, body.artifact_id, validation_id=body.validation_id,
            competition=body.competition, season=body.season,
            prediction_mode=body.prediction_mode,
            deployment_mode=body.deployment_mode,
            requester=body.requester, reason=body.reason)
    except (GovernanceError, PromotionError) as exc:
        raise _gov_error(exc)


@router.post("/approvals", status_code=201)
def approval_endpoint(body: DecisionBody, db: Session = Depends(get_db)):
    _guard()
    if not body.request_id:
        raise HTTPException(status_code=422, detail="request_id is required")
    try:
        return decide(db, body.request_id, decision=body.decision,
                      actor=body.actor, reason=body.reason)
    except (GovernanceError, ApprovalError) as exc:
        raise _gov_error(exc)


@router.post("/shadow/start")
def shadow_start_endpoint(body: ShadowStartBody, db: Session = Depends(get_db)):
    _guard()
    try:
        return start_shadow(
            db, body.challenger_artifact_id, body.champion_artifact_id,
            actor=body.actor)
    except (GovernanceError, ShadowError) as exc:
        raise _gov_error(exc)


@router.post("/shadow/pair", status_code=201)
def shadow_pair_endpoint(body: ShadowPairBody, db: Session = Depends(get_db)):
    _guard()
    try:
        return run_shadow_pair(
            db, challenger_artifact_id=body.challenger_artifact_id,
            champion_artifact_id=body.champion_artifact_id,
            match_id=body.match_id,
            cutoff=datetime.fromisoformat(body.cutoff))
    except (GovernanceError, ShadowError, ValueError) as exc:
        reason = getattr(exc, "reason", str(exc))
        raise HTTPException(status_code=422, detail=reason)


@router.get("/shadow/{artifact_id}")
def shadow_status(artifact_id: str, db: Session = Depends(get_db)):
    try:
        return evaluate_shadow(db, artifact_id)
    except GovernanceError as exc:
        raise _gov_error(exc)


@router.post("/canary/activate")
def canary_endpoint(body: CanaryBody, db: Session = Depends(get_db)):
    _guard()
    try:
        return mark_canary_eligible(db, body.artifact_id, actor=body.actor)
    except (GovernanceError, DeploymentError) as exc:
        raise _gov_error(exc)


@router.get("/canary/{artifact_id}")
def canary_status(artifact_id: str, db: Session = Depends(get_db)):
    try:
        return check_canary_eligibility(db, artifact_id)
    except GovernanceError as exc:
        raise _gov_error(exc)


@router.post("/production/activate")
def production_activate_endpoint(body: ActivateBody,
                                 db: Session = Depends(get_db)):
    _guard()
    try:
        return activate_production(
            db, body.artifact_id, actor=body.actor,
            expected_champion_artifact_id=body.expected_champion_artifact_id,
            reason=body.reason, competition=body.competition,
            season=body.season, prediction_mode=body.prediction_mode)
    except (GovernanceError, DeploymentError) as exc:
        raise _gov_error(exc)


@router.post("/rollback")
def rollback_endpoint(body: RollbackBody, db: Session = Depends(get_db)):
    _guard()
    try:
        return rollback(db, actor=body.actor,
                        target_artifact_id=body.target_artifact_id,
                        reason=body.reason)
    except (GovernanceError, DeploymentError) as exc:
        raise _gov_error(exc)


@router.get("/audit")
def audit_endpoint(artifact_id: Optional[str] = Query(None),
                   limit: int = Query(200, ge=1, le=1000),
                   db: Session = Depends(get_db)):
    return {"events": audit_trail(db, artifact_id=artifact_id, limit=limit)}


@router.get("/status/{artifact_id}")
def flow_status(artifact_id: str, db: Session = Depends(get_db)):
    try:
        return full_flow_status(db, artifact_id)
    except GovernanceError as exc:
        raise _gov_error(exc)

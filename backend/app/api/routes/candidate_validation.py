"""Candidate validation API (Phase 34).

Reads are open. Run/refresh persist append-only validation reports and
require the operational guard. Nothing here promotes, approves,
activates, or rolls back anything.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.db.models.candidate_validation import CandidateValidationReport
from app.services.candidate_validation import (
    DEFAULT_CONFIG_ID,
    VALIDATION_CONFIGS,
    check_staleness,
    get_config,
    get_validation,
    run_validation,
    validation_to_dict,
)
from app.services.candidate_validation.service import ValidationRunError

router = APIRouter(prefix="/candidate-validation", tags=["candidate-validation"])


def _guard() -> None:
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Validation endpoints are disabled in this environment")


class RunBody(BaseModel):
    candidate_artifact_id: str = ""
    evidence_snapshot_id: str = ""
    config_id: str = DEFAULT_CONFIG_ID


@router.get("/status")
def validation_status(db: Session = Depends(get_db)):
    total = db.query(CandidateValidationReport).count()
    by_state = {}
    for (state,) in db.query(
            CandidateValidationReport.validation_state).distinct().all():
        by_state[state or "unknown"] = db.query(
            CandidateValidationReport).filter_by(
            validation_state=state).count()
    validated = by_state.get("VALIDATED_FOR_GOVERNANCE", 0)
    return {
        "validation_count": total,
        "by_state": by_state,
        "validated_for_governance": validated,
        "production_champion": "ensemble_v1-elo+poisson",
        "note": "validation reports evidence readiness for human review; "
                "no automatic promotion exists",
    }


@router.get("/config")
def validation_config(config_id: str = Query(DEFAULT_CONFIG_ID)):
    try:
        return get_config(config_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/configs")
def validation_configs():
    return {"configs": sorted(VALIDATION_CONFIGS.keys())}


@router.get("/candidates")
def validation_candidates(db: Session = Depends(get_db)):
    rows = db.query(
        CandidateValidationReport.candidate_artifact_id).distinct().all()
    return {"candidates": sorted(r[0] for r in rows if r[0])}


@router.get("/{validation_id}")
def validation_detail(validation_id: str, db: Session = Depends(get_db)):
    try:
        return validation_to_dict(get_validation(db, validation_id))
    except ValidationRunError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)


@router.get("/{validation_id}/rules")
def validation_rules(validation_id: str, db: Session = Depends(get_db)):
    try:
        row = get_validation(db, validation_id)
    except ValidationRunError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)
    return {"validation_id": validation_id,
            "validation_state": row.validation_state,
            "rules": (row.rule_results or {}).get("rules", []),
            "by_state": (row.rule_results or {}).get("by_state", {})}


@router.get("/{validation_id}/evidence")
def validation_evidence(validation_id: str, db: Session = Depends(get_db)):
    try:
        row = get_validation(db, validation_id)
    except ValidationRunError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)
    from app.services.evidence import get_snapshot, snapshot_to_dict

    try:
        snapshot = get_snapshot(db, row.evidence_snapshot_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"validation_id": validation_id,
            "evidence": snapshot_to_dict(snapshot)}


@router.get("/{validation_id}/staleness")
def validation_staleness(validation_id: str, db: Session = Depends(get_db)):
    try:
        return check_staleness(db, validation_id)
    except ValidationRunError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)


@router.post("/run", status_code=201)
def validation_run(body: RunBody, db: Session = Depends(get_db)):
    _guard()
    if not body.candidate_artifact_id or not body.evidence_snapshot_id:
        raise HTTPException(
            status_code=422,
            detail="candidate_artifact_id and evidence_snapshot_id required")
    try:
        return run_validation(
            db, body.candidate_artifact_id, body.evidence_snapshot_id,
            config_id=body.config_id)
    except (ValidationRunError, ValueError) as exc:
        reason = getattr(exc, "reason", str(exc))
        raise HTTPException(status_code=422, detail=reason)


@router.post("/refresh")
def validation_refresh(db: Session = Depends(get_db)):
    _guard()
    from app.services.evidence import build_cohort, generate_snapshot

    cohort = build_cohort(db)
    snapshot = generate_snapshot(db, cohort.cohort_id)
    return {"cohort_id": cohort.cohort_id,
            "snapshot_id": snapshot["snapshot_id"],
            "evidence_state": snapshot["evidence_state"],
            "paired_count": snapshot["paired_count"],
            "note": "evidence refresh only; no validation run performed"}

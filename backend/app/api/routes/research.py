"""Research experiment API routes (Phase 29).

Strictly separated from production prediction APIs. Read endpoints are
open; the execution endpoint requires the operational guard AND explicit
confirmation. Nothing here can promote a candidate or touch production.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.db.models.research_registry import (
    ResearchCandidate,
    ResearchExperiment,
)
from app.services.research import (
    audit_temporal_integrity,
    build_dataset,
    candidate_to_dict,
    dataset_to_dict,
    experiment_to_dict,
    get_candidate,
    register_builtin,
    register_candidate,
    run_experiment,
    split_observations,
)
from app.services.research.candidates import BUILTIN_CANDIDATES, CandidateError
from app.services.research.datasets import DatasetError
from app.services.research.experiments import ExperimentError

router = APIRouter(prefix="/research", tags=["research"])


class RegisterCandidateRequest(BaseModel):
    name: str
    description: str = ""
    hypothesis: str = ""
    model_family: str = ""
    members: List[str] = []
    weights: List[float] = []
    declared_inputs: Dict[str, Any] = {}
    version: str = "v1"


class BuildDatasetRequest(BaseModel):
    competitions: List[str] = []
    seasons: List[str] = []
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_history: int = 3
    limit: int = 500
    dataset_version: str = "v1"


class CreateExperimentRequest(BaseModel):
    candidate_id: str
    dataset_id: str
    seed: int = 7
    limit_test: Optional[int] = None


class RunExperimentRequest(BaseModel):
    confirm: bool = False
    seed: int = 7
    limit_test: Optional[int] = None


def _parse_dt(value: Optional[str], name: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{name} must be ISO-8601")


@router.get("/candidates/builtin")
def builtin_candidates():
    return {"builtin": sorted(BUILTIN_CANDIDATES.keys())}


@router.post("/candidates", status_code=201)
def create_candidate(body: RegisterCandidateRequest,
                     db: Session = Depends(get_db)):
    try:
        row = register_candidate(
            db, name=body.name, description=body.description,
            hypothesis=body.hypothesis, model_family=body.model_family,
            members=body.members, weights=body.weights or None,
            declared_inputs=body.declared_inputs,
            version=body.version)
    except CandidateError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)
    return candidate_to_dict(row)


@router.post("/candidates/builtin/{key}", status_code=201)
def create_builtin_candidate(key: str, db: Session = Depends(get_db)):
    try:
        row = register_builtin(db, key)
    except CandidateError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)
    return candidate_to_dict(row)


@router.get("/candidates")
def list_candidates(status: Optional[str] = Query(None),
                    db: Session = Depends(get_db)):
    query = db.query(ResearchCandidate)
    if status:
        query = query.filter_by(status=status)
    return {"candidates": [
        candidate_to_dict(r)
        for r in query.order_by(ResearchCandidate.id.asc()).limit(200).all()]}


@router.get("/candidates/{candidate_id}")
def candidate_detail(candidate_id: str, db: Session = Depends(get_db)):
    try:
        return candidate_to_dict(get_candidate(db, candidate_id))
    except CandidateError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)


@router.post("/datasets", status_code=201)
def create_dataset(body: BuildDatasetRequest, db: Session = Depends(get_db)):
    try:
        row = build_dataset(
            db, competitions=body.competitions or None,
            seasons=body.seasons or None,
            date_from=_parse_dt(body.date_from, "date_from"),
            date_to=_parse_dt(body.date_to, "date_to"),
            min_history=body.min_history, limit=body.limit,
            dataset_version=body.dataset_version)
    except DatasetError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)
    return dataset_to_dict(row)


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    from app.db.models.research_registry import ResearchDataset as DS

    return {"datasets": [
        dataset_to_dict(r)
        for r in db.query(DS).order_by(DS.id.asc()).limit(200).all()]}


@router.get("/datasets/{dataset_id}")
def dataset_detail(dataset_id: str, db: Session = Depends(get_db)):
    from app.db.models.research_registry import ResearchDataset as DS

    row = db.query(DS).filter_by(dataset_id=dataset_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown dataset")
    detail = dataset_to_dict(row)
    detail["temporal_audit"] = audit_temporal_integrity(row)
    splits = split_observations(row)
    detail["split_counts"] = {k: len(v) for k, v in splits.items()}
    return detail


@router.post("/experiments", status_code=201)
def create_experiment(body: CreateExperimentRequest,
                      db: Session = Depends(get_db)):
    """Register an experiment run (creates + executes immediately).

    Requires the operational guard: research execution is explicit.
    """
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Research execution endpoints are disabled in this environment")
    try:
        return run_experiment(
            db, body.candidate_id, body.dataset_id, seed=body.seed,
            limit_test=body.limit_test)
    except (CandidateError, DatasetError, ExperimentError) as exc:
        raise HTTPException(status_code=422, detail=exc.reason)


@router.get("/experiments")
def list_experiments(candidate_id: Optional[str] = Query(None),
                     dataset_id: Optional[str] = Query(None),
                     db: Session = Depends(get_db)):
    query = db.query(ResearchExperiment)
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    if dataset_id:
        query = query.filter_by(dataset_id=dataset_id)
    return {"experiments": [
        experiment_to_dict(r)
        for r in query.order_by(ResearchExperiment.id.asc()).limit(200).all()]}


@router.get("/experiments/{experiment_id}")
def experiment_detail(experiment_id: str, db: Session = Depends(get_db)):
    row = db.query(ResearchExperiment).filter_by(
        experiment_id=experiment_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown experiment")
    return experiment_to_dict(row)


@router.post("/experiments/{experiment_id}/run")
def rerun_experiment(experiment_id: str, body: RunExperimentRequest,
                     db: Session = Depends(get_db)):
    """Re-run an existing experiment (deterministic replay).

    Requires operational guard + explicit confirm=true.
    """
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Research execution endpoints are disabled in this environment")
    if not body.confirm:
        raise HTTPException(
            status_code=422,
            detail="explicit confirm=true is required to run research")
    row = db.query(ResearchExperiment).filter_by(
        experiment_id=experiment_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown experiment")
    try:
        return run_experiment(
            db, row.candidate_id, row.dataset_id, seed=body.seed,
            limit_test=body.limit_test)
    except (CandidateError, DatasetError, ExperimentError) as exc:
        raise HTTPException(status_code=422, detail=exc.reason)


@router.get("/experiments/{experiment_id}/comparison")
def experiment_comparison(experiment_id: str, db: Session = Depends(get_db)):
    row = db.query(ResearchExperiment).filter_by(
        experiment_id=experiment_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown experiment")
    return {
        "experiment_id": row.experiment_id,
        "evidence_state": row.evidence_state,
        "leakage_status": row.leakage_status,
        "baseline_metrics": row.baseline_metrics,
        "candidate_metrics": row.candidate_metrics,
        "comparison": row.comparison,
        "uncertainty": row.uncertainty,
        "calibration": row.calibration,
    }

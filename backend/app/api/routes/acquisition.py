"""Acquisition operations endpoints (Phase 18, extended Phase 19)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.qualification import SourceQualification
from app.services.provider_qualification import health_ext

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


@router.get("/status", summary="Acquisition source/competition health")
def acquisition_status(db: Session = Depends(get_db),
                       source: Optional[str] = Query(None)):
    """Source health + latest acquisition runs + qualification + freshness
    + coverage. No credentials, no payloads."""
    from app.db.models.acquisition import AcquisitionRun
    from app.services.freshness import audit as audit_svc

    health = health_ext.describe(db, source)
    query = db.query(AcquisitionRun).order_by(AcquisitionRun.id.desc())
    if source:
        query = query.filter(AcquisitionRun.source == source)
    runs = query.limit(20).all()
    qualifications = {}
    for qual in db.query(SourceQualification).order_by(
            SourceQualification.id.desc()).limit(20).all():
        if source and qual.source != source:
            continue
        qualifications.setdefault(qual.source, []).append(
            {"status": qual.status, "competition": qual.competition,
             "season": qual.season, "fixture_count": qual.fixture_count,
             "retrieved_at": str(qual.retrieved_at)})
    try:
        coverage = audit_svc.current_season_audit(db)
    except Exception:
        coverage = {"status": "unavailable"}
    return {
        "health": health,
        "qualifications": qualifications,
        "freshness": {name: (entry.get("last_observed_fixture")
                             if isinstance(entry, dict) else None)
                      for name, entry in health.items()},
        "coverage": coverage,
        "recent_runs": [
            {"run_id": r.run_id, "source": r.source, "job": r.job,
             "status": r.status,
             "started_at": str(r.started_at) if r.started_at else None,
             "finished_at": str(r.finished_at) if r.finished_at else None,
             "records_seen": r.records_seen,
             "records_created": r.records_created,
             "records_updated": r.records_updated,
             "records_rejected": r.records_rejected,
             "records_quarantined": r.records_quarantined,
             "errors": r.errors}
            for r in runs
        ],
    }


from pydantic import BaseModel
from fastapi import HTTPException
from app.config import get_settings


class ActivationRequest(BaseModel):
    source: str = "api_football"
    competition: str
    season: str = "current"
    force: bool = False
    reason: str = "api activation"
    actor: str = "api_operator"


class RevocationRequest(BaseModel):
    source: str = "api_football"
    competition: str
    season: str = "current"
    reason: str = "revoked via api"
    actor: str = "api_operator"


@router.get("/readiness", summary="Current season readiness report")
def current_season_readiness_endpoint(
    season: str = Query("current"),
    competition: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Evidence-based current-season readiness and activation status across competitions."""
    from app.services.acquisition.current_season import get_current_season_readiness_report
    leagues = [competition] if competition else None
    return get_current_season_readiness_report(db, season=season, leagues=leagues)


@router.post("/activate", summary="Controlled current-season provider activation")
def activate_provider_endpoint(
    body: ActivationRequest,
    db: Session = Depends(get_db),
):
    """Explicit, audited operational activation of a provider for a competition and season."""
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Operational mutation endpoints are disabled in this environment",
        )
    from app.services.acquisition.activation import activate_current_season
    from app.services.acquisition.current_season import current_canonical_season

    season = current_canonical_season() if body.season == "current" else body.season
    result = activate_current_season(
        db,
        source=body.source,
        competition=body.competition,
        season=season,
        actor=body.actor,
        reason=body.reason,
        force=body.force,
    )
    if not result.get("success", False) and not body.force:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Provider {body.source} cannot be activated for {body.competition}",
                "result": result,
            },
        )
    return result


@router.post("/revoke", summary="Revoke current-season provider activation")
def revoke_provider_endpoint(
    body: RevocationRequest,
    db: Session = Depends(get_db),
):
    """Revoke an active provider for a competition and season."""
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Operational mutation endpoints are disabled in this environment",
        )
    from app.services.acquisition.activation import revoke_activation
    from app.services.acquisition.current_season import current_canonical_season

    season = current_canonical_season() if body.season == "current" else body.season
    return revoke_activation(
        db,
        provider=body.source,
        competition=body.competition,
        season=season,
        reason=body.reason,
        decided_by=body.actor,
    )


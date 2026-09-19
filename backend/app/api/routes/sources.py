"""Source metadata endpoints (Phase 19, read-only except qualify).

No credentials, no raw payloads, no arbitrary URLs: the optional qualify
endpoint accepts only competition/season/budget and resolves adapters from
the trusted registry.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.services.provider_qualification import health_ext, registry

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", summary="Safe source metadata")
def list_sources(db: Session = Depends(get_db)):
    """Registered sources with capabilities, qualification and health.
    No credentials, no raw payloads."""
    entries = registry.get_registry().describe()
    health = health_ext.describe(db)
    out = []
    for source_id, entry in entries.items():
        item = dict(entry)
        item["health"] = health.get(source_id, {"state": "unknown"})
        out.append(item)
    return {"sources": out}


@router.get("/{source_id}/status", summary="Source status")
def source_status(source_id: str, db: Session = Depends(get_db)):
    try:
        entry = registry.get_registry().get(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    health = health_ext.describe(db, source_id)
    return {"source": entry.describe(),
            "health": health.get(source_id, {"state": "unknown"})}


@router.get("/{source_id}/qualification", summary="Latest qualification evidence")
def source_qualification(source_id: str, db: Session = Depends(get_db),
                         competition: Optional[str] = Query(None),
                         season: Optional[str] = Query(None)):
    try:
        registry.get_registry().get(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    from app.services.provider_qualification import snapshots as snapshots_mod

    return snapshots_mod.latest_for(db, source_id, competition or "",
                                    season or "")


class QualifyRequest(BaseModel):
    competition: Optional[str] = None
    season: Optional[str] = None
    max_requests: int = 5


@router.post("/{source_id}/qualify", summary="Run source qualification")
def qualify_source_endpoint(source_id: str, request: QualifyRequest,
                            db: Session = Depends(get_db)):
    """Bounded live qualification. Accepts only competition/season/budget —
    never URLs, credentials, or adapter names beyond the registry id."""
    try:
        registry.get_registry().get(source_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    if request.max_requests is not None and not 1 <= request.max_requests <= 10:
        raise HTTPException(400, "max_requests must be within 1..10")
    from app.services.provider_qualification import health_ext
    from app.services.provider_qualification import qualification as qual_svc

    verdict = qual_svc.qualify_source(
        source_id, competition=request.competition, season=request.season,
        max_requests=request.max_requests, db=db)
    health_ext.record_qualification(db, source_id, verdict["status"])
    return verdict

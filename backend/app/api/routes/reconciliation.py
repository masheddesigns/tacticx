"""Reconciliation + data-quality endpoints (Phase 8).

Read-only except manual mappings (audited, versioned). Raw source strings
are returned as stored; no secrets exist in this subsystem.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.db.models.reconciliation import ReconciliationConflict

router = APIRouter(tags=["reconciliation"])


class MappingRequest(BaseModel):
    entity_type: str = "team"
    source: str = ""
    source_record_id: str = ""
    canonical_id: int = 0
    created_by: str = "api"


@router.get("/data-quality", summary="Coverage + conflicts + quality report")
def data_quality(db: Session = Depends(get_db), league: Optional[str] = None):
    from app.services.reconciliation import conflicts as conflict_svc
    from app.services.reconciliation import identities, matrix, quality

    return {
        "coverage": matrix.canonical_coverage(db, league_code=league),
        "completeness": quality.league_completeness(db, league_code=league),
        "conflicts": conflict_svc.summarize(db),
        "unresolved_queue": identities.queue_summary(db),
        "sources": matrix.coverage_matrix(db),
        "registry": matrix.source_registry_view(db),
    }


@router.get("/data-quality/{entity_type}", summary="Quality slice by entity")
def data_quality_entity(entity_type: str, db: Session = Depends(get_db),
                        league: Optional[str] = None):
    from app.services.reconciliation import identities, matrix, quality
    from app.services.reconciliation import conflicts as conflict_svc

    if entity_type == "matches":
        return matrix.canonical_coverage(db, league_code=league)
    if entity_type == "conflicts":
        return conflict_svc.summarize(db)
    if entity_type == "queue":
        return identities.queue_summary(db)
    if entity_type == "sources":
        return matrix.coverage_matrix(db)
    if entity_type == "completeness":
        return quality.league_completeness(db, league_code=league)
    raise HTTPException(404, f"unknown entity type: {entity_type} "
                             "(matches|conflicts|queue|sources|completeness)")


@router.get("/matches/{match_id}/sources", summary="Source mappings for a match")
def match_sources(match_id: int, db: Session = Depends(get_db)):
    from app.db.models.provenance import MatchSourceMapping

    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    rows = db.query(MatchSourceMapping).filter_by(match_id=match_id).all()
    match = db.get(Match, match_id)
    native = []
    if match and match.provider:
        native.append({"source": match.provider,
                       "source_match_id": match.provider_match_id})
    return {"data": native + [
        {"source": r.source, "source_match_id": r.source_match_id,
         "created_at": str(r.created_at)} for r in rows]}


@router.get("/matches/{match_id}/conflicts", summary="Conflicts for a match")
def match_conflicts(match_id: int, db: Session = Depends(get_db),
                    status: Optional[str] = None):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    query = db.query(ReconciliationConflict).filter_by(
        entity_type="match", canonical_entity_id=match_id)
    if status:
        query = query.filter_by(resolution_status=status)
    return {"data": [{
        "id": r.id, "field": r.field, "source_a": r.source_a,
        "source_b": r.source_b, "value_a": r.value_a, "value_b": r.value_b,
        "severity": r.severity, "classification": r.classification,
        "resolution_status": r.resolution_status, "resolved_by": r.resolved_by,
        "detected_at": str(r.detected_at)} for r in query.all()]}


@router.get("/matches/{match_id}/provenance", summary="Field-level provenance")
def match_provenance(match_id: int, db: Session = Depends(get_db)):
    from app.db.models.provenance import MatchSourceMapping, RawDataRecord

    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    mappings = db.query(MatchSourceMapping).filter_by(match_id=match_id).all()
    raws = db.query(RawDataRecord).filter_by(entity_type="match").all()
    mine = [r for r in raws if str(match_id) in (r.source_record_id or "")]
    fields = {
        "score": {"value": f"{match.home_score}-{match.away_score}",
                  "source": match.provider or "", "quality": "verified"
                  if match.status == "FINISHED" else "unknown"},
        "kickoff": {"value": str(match.kickoff_at), "source": match.provider or "",
                    "quality": "verified" if match.kickoff_at else "unknown"},
        "status": {"value": match.status, "source": match.provider or "",
                   "quality": "verified"},
    }
    return {"match_id": match_id, "fields": fields,
            "mappings": [{"source": r.source, "source_match_id": r.source_match_id}
                         for r in mappings],
            "raw_records": [{"source": r.source,
                             "source_record_id": r.source_record_id,
                             "retrieved_at": str(r.retrieved_at),
                             "processing_status": r.processing_status} for r in mine]}


@router.post("/reconciliation/mappings", summary="Apply a manual mapping")
def create_mapping(request: MappingRequest, db: Session = Depends(get_db)):
    from app.services.reconciliation import identities

    try:
        return identities.apply_manual_mapping(
            db, request.entity_type, request.source, request.source_record_id,
            request.canonical_id, created_by=request.created_by)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/reconciliation/queue", summary="Unresolved record queue")
def unresolved_queue(db: Session = Depends(get_db), status: Optional[str] = None,
                     limit: int = 100):
    from app.db.models.reconciliation import UnresolvedRecord

    query = db.query(UnresolvedRecord)
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(UnresolvedRecord.last_seen.desc()).limit(
        max(1, min(limit, 1000))).all()
    return {"data": [{
        "id": r.id, "entity_type": r.entity_type, "source": r.source,
        "source_record_id": r.source_record_id, "reason": r.reason,
        "first_seen": str(r.first_seen), "last_seen": str(r.last_seen),
        "status": r.status} for r in rows]}

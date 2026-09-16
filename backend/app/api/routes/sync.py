"""Sync/ingestion trigger endpoints (manual + visibility for the scheduler)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import League
from app.db.models.logs import DataSyncLog

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/logs", summary="Recent ingestion runs (visibility into quota + failures)")
def sync_logs(db: Session = Depends(get_db), limit: int = 20):
    rows = db.query(DataSyncLog).order_by(DataSyncLog.created_at.desc()).limit(min(limit, 100)).all()
    return {"data": [
        {"provider": r.provider, "operation": r.operation, "league": r.league,
         "match_id": r.match_id, "received": r.records_received, "inserted": r.records_inserted,
         "updated": r.records_updated, "skipped": r.records_skipped,
         "duration_seconds": r.duration_seconds, "errors": r.errors,
         "created_at": r.created_at}
        for r in rows
    ]}


@router.get("/leagues", summary="Configured leagues and their provider mapping")
def configured_leagues(db: Session = Depends(get_db)):
    from app.config import get_settings

    configured = {e["code"]: e for e in get_settings().supported_leagues_parsed()}
    rows = db.query(League).all()
    stored = {r.code: r for r in rows}
    return {"data": [
        {"code": code, "provider_id": e["provider_id"], "season": e["season"],
         "ingested": code in stored}
        for code, e in configured.items()
    ]}

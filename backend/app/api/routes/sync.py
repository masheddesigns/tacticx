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


@router.post("/seed-expanded", summary="Re-seed authentic expanded leagues fixtures and predictions")
def trigger_seed_expanded(db: Session = Depends(get_db)):
    try:
        try:
            from scripts.seed_expanded_leagues import seed_expanded_leagues
        except ImportError:
            from backend.scripts.seed_expanded_leagues import seed_expanded_leagues
        result = seed_expanded_leagues(db)
        return {"status": "success", "result": result}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@router.post("/fix-fixtures", summary="Purge fabricated fixtures and ensure authentic Oct 20-21 schedule")
def trigger_fix_fixtures(db: Session = Depends(get_db)):
    try:
        from app.services.match_progression import purge_phantom_fixtures_if_needed, ensure_authentic_october_fixtures
        from app.api.routes.matches import _DAILY_SLIPS_CACHE
        purge_phantom_fixtures_if_needed(db)
        ensure_authentic_october_fixtures(db)
        _DAILY_SLIPS_CACHE.clear()
        return {"status": "success", "message": "Purged phantom fixtures and ensured authentic Oct 20-21 schedule"}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}



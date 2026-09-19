"""MiroFish scenario endpoints (Phase 16, read-only + derived runs).

GET returns stored scenario information without touching the core
prediction. POST executes whitelisted scenarios only. Provider failure
yields a machine-readable unavailable state — never HTTP 500 for provider
problems, never a mutation of statistical output.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.db.models.mirofish import MiroFishScenarioRun
from app.services.features.temporal import TemporalMode
from app.services.mirofish import config as config_mod, scenario_builder, service

router = APIRouter(tags=["mirofish"])


class MirofishRunRequest(BaseModel):
    scenario_id: str = "baseline"
    mode: str = "strict_prematch"
    cutoff: Optional[str] = None
    model: Optional[str] = None


class MirofishBatchRequest(BaseModel):
    scenario_ids: Optional[List[str]] = None
    mode: str = "strict_prematch"
    cutoff: Optional[str] = None
    model: Optional[str] = None


def _resolve(match_id: int, db: Session, mode: str, cutoff: Optional[str],
             model: Optional[str] = None):
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "match not found")
    try:
        resolved_mode = TemporalMode(mode)
    except ValueError:
        raise HTTPException(400, "mode must be strict_prematch or historical_estimated")
    try:
        resolved_cutoff = datetime.fromisoformat(cutoff) if cutoff else match.kickoff_at
    except ValueError:
        raise HTTPException(400, "cutoff must be ISO format")
    if resolved_cutoff is None:
        raise HTTPException(400, "match has no kickoff; pass cutoff explicitly")
    if model is not None:
        from app.services.intelligence.composer import build_core_model

        try:
            build_core_model(model)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return resolved_cutoff, resolved_mode


def _row_out(row: MiroFishScenarioRun) -> dict:
    return {"run_id": row.id, "match_id": row.match_id,
            "scenario_id": row.scenario_id, "status": row.status,
            "provider": row.provider,
            "contract_version": row.contract_version,
            "request_hash": row.request_hash,
            "response_hash": row.response_hash,
            "result": row.result_payload}


@router.get("/intelligence/{match_id}/mirofish",
            summary="Latest MiroFish scenario information")
def mirofish_latest(match_id: int, db: Session = Depends(get_db),
                    scenario_id: Optional[str] = None):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    result = service.latest_result(db, match_id, scenario_id)
    if result is None:
        return {"status": "unavailable", "error_code": "no_runs",
                "error_detail": "no MiroFish runs recorded for this match",
                "config": config_mod.diagnose()}
    return result


@router.get("/intelligence/{match_id}/mirofish/{scenario_id}",
            summary="Specific MiroFish scenario result")
def mirofish_specific(match_id: int, scenario_id: str,
                      db: Session = Depends(get_db)):
    if scenario_id not in scenario_builder.allowed_scenario_ids():
        raise HTTPException(400, f"unknown scenario: {scenario_id}")
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    result = service.latest_result(db, match_id, scenario_id)
    if result is None:
        return {"status": "unavailable", "error_code": "no_runs",
                "error_detail": f"no runs recorded for scenario {scenario_id}"}
    return result


@router.post("/intelligence/{match_id}/mirofish",
             summary="Run a MiroFish scenario")
def mirofish_run(match_id: int, request: MirofishRunRequest,
                 db: Session = Depends(get_db)):
    if request.scenario_id not in scenario_builder.allowed_scenario_ids():
        raise HTTPException(400,
                            f"unknown scenario: {request.scenario_id} "
                            f"(known: {scenario_builder.allowed_scenario_ids()})")
    resolved_cutoff, resolved_mode = _resolve(match_id, db, request.mode,
                                              request.cutoff, request.model)
    try:
        return service.run_mirofish_scenario(
            db, match_id, resolved_cutoff, request.scenario_id,
            resolved_mode, model=request.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/intelligence/{match_id}/mirofish/batch",
             summary="Run whitelisted MiroFish scenarios")
def mirofish_batch(match_id: int, request: MirofishBatchRequest,
                   db: Session = Depends(get_db)):
    resolved_cutoff, resolved_mode = _resolve(match_id, db, request.mode,
                                              request.cutoff, request.model)
    try:
        return service.run_mirofish_batch(
            db, match_id, resolved_cutoff, request.scenario_ids,
            resolved_mode, model=request.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

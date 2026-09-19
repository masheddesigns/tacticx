"""MiroFish service orchestrator (Phase 16).

Flow: cutoff-gated intelligence → whitelisted scenario → deterministic
request → provider → strict validation → identity verification (baseline,
match, scenario, contract) → append-only persistence → structured result.

The orchestrator reads predictions, features, odds and history; it writes
only MiroFishScenarioRun rows. Core prediction latency is unaffected by
provider failure: any failure yields a machine-readable unavailable state.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.mirofish import MiroFishScenarioRun
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.mirofish import (
    adapter,
    config as config_mod,
    provenance as provenance_mod,
    request_builder,
    response_parser,
    scenario_builder,
    validation as validation_mod,
)
from app.services.mirofish.contracts import MIROFISH_CONTRACT_VERSION, payload_hash
from app.services.mirofish.errors import MiroFishError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_mirofish_scenario(
    db: Session,
    match_id: int,
    cutoff: datetime,
    scenario_id: str = "baseline",
    mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    provider: Optional[adapter.MiroFishProvider] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Execute one whitelisted scenario through the MiroFish layer."""
    from app.services.intelligence.composer import PredictionComposer

    config = config_mod.load_config()
    started = _utcnow()
    started_ms = time.monotonic()
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"unknown match: {match_id}")
    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise ValueError("cutoff is required")
    # Baseline: cutoff-gated composed prediction (statistical, immutable).
    composed = PredictionComposer().compose(db, match_id, cutoff, mode,
                                            model=model, seed=seed)
    dump = composed.model_dump()
    baseline_hash = payload_hash({
        "probabilities": dump.get("probabilities", {}),
        "goals": dump.get("goals", {}),
        "model": (dump.get("model") or {}).get("version", ""),
    })
    intel_hash = payload_hash({
        "match_id": match_id, "cutoff": str(naive_cutoff),
        "baseline": baseline_hash,
        "temporal_mode": mode.value,
    })
    scenario = scenario_builder.build_definition(
        {k: dump["probabilities"][k] for k in ("home", "draw", "away")},
        (dump.get("goals") or {}).get("home_lambda"),
        (dump.get("goals") or {}).get("away_lambda"),
        scenario_id, baseline_hash)
    baseline_hashes = {"baseline_prediction": baseline_hash,
                       "intelligence_snapshot": intel_hash}
    request = request_builder.build_request(dump, scenario,
                                            config.contract_version,
                                            baseline_hashes)
    request_json = request_builder.request_json(request)
    req_hash = request_builder.request_hash(request)
    chosen = provider or adapter.select_provider()
    provenance = provenance_mod.assemble(
        match_id, str(naive_cutoff),
        (dump.get("model") or {}).get("version", ""), intel_hash,
        scenario_id, scenario.scenario_hash, config.contract_version,
        chosen.name, req_hash)
    expected = {"match_id": match_id, "cutoff": str(naive_cutoff),
                "scenario_id": scenario_id,
                "scenario_hash": scenario.scenario_hash,
                "baseline_prediction_hash": baseline_hash,
                "intelligence_snapshot_hash": intel_hash}
    try:
        import asyncio

        raw = asyncio.run(asyncio.wait_for(
            chosen.run_scenario(request_json),
            timeout=config.timeout_seconds))
    except MiroFishError as exc:
        return _persist_unavailable(db, match_id, provenance, chosen.name,
                                    started, exc.code, exc.detail,
                                    scenario, req_hash, persist)
    except (asyncio.TimeoutError, TimeoutError):
        return _persist_unavailable(db, match_id, provenance, chosen.name,
                                    started, "provider_timeout",
                                    f"MiroFish timed out after "
                                    f"{config.timeout_seconds}s",
                                    scenario, req_hash, persist)
    duration_ms = int((time.monotonic() - started_ms) * 1000)
    completed = _utcnow().isoformat()
    check = validation_mod.validate_response(raw, expected,
                                             config.response_max_bytes)
    if not check["valid"]:
        joined = "; ".join(check["errors"])
        if "contract mismatch" in joined:
            code = "contract_mismatch"
        elif any(word in joined for word in ("missing", "invalid", "sums",
                                             "non-finite")):
            code = "invalid_response"
        else:
            code = "contract_mismatch"
        return _persist_unavailable(
            db, match_id, provenance, chosen.name, started, code,
            joined[:500], scenario, req_hash, persist,
            duration_ms=duration_ms, completed_at=completed)
    result = response_parser.parse_validated(
        check["response"], started.isoformat(), completed, duration_ms)
    result["provenance"] = provenance
    if persist:
        _persist_run(db, match_id, provenance, chosen.name, started,
                     completed, result, scenario, req_hash)
    return result


def run_mirofish_batch(
    db: Session,
    match_id: int,
    cutoff: datetime,
    scenario_ids: Optional[List[str]] = None,
    mode: TemporalMode = TemporalMode.STRICT_PREMATCH,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    provider: Optional[adapter.MiroFishProvider] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Bounded batch over whitelisted scenarios: deterministic order,
    per-scenario status, partial success. No duplicate execution when an
    identical immutable result row already exists."""
    config = config_mod.load_config()
    ids = scenario_ids or scenario_builder.allowed_scenario_ids()
    unknown = [name for name in ids if name not in scenario_builder.allowed_scenario_ids()]
    if unknown:
        raise ValueError(f"unknown scenario IDs: {unknown}")
    ids = sorted(set(ids))
    if len(ids) > config.max_scenarios:
        raise ValueError(f"batch of {len(ids)} scenarios exceeds maximum "
                         f"{config.max_scenarios}")
    results = []
    for scenario_id in ids:
        try:
            result = run_mirofish_scenario(db, match_id, cutoff, scenario_id,
                                           mode, model, seed, provider, persist)
        except (ValueError, MiroFishError) as exc:
            result = response_parser.unavailable_result(
                getattr(exc, "code", "provider_error"), str(exc)[:500],
                {"match_id": match_id, "cutoff": str(cutoff),
                 "scenario_id": scenario_id},
                provider.name if provider else "")
        results.append({"scenario_id": scenario_id, "result": result})
    ok = sum(1 for r in results if r["result"].get("status") == "ok")
    return {"match_id": match_id, "scenarios": results,
            "succeeded": ok, "failed": len(results) - ok,
            "status": "ok" if ok == len(results) else (
                "partial" if ok else "unavailable")}


def latest_result(db: Session, match_id: int,
                  scenario_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query = db.query(MiroFishScenarioRun).filter_by(match_id=match_id)
    if scenario_id:
        query = query.filter_by(scenario_id=scenario_id)
    row = query.order_by(MiroFishScenarioRun.id.desc()).first()
    return dict(row.result_payload) if row and row.result_payload else None


def _persist_unavailable(db: Session, match_id: int, provenance: Dict[str, Any],
                         provider_name: str, started: datetime, code: str,
                         detail: str, scenario, req_hash: str, persist: bool,
                         duration_ms: int = 0,
                         completed_at: Optional[str] = None) -> Dict[str, Any]:
    result = response_parser.unavailable_result(code, detail, provenance,
                                                provider_name)
    result["scenario_hash"] = scenario.scenario_hash
    if persist:
        _persist_run(db, match_id, provenance, provider_name, started,
                     completed_at or _utcnow().isoformat(), result, scenario,
                     req_hash, duration_ms=duration_ms)
    return result


def _persist_run(db: Session, match_id: int, provenance: Dict[str, Any],
                 provider_name: str, started: datetime, completed,
                 result: Dict[str, Any], scenario, req_hash: str,
                 duration_ms: Optional[int] = None) -> None:
    if isinstance(completed, str):
        try:
            completed_dt = datetime.fromisoformat(completed)
        except ValueError:
            completed_dt = _utcnow()
    else:
        completed_dt = completed or _utcnow()
    db.add(MiroFishScenarioRun(
        match_id=match_id,
        intelligence_snapshot_id=provenance.get("intelligence_snapshot_hash"),
        contract_version=provenance.get(
            "contract_version", MIROFISH_CONTRACT_VERSION),
        scenario_id=provenance.get("scenario_id", ""),
        scenario_hash=scenario.scenario_hash,
        request_hash=req_hash,
        response_hash=result.get("response_hash", ""),
        provider=provider_name,
        status=result.get("status", "unavailable"),
        started_at=started, completed_at=completed_dt,
        result_payload=result,
        error_code=result.get("error_code", "")))
    db.commit()

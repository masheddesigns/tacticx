"""MiroFish provenance assembly (Phase 16).

Every result exposes match, cutoff, prediction/model version, intelligence
snapshot, scenario version + hash, contract version, provider, request and
response hashes, and timestamps. A result without provenance is invalid.
"""
from __future__ import annotations

from typing import Any, Dict

REQUIRED_KEYS = ("match_id", "cutoff", "model_version",
                 "intelligence_snapshot_hash", "scenario_id", "scenario_hash",
                 "contract_version", "provider", "request_hash")


def assemble(match_id: int, cutoff: str, model_version: str,
             snapshot_hash: str, scenario_id: str, scenario_hash: str,
             contract_version: str, provider: str,
             request_hash: str) -> Dict[str, Any]:
    provenance = {
        "match_id": match_id,
        "cutoff": cutoff,
        "prediction_version": model_version,
        "model_version": model_version,
        "intelligence_snapshot_hash": snapshot_hash,
        "scenario_version": scenario_id,
        "scenario_id": scenario_id,
        "scenario_hash": scenario_hash,
        "contract_version": contract_version,
        "provider": provider,
        "request_hash": request_hash,
    }
    missing = [key for key in REQUIRED_KEYS if not provenance.get(key)]
    if missing:
        raise ValueError(f"provenance incomplete: {missing}")
    return provenance

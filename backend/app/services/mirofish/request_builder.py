"""Deterministic MiroFish request construction (Phase 16).

Built exclusively from a Phase 15 intelligence response plus a whitelisted
scenario definition. Only whitelisted fields are copied — the database
record is never sent blindly. Post-cutoff material cannot enter because the
intelligence response itself is cutoff-gated; the builder additionally drops
anything resembling results/closing data if ever present.
"""
from __future__ import annotations

from typing import Any, Dict

from app.services.mirofish.contracts import (
    CORE_PREDICTION_FIELDS,
    GOALS_FIELDS,
    MiroFishRequest,
    REQUEST_FIELDS,
    ScenarioDefinition,
    canonical_json,
    payload_hash,
)

# Fields that must never be sent even if present upstream.
FORBIDDEN_SUBSTRINGS = ("result", "closing", "final_score", "actual_")


def _pick(source: Dict[str, Any], keys) -> Dict[str, Any]:
    return {k: source.get(k) for k in keys if k in source}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()
                if not any(bad in str(k).lower() for bad in FORBIDDEN_SUBSTRINGS)}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def build_request(composed: Dict[str, Any],
                  scenario: ScenarioDefinition,
                  contract_version: str,
                  baseline_hashes: Dict[str, str]) -> MiroFishRequest:
    """Assemble the whitelisted request from a composed Phase 6/15 dump.
    Raises on missing essentials."""
    match = composed.get("match", {}) or {}
    probabilities = composed.get("probabilities", {}) or {}
    goals = composed.get("goals", {}) or {}
    if not all(k in probabilities for k in CORE_PREDICTION_FIELDS):
        raise ValueError("composed output lacks 1X2 probabilities")
    if not all(k in goals for k in GOALS_FIELDS):
        raise ValueError("composed output lacks goal lambdas")
    provenance = composed.get("provenance", {}) or {}
    request = MiroFishRequest(
        contract_version=contract_version,
        match_id=int(match.get("match_id", 0) or 0),
        competition=str(match.get("league_id", "")
                        or provenance.get("competition", "")),
        kickoff=str(match.get("kickoff_at", "")),
        cutoff=str(provenance.get("cutoff", "") or composed.get("cutoff", "")),
        home_team=_scrub({"team_id": match.get("home_team_id")}),
        away_team=_scrub({"team_id": match.get("away_team_id")}),
        core_prediction={k: float(probabilities[k]) for k in CORE_PREDICTION_FIELDS},
        derived_probabilities=_scrub({
            "double_chance": ((composed.get("markets") or {}).get(
                "double_chance") or {}).get("probabilities", {}),
            "totals": ((composed.get("markets") or {}).get("totals") or {}).get(
                "probabilities", {}),
            "btts": (composed.get("markets") or {}).get("btts", {}),
        }),
        expected_goals={k: goals[k] for k in GOALS_FIELDS},
        uncertainty=_scrub(composed.get("uncertainty", {}) or {}),
        model_disagreement=_scrub(composed.get("model_disagreement", {}) or {}),
        data_completeness=_scrub((composed.get("data_quality") or {})),
        temporal_quality=_scrub({
            "mode": provenance.get("temporal_mode", ""),
            "estimated_fields": (composed.get("data_quality") or {}).get(
                "estimated_fields", []),
        }),
        scenario=scenario,
        provenance=_scrub({
            "model": (composed.get("model") or {}),
            "temporal_mode": provenance.get("temporal_mode", ""),
            "intelligence_snapshot_hash": provenance.get("hash", ""),
        }),
        baseline_hashes=dict(baseline_hashes),
    )
    # Enforce the whitelist at the top level (defense in depth).
    dumped = request.model_dump()
    assert set(dumped) <= set(REQUEST_FIELDS), "request leaked non-whitelisted fields"
    return request


def request_hash(request: MiroFishRequest) -> str:
    return payload_hash(request.model_dump())


def request_json(request: MiroFishRequest) -> str:
    return canonical_json(request.model_dump())

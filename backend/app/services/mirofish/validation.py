"""Strict MiroFish response validation (Phase 16).

Validates contract version, match/scenario/baseline identity, required
fields, types, probability ranges and sums, finiteness (no NaN/infinity),
size and provenance. Malformed responses are rejected with reasons — never
repaired, never silently accepted.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.services.mirofish.contracts import (
    MIROFISH_CONTRACT_VERSION,
    is_finite_number,
)

REQUIRED_FIELDS = ("contract_version", "match_id", "cutoff", "scenario_id",
                   "scenario_hash", "baseline_prediction_hash",
                   "intelligence_snapshot_hash", "provider")


def validate_response(payload: Dict[str, Any], expected: Dict[str, Any],
                      max_bytes: int) -> Dict[str, Any]:
    """Validate a decoded provider response against the expected identity
    envelope. Returns {valid, errors, response}."""
    from app.services.mirofish.contracts import canonical_json

    errors: List[str] = []
    if len(canonical_json(payload).encode()) > max_bytes:
        errors.append(f"response exceeds {max_bytes} bytes")
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing field: {field}")
    if payload.get("contract_version") != MIROFISH_CONTRACT_VERSION:
        errors.append(
            f"contract mismatch: {payload.get('contract_version')!r} != "
            f"{MIROFISH_CONTRACT_VERSION!r}")
    for key in ("match_id", "cutoff", "scenario_id", "scenario_hash",
                "baseline_prediction_hash", "intelligence_snapshot_hash"):
        if key in payload and key in expected \
                and payload.get(key) != expected.get(key):
            errors.append(f"identity mismatch on {key}")
    probs = payload.get("scenario_probabilities")
    if probs is not None:
        if not isinstance(probs, dict):
            errors.append("scenario_probabilities is not an object")
        else:
            for key in ("home", "draw", "away"):
                if key in probs and not (
                        is_finite_number(probs[key]) and 0.0 <= probs[key] <= 1.0):
                    errors.append(f"scenario_probabilities[{key}] invalid")
            if all(k in probs for k in ("home", "draw", "away")):
                total = probs["home"] + probs["draw"] + probs["away"]
                if not (is_finite_number(total) and abs(total - 1.0) <= 1e-3):
                    errors.append(f"scenario 1X2 sums to {total!r}")
    grid = payload.get("score_distribution")
    if grid is not None:
        if not isinstance(grid, dict):
            errors.append("score_distribution is not an object")
        else:
            values = list(grid.values())
            if values and not all(is_finite_number(v) and 0.0 <= v <= 1.0
                                  for v in values):
                errors.append("score_distribution has invalid entries")
            elif values and abs(sum(values) - 1.0) > 1e-3:
                errors.append("score_distribution does not sum to 1")
    for key, value in payload.items():
        if isinstance(value, float) and not is_finite_number(value):
            errors.append(f"non-finite numeric field: {key}")
    return {"valid": not errors, "errors": errors, "response": payload}

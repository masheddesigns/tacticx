"""Phase 32 shadow execution contracts.

Shadow evidence does not authorize production activation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

SHADOW_CONTRACT_VERSION = "SHADOW_EXECUTION_V1"
SHADOW_PAIR_INVALID = "SHADOW_PAIR_INVALID"
SHADOW_INCOMPATIBLE = "INCOMPATIBLE"

# Operational states for eligibility scanning.
NO_ELIGIBLE_MATCHES = "NO_ELIGIBLE_MATCHES"
ELIGIBLE = "ELIGIBLE"

# Evaluation states on shadow rows.
EVAL_PENDING = "PENDING"
EVAL_EVALUATED = "EVALUATED"
EVAL_INSUFFICIENT = "INSUFFICIENT_DATA"


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def shadow_execution_key(
    match_id: int,
    challenger_artifact_id: str,
    feature_snapshot_hash: str,
    cutoff_iso: str,
    prediction_mode: str = "PRE_MATCH",
) -> str:
    return canonical_hash({
        "contract": SHADOW_CONTRACT_VERSION,
        "match_id": match_id,
        "challenger_artifact_id": challenger_artifact_id,
        "feature_snapshot_hash": feature_snapshot_hash,
        "cutoff": cutoff_iso,
        "prediction_mode": prediction_mode,
    })

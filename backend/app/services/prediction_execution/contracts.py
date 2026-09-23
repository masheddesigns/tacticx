"""Phase 26 execution contracts: constants, canonical hashing, identity.

No model mathematics here. No readiness evaluation here (Phase 25.1 owns it).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

EXECUTION_CONTRACT_VERSION = "PREMATCH_PREDICTION_V1"
FEATURE_SNAPSHOT_VERSION = "features_v1"
PREDICTION_MODE = "PRE_MATCH"

ELIGIBLE_READINESS = ("PREDICTION_READY", "READY_DEGRADED")

# Probability-sum tolerance for 1X2 validation.
PROB_SUM_TOLERANCE = 1e-4

SUPPORTED_MODEL_IDS = ("ensemble_v1-elo+poisson",)


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_cutoff_iso(value: Any) -> str:
    """Normalize any datetime/ISO input to naive-UTC ISO without microseconds drift."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat()


def execution_key(
    match_id: int,
    cutoff_iso: str,
    model_id: str,
    model_version: str,
    feature_snapshot_hash: str,
) -> str:
    return canonical_hash({
        "contract": EXECUTION_CONTRACT_VERSION,
        "match_id": match_id,
        "cutoff": normalize_cutoff_iso(cutoff_iso),
        "model_id": model_id,
        "model_version": model_version,
        "feature_snapshot_hash": feature_snapshot_hash,
    })


def ensemble_members(model_id: str) -> list:
    """Derive registry member names from an ensemble model id.

    Only the production ensemble is supported; anything else is rejected
    by the caller before reaching the model.
    """
    if model_id not in SUPPORTED_MODEL_IDS:
        raise ValueError(f"unsupported model_id for Phase 26 execution: {model_id}")
    suffix = model_id.split("-", 1)[1]
    return suffix.split("+")

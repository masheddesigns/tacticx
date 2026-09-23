"""Phase 27 evaluation contracts: constants, hashing, eligibility.

Evaluation happens AFTER the match result is legitimately available.
Nothing here touches prediction generation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

EVALUATION_CONTRACT_VERSION = "PREDICTION_EVALUATION_V1"
OUTCOME_CONTRACT_VERSION = "MATCH_OUTCOME_V1"

# Only a canonical FINISHED result with recorded scores is evaluable.
ELIGIBLE_STATUS = ("FINISHED",)
# Defensive tolerance (mirrors readiness Gate 3): never evaluable.
INELIGIBLE_STATUSES = (
    "SCHEDULED", "PRE_MATCH", "LIVE", "HALFTIME",
    "POSTPONED", "CANCELLED", "SUSPENDED", "ABANDONED",
)

RESULT_HOME = "home"
RESULT_DRAW = "draw"
RESULT_AWAY = "away"

# Minimum sample for windowed drift comparisons to be reported.
MIN_DRIFT_SAMPLE = 20


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def result_from_goals(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return RESULT_HOME
    if home_goals < away_goals:
        return RESULT_AWAY
    return RESULT_DRAW


def result_index(result: str) -> int:
    return {RESULT_HOME: 0, RESULT_DRAW: 1, RESULT_AWAY: 2}[result]


def evaluation_key(prediction_id: str, outcome_hash: str) -> str:
    return canonical_hash({
        "contract": EVALUATION_CONTRACT_VERSION,
        "prediction_id": prediction_id,
        "outcome_hash": outcome_hash,
    })

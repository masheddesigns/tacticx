"""Versioned MiroFish request/response contract (Phase 16).

Contract: ``mirofish_contract_v1``. Only explicitly whitelisted fields may
leave TacticX; the request is deterministic (canonical JSON, sorted keys)
so identical (match, cutoff, snapshot, scenario, contract) inputs hash
identically. Responses must echo the identity envelope or they are rejected.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List

from pydantic import BaseModel, Field

MIROFISH_CONTRACT_VERSION = "mirofish_contract_v1"

# Whitelisted top-level request fields. Anything else is dropped, never sent.
REQUEST_FIELDS = (
    "contract_version",
    "match_id",
    "competition",
    "kickoff",
    "cutoff",
    "home_team",
    "away_team",
    "core_prediction",
    "derived_probabilities",
    "expected_goals",
    "uncertainty",
    "model_disagreement",
    "data_completeness",
    "temporal_quality",
    "scenario",
    "provenance",
    "baseline_hashes",
)

# Whitelisted nested fields inside core_prediction / derived sections.
CORE_PREDICTION_FIELDS = ("home", "draw", "away")
GOALS_FIELDS = ("home_lambda", "away_lambda", "total_lambda")


class ScenarioDefinition(BaseModel):
    scenario_id: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    baseline_hash: str = ""
    scenario_hash: str = ""


class MiroFishRequest(BaseModel):
    contract_version: str = MIROFISH_CONTRACT_VERSION
    match_id: int = 0
    competition: str = ""
    kickoff: str = ""
    cutoff: str = ""
    home_team: Dict[str, Any] = Field(default_factory=dict)
    away_team: Dict[str, Any] = Field(default_factory=dict)
    core_prediction: Dict[str, float] = Field(default_factory=dict)
    derived_probabilities: Dict[str, Any] = Field(default_factory=dict)
    expected_goals: Dict[str, Any] = Field(default_factory=dict)
    uncertainty: Dict[str, Any] = Field(default_factory=dict)
    model_disagreement: Dict[str, Any] = Field(default_factory=dict)
    data_completeness: Dict[str, Any] = Field(default_factory=dict)
    temporal_quality: Dict[str, Any] = Field(default_factory=dict)
    scenario: ScenarioDefinition = Field(default_factory=ScenarioDefinition)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    baseline_hashes: Dict[str, str] = Field(default_factory=dict)


class MiroFishObservation(BaseModel):
    kind: str = ""  # e.g. "sensitivity", "divergence", "caveat"
    statement: str = ""
    detail: Dict[str, Any] = Field(default_factory=dict)


class MiroFishResponse(BaseModel):
    contract_version: str = ""
    match_id: int = 0
    cutoff: str = ""
    scenario_id: str = ""
    scenario_hash: str = ""
    baseline_prediction_hash: str = ""
    intelligence_snapshot_hash: str = ""
    provider: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    structured_observations: List[MiroFishObservation] = Field(default_factory=list)
    narrative: str = ""
    warnings: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)

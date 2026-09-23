"""Phase 29 research contracts: versions, states, hashing, comparison rules.

Research is evidence production only. No status, state, or result here
can promote a candidate; promotion is out of scope.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

RESEARCH_CONTRACT_VERSION = "RESEARCH_EXPERIMENT_V1"
EVALUATION_PROTOCOL = "cutoff_safe_walkforward"
EVALUATION_PROTOCOL_VERSION = "v1"

BASELINE_MODEL_ID = "ensemble_v1-elo+poisson"

# Candidate lifecycle (no PRODUCTION status exists by design).
STATUS_DRAFT = "DRAFT"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_INVALID = "INVALID_EXPERIMENT"
STATUS_SUPERSEDED = "SUPERSEDED"

# Leakage audit outcome.
LEAKAGE_PASS = "PASS"
LEAKAGE_INVALID = "INVALID_EXPERIMENT"

# Comparison evidence states (documented rules in comparison module).
EVIDENCE_IMPROVEMENT = "IMPROVEMENT_EVIDENCE"
EVIDENCE_NONE = "NO_CLEAR_DIFFERENCE"
EVIDENCE_REGRESSION = "REGRESSION_EVIDENCE"
EVIDENCE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

MIN_EVIDENCE_SAMPLE = 20

# Cutoff-safe input allowlist: candidate-declared tables must be within it.
CUTOFF_SAFE_TABLES = frozenset({
    "matches",
    "match_statistics",
    "teams",
    "leagues",
    "team_statistics",
    "standings",
})


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

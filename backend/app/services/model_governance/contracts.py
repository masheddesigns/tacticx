"""Phase 30 governance contracts: states, transitions, modes, config.

Research evidence does not itself authorize production activation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

GOVERNANCE_CONTRACT_VERSION = "MODEL_GOVERNANCE_V1"
VALIDATOR_VERSION = "governance_validator_v1"

# Lifecycle states.
RESEARCH_ONLY = "RESEARCH_ONLY"
VALIDATION_PENDING = "VALIDATION_PENDING"
VALIDATED = "VALIDATED"
CHALLENGER = "CHALLENGER"
PROMOTION_REQUESTED = "PROMOTION_REQUESTED"
APPROVAL_PENDING = "APPROVAL_PENDING"
APPROVED = "APPROVED"
SHADOW = "SHADOW"
CANARY_ELIGIBLE = "CANARY_ELIGIBLE"
PRODUCTION_ACTIVE = "PRODUCTION_ACTIVE"
REJECTED = "REJECTED"
WITHDRAWN = "WITHDRAWN"
ROLLED_BACK = "ROLLED_BACK"
SUPERSEDED = "SUPERSEDED"
INVALIDATED = "INVALIDATED"

ALLOWED_TRANSITIONS: Dict[str, tuple] = {
    RESEARCH_ONLY: (VALIDATION_PENDING, WITHDRAWN),
    VALIDATION_PENDING: (VALIDATED, REJECTED, INVALIDATED),
    VALIDATED: (CHALLENGER, SUPERSEDED, WITHDRAWN),
    CHALLENGER: (PROMOTION_REQUESTED, SUPERSEDED, WITHDRAWN),
    PROMOTION_REQUESTED: (APPROVAL_PENDING, APPROVED, REJECTED, WITHDRAWN),
    APPROVAL_PENDING: (APPROVED, REJECTED, WITHDRAWN),
    APPROVED: (SHADOW, WITHDRAWN),
    SHADOW: (CANARY_ELIGIBLE, WITHDRAWN, INVALIDATED),
    CANARY_ELIGIBLE: (PRODUCTION_ACTIVE, WITHDRAWN, INVALIDATED),
    PRODUCTION_ACTIVE: (ROLLED_BACK, SUPERSEDED),
    REJECTED: (),
    WITHDRAWN: (),
    ROLLED_BACK: (),
    # Rollback restoration only (enforced by deployment.rollback with an
    # explicit actor + target): a superseded prior champion may resume.
    SUPERSEDED: (PRODUCTION_ACTIVE,),
    INVALIDATED: (),
}

# Roles / modes / decisions.
ROLE_CHAMPION = "CHAMPION"
ROLE_CHALLENGER = "CHALLENGER"

DEPLOYMENT_SHADOW = "SHADOW"
DEPLOYMENT_CANARY = "CANARY"
DEPLOYMENT_PRODUCTION = "PRODUCTION"

DECISION_APPROVE = "APPROVE"
DECISION_REJECT = "REJECT"

# Validation results.
VALIDATION_VALIDATED = "VALIDATED"
VALIDATION_REJECTED = "REJECTED"
VALIDATION_INCONCLUSIVE = "INCONCLUSIVE"
VALIDATION_INVALID = "INVALID"

# Canary evidence rules (documented observational thresholds).
MIN_SHADOW_PAIRS = 10
REQUIRED_APPROVAL_COUNT = 1

# Production champion identity (seeded, never mutated).
CHAMPION_MODEL_ID = "ensemble_v1-elo+poisson"
CHAMPION_MODEL_VERSION = "ensemble_v1-elo+poisson"
CHAMPION_MEMBERS = ["elo", "poisson"]
CHAMPION_WEIGHTS = [0.5, 0.5]


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

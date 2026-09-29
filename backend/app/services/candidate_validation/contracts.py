"""Phase 34 validation contracts: states, versioned configuration.

Threshold rationale (documented; configurable; human sign-off required
before production use):
- min_paired_observations = 50: governance handoff outranks Phase 33
  inference (20); paired-bootstrap CIs on log-loss differences need
  practical width before a human review is worthwhile.
- max_exclusion_rate = 0.30: above this the paired set may no longer
  represent the cohort.
- max_temporal_violation_rate = 0.0: any contamination blocks (safety).
- allowed_evidence_states: SUPPORTED_DIFFERENCE, INCONCLUSIVE.
  The gate certifies completeness + integrity, not superiority; neutral
  evidence is reviewable, demonstrably-worse evidence is not promoted
  to review (INCONCLUSIVE), thin evidence is INSUFFICIENT_DATA.
- Calibration must be AVAILABLE (payloads exist when pairs >= 10).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

VALIDATION_CONTRACT_VERSION = "CANDIDATE_VALIDATION_V1"
CALCULATION_VERSION = "validation_calc_v1"

# Validation states.
STATE_PENDING = "PENDING"
STATE_BLOCKED = "BLOCKED"
STATE_INSUFFICIENT = "INSUFFICIENT_DATA"
STATE_INCONCLUSIVE = "INCONCLUSIVE"
STATE_VALIDATED = "VALIDATED_FOR_GOVERNANCE"
STATE_INVALID = "INVALID"

# Staleness states.
STALENESS_VALID = "VALID"
STALENESS_STALE = "STALE"
STALENESS_SUPERSEDED = "SUPERSEDED"

# Rule result states.
RULE_PASS = "PASS"
RULE_BLOCKED = "BLOCKED"
RULE_INSUFFICIENT = "INSUFFICIENT_DATA"
RULE_INCONCLUSIVE = "INCONCLUSIVE"
RULE_WARNING = "WARNING"

VALIDATION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "candidate_validation_v1": {
        "config_id": "candidate_validation_v1",
        "config_version": "v1",
        "min_paired_observations": 50,
        "min_evaluated_observations": 50,
        "max_exclusion_rate": 0.30,
        "max_temporal_violation_rate": 0.0,
        "required_evidence_states": ["SUPPORTED_DIFFERENCE", "INCONCLUSIVE"],
        "required_metrics": ["accuracy_1x2", "log_loss_1x2", "brier_1x2",
                             "goal_mae"],
        "uncertainty_method": "paired_bootstrap_seed7",
        "confidence_level": 95.0,
        "required_calibration": True,
        "required_data_quality": True,
        "required_competitions": [],
        "required_time_window": None,
        "required_shadow_coverage": True,
        "required_operational_health": True,
        "rationale": "conservative defaults; human/domain sign-off "
                     "required before production use",
    },
}

DEFAULT_CONFIG_ID = "candidate_validation_v1"


def get_config(config_id: str = DEFAULT_CONFIG_ID) -> Dict[str, Any]:
    if config_id not in VALIDATION_CONFIGS:
        raise ValueError(f"unknown validation config: {config_id!r}")
    return dict(VALIDATION_CONFIGS[config_id])


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

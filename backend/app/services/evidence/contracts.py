"""Phase 33 evidence contracts.

Phase 33 produces evidence; it does not make model-promotion decisions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

EVIDENCE_CONTRACT_VERSION = "REAL_WORLD_EVIDENCE_V1"
CALCULATION_VERSION = "evidence_calc_v1"
METRIC_DEFINITION_VERSION = "monitoring_metrics_v1"
BUCKET_DEFINITION_VERSION = "reliability_buckets_v1"
CALIBRATION_BINS = 10

# Evidence states (deterministic from data, never subjective).
STATE_NO_DATA = "NO_DATA"
STATE_INSUFFICIENT = "INSUFFICIENT_REAL_DATA"
STATE_DESCRIPTIVE = "DESCRIPTIVE_ONLY"
STATE_INCONCLUSIVE = "INCONCLUSIVE"
STATE_SUPPORTED = "SUPPORTED_DIFFERENCE"
STATE_CONFLICTING = "CONFLICTING_EVIDENCE"
STATE_INVALID = "INVALID"

# Sample policy (established convention: 20; documented + versioned).
MIN_PAIRED_EVIDENCE = 20
MIN_CALIBRATION_PAIRS = 10

# Uncertainty configuration (deterministic, versioned).
BOOTSTRAP_SEED = 7
BOOTSTRAP_RESAMPLES = 500
BOOTSTRAP_CONFIDENCE = 95.0


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

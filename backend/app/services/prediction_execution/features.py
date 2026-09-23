"""Phase 26 cutoff-safe feature snapshot builder.

Wraps the existing features_v1 builders (owned by the features layer) in a
deterministic, content-addressed envelope. This module adds no new feature
mathematics; every input derives from pre-cutoff records through
HistoricalFeatureRepository.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.services.features.availability import assess_availability
from app.services.features.engineered import build_feature_snapshot
from app.services.features.temporal import TemporalMode, as_naive_utc

from .contracts import (
    FEATURE_SNAPSHOT_VERSION,
    canonical_hash,
    normalize_cutoff_iso,
)


def build_cutoff_safe_snapshot(
    db: Session,
    match_id: int,
    cutoff: datetime,
    model_id: str,
    model_version: str,
) -> Dict[str, Any]:
    """Build the deterministic feature envelope for one (match, cutoff).

    Raises ValueError for unknown matches or unusable cutoffs. Never invents
    numbers; missing data is reported via availability envelopes.
    """
    naive = as_naive_utc(cutoff)
    if naive is None:
        raise ValueError("cutoff is required")
    cutoff_iso = normalize_cutoff_iso(cutoff)

    features = build_feature_snapshot(
        db, match_id, cutoff, TemporalMode.STRICT_PREMATCH)
    availability = assess_availability(db, match_id, cutoff,
                                       TemporalMode.STRICT_PREMATCH)

    envelope = {
        "match_id": match_id,
        "cutoff": cutoff_iso,
        "feature_version": FEATURE_SNAPSHOT_VERSION,
        "temporal_mode": TemporalMode.STRICT_PREMATCH.value,
        "model_id": model_id,
        "model_version": model_version,
        "features": features,
        "availability": availability.as_dict(),
        "provenance": {
            "builder": "prediction_execution.features",
            "feature_version": FEATURE_SNAPSHOT_VERSION,
            "cutoff_policy": "strict_prematch: only pre-cutoff records contribute",
            "as_of": cutoff_iso,
        },
    }
    snapshot_hash = canonical_hash(_hashable_envelope(envelope))
    return {
        "snapshot_id": f"fs_{match_id}_{snapshot_hash[:12]}",
        "snapshot_hash": snapshot_hash,
        "envelope": envelope,
    }


def _hashable_envelope(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Envelope minus nothing nondeterministic (no generated_at is stored here)."""
    return envelope


def feature_snapshot_provenance(snapshot_id: str, snapshot_hash: str,
                                cutoff_iso: str) -> Dict[str, Any]:
    return {
        "feature_snapshot_id": snapshot_id,
        "feature_snapshot_hash": snapshot_hash,
        "feature_version": FEATURE_SNAPSHOT_VERSION,
        "cutoff": cutoff_iso,
        "cutoff_policy": "strict_prematch: only pre-cutoff records contribute",
    }


def snapshot_nonce() -> str:
    """Uniqueness suffix for snapshot_id only — never part of any hash."""
    return uuid.uuid4().hex[:12]

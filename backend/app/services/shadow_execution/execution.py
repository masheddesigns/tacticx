"""Phase 32 shared-snapshot shadow execution.

Flow per match: readiness cert → champion Phase 26 snapshot (existing;
champion authoritative, never recomputed here) → resolve its
PredictionFeatureSnapshot row (shared input) → run challenger via the
research path → validate output → persist shadow row bound to the SAME
feature snapshot. Idempotent on shadow_execution_key.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.governance import ShadowPredictionSnapshot
from app.services.features.temporal import as_naive_utc
from app.services.model_governance.validation import check_compatibility
from app.services.prediction_execution.service import get_latest_certificate
from app.services.prediction_execution.store import (
    find_feature_snapshot,
    latest_prediction_for_match,
)
from app.services.prediction_execution.validation import (
    validate_prediction_output,
)

from .contracts import (
    SHADOW_INCOMPATIBLE,
    SHADOW_PAIR_INVALID,
    canonical_hash,
    shadow_execution_key,
)
from .eligibility import ShadowIneligible, check_challenger, check_match


class ShadowExecutionError(Exception):
    def __init__(self, reason: str, *, code: str = "SHADOW_EXECUTION_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def find_shadow(
    db: Session,
    execution_key_value: str,
) -> Optional[ShadowPredictionSnapshot]:
    return (db.query(ShadowPredictionSnapshot)
            .filter_by(shadow_execution_key=execution_key_value)
            .order_by(ShadowPredictionSnapshot.id.desc()).first())


def validate_shadow_pair(
    db: Session,
    shadow_id: str,
) -> Dict[str, Any]:
    """Verify a stored shadow pair shares match/kickoff/cutoff/mode and
    the exact feature snapshot of the champion prediction."""
    from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
    from app.db.models.prediction_snapshots import (
        PredictionFeatureSnapshot,
    )

    row = db.query(ShadowPredictionSnapshot).filter_by(
        shadow_id=shadow_id).first()
    if row is None:
        return {"valid": False, "code": SHADOW_PAIR_INVALID,
                "reason": f"unknown shadow: {shadow_id}"}
    match = db.get(Match, row.match_id)
    if match is None:
        return {"valid": False, "code": SHADOW_PAIR_INVALID,
                "reason": "match missing"}
    feature = db.query(PredictionFeatureSnapshot).filter_by(
        snapshot_id=row.feature_snapshot_id).first()
    if row.feature_snapshot_id is None or feature is None:
        return {"valid": False, "code": SHADOW_PAIR_INVALID,
                "reason": "shared feature snapshot not bound"}
    if feature.snapshot_hash != row.feature_snapshot_hash:
        return {"valid": False, "code": SHADOW_PAIR_INVALID,
                "reason": "feature snapshot hash mismatch"}
    if row.production_prediction_id is not None:
        prod = db.query(PreMatchPredictionSnapshot).filter_by(
            prediction_id=row.production_prediction_id).first()
        if prod is None or prod.feature_snapshot_hash != \
                row.feature_snapshot_hash:
            return {"valid": False, "code": SHADOW_PAIR_INVALID,
                    "reason": "champion prediction binding mismatch"}
    kickoff_ok = as_naive_utc(match.kickoff_at) is not None and \
        as_naive_utc(row.cutoff) is not None and \
        as_naive_utc(row.cutoff) < as_naive_utc(match.kickoff_at)
    if not kickoff_ok:
        return {"valid": False, "code": SHADOW_PAIR_INVALID,
                "reason": "cutoff not before kickoff"}
    return {"valid": True, "code": "SHADOW_PAIR_VALID",
            "match_id": row.match_id,
            "feature_snapshot_id": row.feature_snapshot_id,
            "feature_snapshot_hash": row.feature_snapshot_hash}


def execute_shadow(
    db: Session,
    match_id: int,
    challenger_artifact_id: str,
    *,
    champion_artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute one shadow prediction on the shared feature snapshot."""
    from app.services.model_governance.artifact import get_artifact
    from app.services.research import predict_with_candidate

    check_challenger(db, challenger_artifact_id)
    check_match(db, match_id)
    cert = get_latest_certificate(db, match_id)
    production = latest_prediction_for_match(db, match_id)
    if production is None:  # pragma: no cover - gated above
        raise ShadowExecutionError("no production prediction",
                                   code="NO_CHAMPION_PREDICTION")
    from app.services.prediction_execution.contracts import (
        normalize_cutoff_iso,
    )

    if normalize_cutoff_iso(production.cutoff_time) != \
            normalize_cutoff_iso(cert.cutoff):
        raise ShadowIneligible(
            "champion prediction cutoff does not match the latest "
            "readiness certificate; refusing to mix inputs",
            code="CERTIFICATE_CUTOFF_MISMATCH")

    feature = find_feature_snapshot(
        db, match_id, production.feature_snapshot_hash)
    if feature is None:
        raise ShadowExecutionError(
            "champion feature snapshot row missing; cannot share input",
            code="MISSING_FEATURE_SNAPSHOT")

    try:
        challenger_artifact = get_artifact(db, challenger_artifact_id)
    except Exception as exc:
        raise ShadowExecutionError(str(exc),
                                   code="UNKNOWN_CHALLENGER") from exc
    hyper = challenger_artifact.config_fingerprint or {}
    members = hyper.get("members") or []
    if not members:
        raise ShadowExecutionError(
            "challenger artifact has no model members",
            code="INVALID_CHALLENGER_CONFIG")
    cutoff = cert.cutoff
    try:
        challenger_out = predict_with_candidate(
            db, _candidate_view(challenger_artifact), match_id, cutoff)
    except Exception as exc:
        raise ShadowExecutionError(
            f"challenger execution failed: {exc}",
            code="CHALLENGER_EXECUTION_FAILED") from exc

    violations = validate_prediction_output(challenger_out)
    if violations:
        raise ShadowExecutionError(
            f"challenger output invalid: {violations}",
            code=SHADOW_INCOMPATIBLE)
    compat = check_compatibility(challenger_out)
    if not compat.get("compatible"):
        raise ShadowExecutionError(
            f"challenger output incompatible: {compat}",
            code=SHADOW_INCOMPATIBLE)

    from app.services.prediction_execution.contracts import (
        normalize_cutoff_iso,
    )

    cutoff_iso = normalize_cutoff_iso(cutoff)
    key = shadow_execution_key(
        match_id, challenger_artifact_id, feature.snapshot_hash, cutoff_iso)
    existing = find_shadow(db, key)
    if existing is not None:
        result = shadow_to_dict(existing)
        result["cache_hit"] = True
        return result

    champion_artifact = (
        champion_artifact_id
        or _champion_artifact_for_model(db, production.model_id))
    row = ShadowPredictionSnapshot(
        shadow_id=f"shdw_{uuid.uuid4().hex[:12]}",
        match_id=match_id,
        challenger_artifact_id=challenger_artifact_id,
        champion_artifact_id=champion_artifact,
        cutoff=cutoff,
        feature_snapshot_hash=feature.snapshot_hash,
        feature_snapshot_id=feature.snapshot_id,
        production_prediction_id=production.prediction_id,
        shadow_execution_key=key,
        evaluation_state="PENDING",
        champion_output=production.prediction_payload.get("prediction", {}),
        challenger_output=challenger_out,
        champion_output_hash=production.prediction_hash,
        challenger_output_hash=canonical_hash(challenger_out),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    result = shadow_to_dict(row)
    result["cache_hit"] = False
    return result


def _candidate_view(artifact):
    """Adapt a governance artifact to the research candidate surface."""

    class _View:
        def __init__(self, artifact):
            cfg = artifact.config_fingerprint or {}
            self.status = "DRAFT"
            self.declared_inputs = {"tables": ["matches"]}
            self.model_family = "ensemble" if artifact.model_id.startswith(
                "ensemble_v1") else artifact.model_id.split("_v1")[0]
            self.hyperparameters = {
                "members": cfg.get("members", []),
                "weights": cfg.get("weights", []),
            }

    return _View(artifact)


def _champion_artifact_for_model(db: Session, model_id: str) -> str:
    from app.services.model_governance.registry import current_champion

    try:
        return current_champion(db).artifact_id
    except Exception:
        return ""


def shadow_to_dict(row: ShadowPredictionSnapshot) -> Dict[str, Any]:
    return {
        "shadow_id": row.shadow_id,
        "match_id": row.match_id,
        "challenger_artifact_id": row.challenger_artifact_id,
        "champion_artifact_id": row.champion_artifact_id,
        "cutoff": row.cutoff.isoformat() if row.cutoff else None,
        "feature_snapshot_id": row.feature_snapshot_id,
        "feature_snapshot_hash": row.feature_snapshot_hash,
        "production_prediction_id": row.production_prediction_id,
        "shadow_execution_key": row.shadow_execution_key,
        "evaluation_state": row.evaluation_state,
        "champion_output_hash": row.champion_output_hash,
        "challenger_output_hash": row.challenger_output_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

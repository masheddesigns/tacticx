"""Phase 26 pre-match prediction execution service.

Flow: match -> readiness certificate -> cutoff -> config -> feature snapshot
-> production model -> output validation -> immutable persistence -> response.

BLOCKED readiness never yields a prediction. Failed output validation never
persists. Repeated identical execution returns the existing snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.prematch import PreMatchReadinessCertificate
from app.services.acquisition.readiness_gate import (
    DEFAULT_MODEL_ID,
    get_prediction_config,
)
from app.services.features.temporal import TemporalMode, as_naive_utc

from .contracts import (
    ELIGIBLE_READINESS,
    EXECUTION_CONTRACT_VERSION,
    PREDICTION_MODE,
    SUPPORTED_MODEL_IDS,
    canonical_hash,
    ensemble_members,
    execution_key,
    normalize_cutoff_iso,
)
from .features import build_cutoff_safe_snapshot, feature_snapshot_provenance
from .store import (
    find_prediction_by_execution_key,
    list_predictions_for_match,
    snapshot_to_dict,
    store_feature_snapshot,
    store_prediction_snapshot,
)
from .validation import validate_prediction_output


class PredictionBlocked(Exception):
    """Raised when execution is refused (readiness, cutoff, config, validation)."""

    def __init__(self, reason: str, *, code: str = "BLOCKED",
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.details = details or {}


def get_latest_certificate(db: Session,
                           match_id: int) -> Optional[PreMatchReadinessCertificate]:
    return (
        db.query(PreMatchReadinessCertificate)
        .filter_by(match_id=match_id)
        .order_by(PreMatchReadinessCertificate.id.desc())
        .first()
    )


def resolve_certificate(db: Session, match_id: int,
                        cutoff_iso: str,
                        certificate_id: Optional[str] = None
                        ) -> PreMatchReadinessCertificate:
    """Bind execution to the exact latest readiness certificate for the match.

    Rules:
    - An explicitly requested certificate must exist, belong to the match,
      and be the latest certificate for that match (superseded certs refuse).
    - Without an explicit id, the latest certificate for the match is used.
    - The certificate cutoff must equal the requested execution cutoff.
    - The certificate readiness state must be PREDICTION_READY or READY_DEGRADED.
    """
    if certificate_id is not None:
        cert = (
            db.query(PreMatchReadinessCertificate)
            .filter_by(certificate_id=certificate_id)
            .first()
        )
        if cert is None:
            raise PredictionBlocked(
                f"readiness certificate not found: {certificate_id}",
                code="CERTIFICATE_NOT_FOUND")
        if cert.match_id != match_id:
            raise PredictionBlocked(
                "readiness certificate belongs to a different match",
                code="CERTIFICATE_MATCH_MISMATCH")
    else:
        cert = get_latest_certificate(db, match_id)
        if cert is None:
            raise PredictionBlocked(
                "no readiness certificate exists for this match; "
                "evaluate Phase 25.1 readiness first",
                code="CERTIFICATE_MISSING")

    latest = get_latest_certificate(db, match_id)
    if latest is not None and latest.certificate_id != cert.certificate_id:
        raise PredictionBlocked(
            "readiness certificate is superseded by a newer evaluation; "
            "use the latest certificate",
            code="CERTIFICATE_SUPERSEDED",
            details={"latest_certificate_id": latest.certificate_id})

    cert_cutoff_iso = normalize_cutoff_iso(cert.cutoff)
    if cert_cutoff_iso != cutoff_iso:
        raise PredictionBlocked(
            f"certificate cutoff {cert_cutoff_iso} does not match "
            f"execution cutoff {cutoff_iso}",
            code="CERTIFICATE_CUTOFF_MISMATCH")

    if cert.readiness_state not in ELIGIBLE_READINESS:
        raise PredictionBlocked(
            f"readiness state {cert.readiness_state} is not eligible "
            "for prediction",
            code="READINESS_BLOCKED",
            details={"readiness_state": cert.readiness_state,
                     "blocking_reasons": list(cert.blocking_reasons or [])})
    return cert


def execute_pre_match_prediction(
    db: Session,
    match_id: int,
    cutoff: datetime,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    certificate_id: Optional[str] = None,
    with_intelligence: bool = False,
) -> Dict[str, Any]:
    """Execute one cutoff-safe pre-match prediction and persist the snapshot."""
    match = db.get(Match, match_id)
    if match is None:
        raise PredictionBlocked(f"unknown match: {match_id}",
                                code="UNKNOWN_MATCH")
    if match.home_team_id is None or match.away_team_id is None:
        raise PredictionBlocked("match teams are not set",
                                code="INVALID_MATCH_TEAMS")
    if match.kickoff_at is None:
        raise PredictionBlocked("match kickoff is not set",
                                code="INVALID_MATCH_KICKOFF")

    naive_cutoff = as_naive_utc(cutoff)
    if naive_cutoff is None:
        raise PredictionBlocked("cutoff is required", code="INVALID_CUTOFF")
    naive_kickoff = as_naive_utc(match.kickoff_at)
    if naive_cutoff >= naive_kickoff:
        raise PredictionBlocked(
            "PRE_MATCH cutoff must be strictly before kickoff",
            code="CUTOFF_AT_OR_AFTER_KICKOFF")

    if model_id not in SUPPORTED_MODEL_IDS:
        raise PredictionBlocked(
            f"unsupported model_id for Phase 26 execution: {model_id}",
            code="UNSUPPORTED_MODEL")
    try:
        config = get_prediction_config(model_id)
    except (KeyError, ValueError) as exc:
        raise PredictionBlocked(f"unknown prediction config: {model_id}",
                                code="UNKNOWN_CONFIG") from exc
    member_names = ensemble_members(model_id)

    cutoff_iso = normalize_cutoff_iso(cutoff)
    cert = resolve_certificate(db, match_id, cutoff_iso, certificate_id)

    # Feature snapshot (cutoff-safe by construction).
    built = build_cutoff_safe_snapshot(
        db, match_id, cutoff, model_id, config.model_version)
    feature_row = store_feature_snapshot(
        db, match_id, cutoff, model_id, config.model_version,
        built["envelope"], built["snapshot_hash"])

    key = execution_key(match_id, cutoff_iso, model_id,
                        config.model_version, built["snapshot_hash"])
    existing = find_prediction_by_execution_key(db, key)
    if existing is not None:
        result = snapshot_to_dict(existing)
        result["cache_hit"] = True
        if with_intelligence:
            result["match_intelligence"] = _attached_intelligence(
                db, match_id, cutoff)
        return result

    # Production model execution (existing promoted model, unmodified).
    from app.services.predictions.ensemble import EnsembleModel

    model = EnsembleModel.from_names(member_names)
    full = model.predict(db, match_id, cutoff, TemporalMode.STRICT_PREMATCH)
    payload = full.model_dump(mode="json")

    violations = validate_prediction_output(payload)
    if violations:
        raise PredictionBlocked(
            "model output failed validation; nothing persisted",
            code="OUTPUT_VALIDATION_FAILED", details={"violations": violations})

    prediction_payload = {
        "contract": EXECUTION_CONTRACT_VERSION,
        "match_id": match_id,
        "cutoff": cutoff_iso,
        "model_id": model_id,
        "model_version": config.model_version,
        "prediction_mode": PREDICTION_MODE,
        "feature_snapshot_hash": built["snapshot_hash"],
        "readiness_certificate_id": cert.certificate_id,
        "readiness_certificate_hash": cert.payload_hash,
        "readiness_state": cert.readiness_state,
        "prediction": payload,
    }
    pred_hash = canonical_hash(prediction_payload)

    provenance = {
        "contract": EXECUTION_CONTRACT_VERSION,
        "model_id": model_id,
        "model_version": config.model_version,
        "prediction_mode": PREDICTION_MODE,
        "cutoff": cutoff_iso,
        "cutoff_policy": "strict_prematch: only pre-cutoff records contribute",
        "feature_snapshot": feature_snapshot_provenance(
            feature_row.snapshot_id, built["snapshot_hash"], cutoff_iso),
        "readiness": {
            "certificate_id": cert.certificate_id,
            "certificate_hash": cert.payload_hash,
            "readiness_state": cert.readiness_state,
            "contract_version": cert.readiness_contract_version,
        },
        "executed_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
    }

    row = store_prediction_snapshot(
        db,
        match_id=match_id,
        model_id=model_id,
        model_version=config.model_version,
        cutoff_time=cutoff,
        kickoff_time=match.kickoff_at,
        readiness_certificate_id=cert.certificate_id,
        readiness_certificate_hash=cert.payload_hash,
        readiness_state=cert.readiness_state,
        feature_snapshot_id=feature_row.snapshot_id,
        feature_snapshot_hash=built["snapshot_hash"],
        prediction_payload=prediction_payload,
        prediction_hash=pred_hash,
        execution_key_value=key,
        provenance=provenance,
    )
    result = snapshot_to_dict(row)
    result["cache_hit"] = False
    if with_intelligence:
        result["match_intelligence"] = _attached_intelligence(
            db, match_id, cutoff)
    return result


def _attached_intelligence(db: Session, match_id: int,
                           cutoff: datetime) -> Dict[str, Any]:
    """Read-only intelligence document for the same cutoff (no recompute here)."""
    from app.services.match_intelligence.service import (
        build_match_intelligence,
    )

    return build_match_intelligence(
        db, match_id, cutoff, TemporalMode.STRICT_PREMATCH,
        response_mode="standard", with_mirofish=False)


def get_prediction(db: Session, prediction_id: str) -> Dict[str, Any]:
    from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

    row = (
        db.query(PreMatchPredictionSnapshot)
        .filter_by(prediction_id=prediction_id)
        .first()
    )
    if row is None:
        raise PredictionBlocked(f"unknown prediction: {prediction_id}",
                                code="UNKNOWN_PREDICTION")
    return snapshot_to_dict(row)


def describe_match_predictions(db: Session, match_id: int) -> Dict[str, Any]:
    """Execution status for a match: not generated / generated / degraded / blocked."""
    match = db.get(Match, match_id)
    if match is None:
        raise PredictionBlocked(f"unknown match: {match_id}",
                                code="UNKNOWN_MATCH")
    snapshots = list_predictions_for_match(db, match_id)
    cert = get_latest_certificate(db, match_id)
    latest = snapshots[0] if snapshots else None
    if latest is None and cert is None:
        status = "NOT_GENERATED"
    elif latest is None:
        status = "BLOCKED" if cert.readiness_state == "BLOCKED" else "NOT_GENERATED"
    elif latest.readiness_state == "READY_DEGRADED":
        status = "DEGRADED"
    else:
        status = "GENERATED"
    return {
        "match_id": match_id,
        "status": status,
        "prediction_count": len(snapshots),
        "latest": snapshot_to_dict(latest) if latest else None,
        "latest_certificate_id": cert.certificate_id if cert else None,
        "latest_readiness_state": cert.readiness_state if cert else None,
    }

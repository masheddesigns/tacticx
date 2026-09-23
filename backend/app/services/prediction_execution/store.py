"""Phase 26 snapshot persistence + idempotency lookups."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.prediction_snapshots import (
    PredictionFeatureSnapshot,
    PreMatchPredictionSnapshot,
)

from .contracts import normalize_cutoff_iso
from .features import snapshot_nonce


def find_feature_snapshot(db: Session, match_id: int,
                          snapshot_hash: str) -> Optional[PredictionFeatureSnapshot]:
    return (
        db.query(PredictionFeatureSnapshot)
        .filter_by(match_id=match_id, snapshot_hash=snapshot_hash)
        .order_by(PredictionFeatureSnapshot.id.desc())
        .first()
    )


def store_feature_snapshot(db: Session, match_id: int, cutoff: datetime,
                           model_id: str, model_version: str,
                           envelope: Dict[str, Any],
                           snapshot_hash: str) -> PredictionFeatureSnapshot:
    existing = find_feature_snapshot(db, match_id, snapshot_hash)
    if existing is not None:
        return existing
    row = PredictionFeatureSnapshot(
        snapshot_id=f"fs_{match_id}_{snapshot_nonce()}",
        match_id=match_id,
        cutoff=cutoff,
        feature_version=envelope.get("feature_version", "features_v1"),
        model_id=model_id,
        model_version=model_version,
        features=envelope.get("features", {}),
        provenance=envelope.get("provenance", {}),
        snapshot_hash=snapshot_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def find_prediction_by_execution_key(
        db: Session, execution_key: str) -> Optional[PreMatchPredictionSnapshot]:
    return (
        db.query(PreMatchPredictionSnapshot)
        .filter_by(execution_key=execution_key)
        .order_by(PreMatchPredictionSnapshot.id.desc())
        .first()
    )


def latest_prediction_for_match(db: Session,
                                match_id: int) -> Optional[PreMatchPredictionSnapshot]:
    return (
        db.query(PreMatchPredictionSnapshot)
        .filter_by(match_id=match_id)
        .order_by(PreMatchPredictionSnapshot.id.desc())
        .first()
    )


def list_predictions_for_match(db: Session, match_id: int,
                               limit: int = 50):
    return (
        db.query(PreMatchPredictionSnapshot)
        .filter_by(match_id=match_id)
        .order_by(PreMatchPredictionSnapshot.id.desc())
        .limit(limit)
        .all()
    )


def store_prediction_snapshot(
    db: Session,
    *,
    match_id: int,
    model_id: str,
    model_version: str,
    cutoff_time: datetime,
    kickoff_time: datetime,
    readiness_certificate_id: str,
    readiness_certificate_hash: str,
    readiness_state: str,
    feature_snapshot_id: str,
    feature_snapshot_hash: str,
    prediction_payload: Dict[str, Any],
    prediction_hash: str,
    execution_key_value: str,
    provenance: Dict[str, Any],
) -> PreMatchPredictionSnapshot:
    existing = find_prediction_by_execution_key(db, execution_key_value)
    if existing is not None:
        return existing
    latest = latest_prediction_for_match(db, match_id)
    version = (latest.prediction_version + 1) if latest is not None else 1
    row = PreMatchPredictionSnapshot(
        prediction_id=f"pred_{match_id}_{snapshot_nonce()}",
        match_id=match_id,
        prediction_version=version,
        model_id=model_id,
        model_version=model_version,
        prediction_mode="PRE_MATCH",
        cutoff_time=cutoff_time,
        kickoff_time=kickoff_time,
        readiness_certificate_id=readiness_certificate_id,
        readiness_certificate_hash=readiness_certificate_hash,
        readiness_state=readiness_state,
        feature_snapshot_id=feature_snapshot_id,
        feature_snapshot_hash=feature_snapshot_hash,
        prediction_payload=prediction_payload,
        prediction_hash=prediction_hash,
        execution_key=execution_key_value,
        provenance=provenance,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def snapshot_to_dict(row: PreMatchPredictionSnapshot) -> Dict[str, Any]:
    cutoff = row.cutoff_time
    kickoff = row.kickoff_time
    return {
        "prediction_id": row.prediction_id,
        "match_id": row.match_id,
        "prediction_version": row.prediction_version,
        "model_id": row.model_id,
        "model_version": row.model_version,
        "prediction_mode": row.prediction_mode,
        "cutoff_time": cutoff.isoformat() if cutoff is not None else None,
        "kickoff_time": kickoff.isoformat() if kickoff is not None else None,
        "readiness_certificate_id": row.readiness_certificate_id,
        "readiness_certificate_hash": row.readiness_certificate_hash,
        "readiness_state": row.readiness_state,
        "feature_snapshot_id": row.feature_snapshot_id,
        "feature_snapshot_hash": row.feature_snapshot_hash,
        "prediction_payload": row.prediction_payload,
        "prediction_hash": row.prediction_hash,
        "execution_key": row.execution_key,
        "provenance": row.provenance,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def feature_snapshot_to_dict(row: PredictionFeatureSnapshot) -> Dict[str, Any]:
    return {
        "snapshot_id": row.snapshot_id,
        "match_id": row.match_id,
        "cutoff": row.cutoff.isoformat() if row.cutoff else None,
        "feature_version": row.feature_version,
        "model_id": row.model_id,
        "model_version": row.model_version,
        "snapshot_hash": row.snapshot_hash,
        "provenance": row.provenance,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def cutoff_iso(value: Any) -> str:
    return normalize_cutoff_iso(value)

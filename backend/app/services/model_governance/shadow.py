"""Phase 30 shadow evaluation: isolated challenger outputs.

A SHADOW challenger never touches production snapshots, intelligence, or
user-visible predictions. Outputs land in shadow_prediction_snapshots
only, scored with Phase 27 metric definitions for factual comparison.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.governance import ShadowPredictionSnapshot
from app.services.features.temporal import TemporalMode, as_naive_utc
from app.services.prediction_evaluation.metrics import score_snapshot

from .artifact import get_artifact
from .contracts import (
    APPROVED,
    SHADOW,
    canonical_hash,
)
from .lifecycle import transition


class ShadowError(Exception):
    def __init__(self, reason: str, *, code: str = "SHADOW_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def start_shadow(
    db: Session,
    challenger_artifact_id: str,
    champion_artifact_id: str,
    *,
    actor: str = "",
) -> Dict[str, Any]:
    """Move an APPROVED artifact into SHADOW (explicit operation)."""
    challenger = get_artifact(db, challenger_artifact_id)
    get_artifact(db, champion_artifact_id)
    if challenger.lifecycle_state != APPROVED:
        raise ShadowError(
            f"artifact state {challenger.lifecycle_state} cannot start "
            "shadow; explicit approval required first",
            code="INVALID_ARTIFACT_STATE")
    transition(db, challenger, SHADOW, actor=actor or "system",
               reason="shadow evaluation started",
               references={"champion_artifact_id": champion_artifact_id})
    return {"challenger_artifact_id": challenger_artifact_id,
            "champion_artifact_id": champion_artifact_id,
            "state": SHADOW}


def _run_model(db: Session, model_id: str, members: List[str],
               weights: List[float], match_id: int,
               cutoff: datetime) -> Dict[str, Any]:
    from app.services.predictions.ensemble import EnsembleModel

    model = EnsembleModel.from_names(list(members),
                                     list(weights) if weights else None)
    full = model.predict(db, match_id, cutoff, TemporalMode.STRICT_PREMATCH)
    return full.model_dump(mode="json")


def run_shadow_pair(
    db: Session,
    *,
    challenger_artifact_id: str,
    champion_artifact_id: str,
    match_id: int,
    cutoff: datetime,
) -> Dict[str, Any]:
    """Produce one isolated champion/challenger output pair (no prod writes)."""
    challenger = get_artifact(db, challenger_artifact_id)
    champion = get_artifact(db, champion_artifact_id)
    if challenger.lifecycle_state != SHADOW:
        raise ShadowError("challenger is not in SHADOW state",
                          code="INVALID_ARTIFACT_STATE")
    match = db.get(Match, match_id)
    if match is None:
        raise ShadowError(f"unknown match: {match_id}",
                          code="UNKNOWN_MATCH")

    champ_cfg = champion.config_fingerprint or {}
    chal_cfg = challenger.config_fingerprint or {}
    champion_out = _run_model(
        db, champion.model_id, champ_cfg.get("members", ["elo", "poisson"]),
        champ_cfg.get("weights", [0.5, 0.5]), match_id, cutoff)
    challenger_out = _run_model(
        db, challenger.model_id, chal_cfg.get("members", ["elo", "poisson"]),
        chal_cfg.get("weights", [0.5, 0.5]), match_id, cutoff)
    if champion_out.get("status") != "valid" \
            or challenger_out.get("status") != "valid":
        raise ShadowError("shadow model output is not valid",
                          code="INVALID_SHADOW_OUTPUT")

    naive_cutoff = as_naive_utc(cutoff)
    feature_hash = canonical_hash({
        "match_id": match_id,
        "cutoff": naive_cutoff.replace(microsecond=0).isoformat()
        if naive_cutoff else str(cutoff),
        "feature_contract": "features_v1"})
    row = ShadowPredictionSnapshot(
        shadow_id=f"shdw_{uuid.uuid4().hex[:12]}",
        match_id=match_id,
        challenger_artifact_id=challenger_artifact_id,
        champion_artifact_id=champion_artifact_id,
        cutoff=cutoff,
        feature_snapshot_hash=feature_hash,
        champion_output=champion_out,
        challenger_output=challenger_out,
        champion_output_hash=canonical_hash(champion_out),
        challenger_output_hash=canonical_hash(challenger_out),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return shadow_to_dict(row)


def shadow_pairs(db: Session, challenger_artifact_id: str,
                 limit: int = 500) -> List[ShadowPredictionSnapshot]:
    return (db.query(ShadowPredictionSnapshot)
            .filter_by(challenger_artifact_id=challenger_artifact_id)
            .order_by(ShadowPredictionSnapshot.id.asc())
            .limit(limit).all())


def evaluate_shadow(db: Session,
                    challenger_artifact_id: str) -> Dict[str, Any]:
    """Score shadow pairs with verified outcomes (factual diffs only)."""
    pairs = shadow_pairs(db, challenger_artifact_id)
    scored = 0
    champ_acc = champ_ll = champ_br = 0.0
    chal_acc = chal_ll = chal_br = 0.0
    for pair in pairs:
        match = db.get(Match, pair.match_id)
        if match is None or match.status != "FINISHED" \
                or match.home_score is None or match.away_score is None:
            continue
        champ_m = score_snapshot(pair.champion_output, match.home_score,
                                 match.away_score)
        chal_m = score_snapshot(pair.challenger_output, match.home_score,
                                match.away_score)
        scored += 1
        champ_acc += champ_m.get("accuracy_1x2", 0)
        champ_ll += champ_m.get("log_loss_1x2", 0.0)
        champ_br += champ_m.get("brier_1x2", 0.0)
        chal_acc += chal_m.get("accuracy_1x2", 0)
        chal_ll += chal_m.get("log_loss_1x2", 0.0)
        chal_br += chal_m.get("brier_1x2", 0.0)

    def avg(total: float) -> Optional[float]:
        return round(total / scored, 6) if scored else None

    return {
        "challenger_artifact_id": challenger_artifact_id,
        "shadow_pairs": len(pairs),
        "scored_pairs": scored,
        "champion": {"accuracy_1x2": avg(champ_acc),
                     "log_loss_1x2": avg(champ_ll),
                     "brier_1x2": avg(champ_br)},
        "challenger": {"accuracy_1x2": avg(chal_acc),
                       "log_loss_1x2": avg(chal_ll),
                       "brier_1x2": avg(chal_br)},
        "differences_challenger_minus_champion": {
            "accuracy_1x2": (round(chal_acc / scored - champ_acc / scored, 6)
                             if scored else None),
            "log_loss_1x2": (round(chal_ll / scored - champ_ll / scored, 6)
                             if scored else None),
            "brier_1x2": (round(chal_br / scored - champ_br / scored, 6)
                          if scored else None),
        },
        "note": "factual differences only; no winner declaration",
    }


def shadow_to_dict(row: ShadowPredictionSnapshot) -> Dict[str, Any]:
    return {
        "shadow_id": row.shadow_id,
        "match_id": row.match_id,
        "challenger_artifact_id": row.challenger_artifact_id,
        "champion_artifact_id": row.champion_artifact_id,
        "cutoff": row.cutoff.isoformat() if row.cutoff else None,
        "feature_snapshot_hash": row.feature_snapshot_hash,
        "champion_output_hash": row.champion_output_hash,
        "challenger_output_hash": row.challenger_output_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

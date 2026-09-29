"""Phase 32 shadow eligibility (challenger + match gates)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.services.features.temporal import as_naive_utc
from app.services.model_governance.artifact import get_artifact
from app.services.model_governance.lifecycle import GovernanceError
from app.services.prediction_execution.service import get_latest_certificate
from app.services.prediction_execution.contracts import ELIGIBLE_READINESS


class ShadowIneligible(Exception):
    def __init__(self, reason: str, *, code: str = "SHADOW_INELIGIBLE"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def check_challenger(
    db: Session,
    challenger_artifact_id: str,
) -> Dict[str, Any]:
    """Verify challenger artifact may run in shadow (read-only)."""
    try:
        artifact = get_artifact(db, challenger_artifact_id)
    except GovernanceError as exc:
        raise ShadowIneligible(exc.reason, code="UNKNOWN_CHALLENGER") from exc
    if artifact.lifecycle_state != "SHADOW":
        raise ShadowIneligible(
            f"challenger state {artifact.lifecycle_state} does not permit "
            "shadow execution (move to SHADOW via governance first)",
            code="INVALID_CHALLENGER_STATE")
    return {"artifact_id": artifact.artifact_id,
            "model_id": artifact.model_id,
            "model_version": artifact.model_version,
            "config_fingerprint": artifact.config_fingerprint}


def check_match(
    db: Session,
    match_id: int,
    *,
    require_production_prediction: bool = True,
) -> Dict[str, Any]:
    """Verify a real match is shadow-eligible (read-only)."""
    from app.services.prediction_execution.store import (
        latest_prediction_for_match,
    )

    match = db.get(Match, match_id)
    if match is None:
        raise ShadowIneligible(f"unknown match: {match_id}",
                               code="UNKNOWN_MATCH")
    if match.status not in ("SCHEDULED", "PRE_MATCH"):
        raise ShadowIneligible(
            f"match status {match.status!r} is not shadow-eligible",
            code="MATCH_NOT_UPCOMING")
    if match.kickoff_at is None:
        raise ShadowIneligible("match kickoff is not set",
                               code="MISSING_KICKOFF")
    cert = get_latest_certificate(db, match_id)
    if cert is None:
        raise ShadowIneligible("no readiness certificate for match",
                               code="NO_READINESS")
    if cert.readiness_state not in ELIGIBLE_READINESS:
        raise ShadowIneligible(
            f"readiness {cert.readiness_state} blocks shadow execution",
            code="READINESS_BLOCKED")
    naive_cutoff = as_naive_utc(cert.cutoff)
    naive_kickoff = as_naive_utc(match.kickoff_at)
    if naive_cutoff is None or naive_kickoff is None \
            or not naive_cutoff < naive_kickoff:
        raise ShadowIneligible("certificate cutoff is not before kickoff",
                               code="CUTOFF_VIOLATION")
    production = latest_prediction_for_match(db, match_id)
    if require_production_prediction and production is None:
        raise ShadowIneligible(
            "no production prediction yet; shadow waits for champion",
            code="NO_CHAMPION_PREDICTION")
    return {"match_id": match_id,
            "certificate_id": cert.certificate_id,
            "cutoff": cert.cutoff,
            "kickoff": match.kickoff_at,
            "production_prediction_id": (
                production.prediction_id if production else None)}


def find_eligible_matches(
    db: Session,
    *,
    competition: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Scan real upcoming matches for shadow eligibility (read-only)."""
    query = db.query(Match).filter(
        Match.status.in_(("SCHEDULED", "PRE_MATCH")))
    if competition:
        query = query.join(League, Match.league_id == League.id).filter(
            League.code == competition)
    candidates = query.order_by(Match.kickoff_at.asc()).limit(limit).all()
    eligible: List[int] = []
    skipped: List[Dict[str, Any]] = []
    for match in candidates:
        try:
            check_match(db, match.id)
            eligible.append(match.id)
        except ShadowIneligible as exc:
            skipped.append({"match_id": match.id, "code": exc.code})
    if not eligible:
        return {"state": "NO_ELIGIBLE_MATCHES", "eligible": [],
                "skipped": skipped,
                "reason": "no eligible real fixtures"}
    return {"state": "ELIGIBLE", "eligible": eligible, "skipped": skipped}

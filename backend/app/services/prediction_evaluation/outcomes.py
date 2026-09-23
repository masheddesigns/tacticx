"""Phase 27 canonical outcome snapshots.

Verified := status FINISHED with recorded home/away scores. There is no
separate verification flag in the schema; a canonical FINISHED result is
the verified outcome. Anything else refuses with a machine-readable code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.evaluation_records import MatchOutcomeSnapshot

from .contracts import (
    ELIGIBLE_STATUS,
    OUTCOME_CONTRACT_VERSION,
    canonical_hash,
    result_from_goals,
)


class OutcomeNotReady(Exception):
    """Raised when a match has no evaluable canonical result."""

    def __init__(self, reason: str, *, code: str = "OUTCOME_NOT_READY"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def outcome_eligibility(db: Session, match_id: int) -> Dict[str, Any]:
    """Inspect a match without writing. eligible + reason/code either way."""
    match = db.get(Match, match_id)
    if match is None:
        return {"eligible": False, "code": "UNKNOWN_MATCH",
                "reason": f"unknown match: {match_id}"}
    if match.status not in ELIGIBLE_STATUS:
        return {"eligible": False, "code": "MATCH_NOT_FINISHED",
                "reason": f"match status {match.status!r} is not evaluable",
                "status": match.status}
    if match.home_score is None or match.away_score is None:
        return {"eligible": False, "code": "RESULT_SCORES_MISSING",
                "reason": "finished match has no recorded scores"}
    return {"eligible": True, "code": "ELIGIBLE", "reason": "",
            "status": match.status,
            "home_score": match.home_score, "away_score": match.away_score}


def _payload(match: Match) -> Dict[str, Any]:
    result = result_from_goals(match.home_score, match.away_score)
    return {
        "contract": OUTCOME_CONTRACT_VERSION,
        "match_id": match.id,
        "final_home_goals": match.home_score,
        "final_away_goals": match.away_score,
        "final_result": result,
        "status": match.status,
        "provider": match.provider or "",
        "provider_match_id": match.provider_match_id or "",
    }


def latest_outcome(db: Session, match_id: int) -> Optional[MatchOutcomeSnapshot]:
    return (
        db.query(MatchOutcomeSnapshot)
        .filter_by(match_id=match_id)
        .order_by(MatchOutcomeSnapshot.id.desc())
        .first()
    )


def capture_outcome_snapshot(db: Session, match_id: int) -> MatchOutcomeSnapshot:
    """Capture (or reuse) the canonical outcome snapshot for a match."""
    check = outcome_eligibility(db, match_id)
    if not check["eligible"]:
        raise OutcomeNotReady(check["reason"], code=check["code"])
    match = db.get(Match, match_id)
    payload = _payload(match)
    outcome_hash = canonical_hash(payload)
    existing = (
        db.query(MatchOutcomeSnapshot)
        .filter_by(match_id=match_id, outcome_hash=outcome_hash)
        .order_by(MatchOutcomeSnapshot.id.desc())
        .first()
    )
    if existing is not None:
        return existing
    latest = latest_outcome(db, match_id)
    import uuid

    row = MatchOutcomeSnapshot(
        outcome_id=f"out_{match_id}_{uuid.uuid4().hex[:12]}",
        match_id=match_id,
        final_home_goals=match.home_score,
        final_away_goals=match.away_score,
        final_result=payload["final_result"],
        status=match.status,
        outcome_timestamp=match.updated_at,
        provider=match.provider or None,
        provider_match_id=match.provider_match_id or None,
        provenance={
            "contract": OUTCOME_CONTRACT_VERSION,
            "source": "canonical match result",
            "verified": "FINISHED with recorded scores",
            "captured_at": datetime.now(timezone.utc).replace(
                microsecond=0).isoformat(),
        },
        outcome_hash=outcome_hash,
        supersedes_outcome_id=(
            latest.outcome_id if latest is not None else None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def outcome_to_dict(row: MatchOutcomeSnapshot) -> Dict[str, Any]:
    return {
        "outcome_id": row.outcome_id,
        "match_id": row.match_id,
        "final_home_goals": row.final_home_goals,
        "final_away_goals": row.final_away_goals,
        "final_result": row.final_result,
        "status": row.status,
        "outcome_timestamp": row.outcome_timestamp.isoformat()
        if row.outcome_timestamp else None,
        "provider": row.provider,
        "provider_match_id": row.provider_match_id,
        "provenance": row.provenance,
        "outcome_hash": row.outcome_hash,
        "supersedes_outcome_id": row.supersedes_outcome_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

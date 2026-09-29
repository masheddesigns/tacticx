"""Phase 33 evidence cohorts: deterministic population definitions."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceCohort

from .contracts import canonical_hash


class CohortError(Exception):
    def __init__(self, reason: str, *, code: str = "COHORT_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def build_cohort(
    db: Session,
    *,
    champion_artifact_id: Optional[str] = None,
    challenger_artifact_id: Optional[str] = None,
    competitions: Optional[List[str]] = None,
    seasons: Optional[List[str]] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    prediction_mode: str = "PRE_MATCH",
    persist: bool = True,
):
    """Define (or reuse by hash) an evidence cohort.

    persist=False returns an ephemeral cohort view for read-only
    computation without writing rows.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise CohortError("date_from must not exceed date_to",
                          code="INVALID_DATE_RANGE")
    fingerprint = {
        "champion_artifact_id": champion_artifact_id or "",
        "challenger_artifact_id": challenger_artifact_id or "",
        "competitions": sorted(competitions or []),
        "seasons": sorted(seasons or []),
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "prediction_mode": prediction_mode,
    }
    cohort_hash = canonical_hash({
        "contract": "EVIDENCE_COHORT_V1", **fingerprint})
    existing = db.query(EvidenceCohort).filter_by(
        cohort_hash=cohort_hash).first()
    if existing is not None:
        return existing
    if not persist:
        return _ephemeral_cohort(
            champion_artifact_id=champion_artifact_id,
            challenger_artifact_id=challenger_artifact_id,
            competitions=competitions, seasons=seasons,
            date_from=date_from, date_to=date_to,
            prediction_mode=prediction_mode, fingerprint=fingerprint,
            cohort_hash=cohort_hash)
    row = EvidenceCohort(
        cohort_id=f"coh_{uuid.uuid4().hex[:12]}",
        champion_artifact_id=champion_artifact_id,
        challenger_artifact_id=challenger_artifact_id,
        competitions={"values": sorted(competitions or [])},
        seasons={"values": sorted(seasons or [])},
        date_from=date_from,
        date_to=date_to,
        prediction_mode=prediction_mode,
        min_completeness=1.0,
        query_fingerprint=fingerprint,
        cohort_hash=cohort_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ephemeral_cohort(**fields):
    """Non-persisted cohort view for read-only computation."""

    class _Ephemeral:
        def __init__(self, fields):
            self.cohort_id = f"ephemeral-{fields['cohort_hash'][:12]}"
            for key, value in fields.items():
                if key == "cohort_hash":
                    continue
                setattr(self, key, value)
            self.cohort_hash = fields["cohort_hash"]
            self.min_completeness = 1.0
            self.created_at = None

    return _Ephemeral({
        "champion_artifact_id": fields.get("champion_artifact_id"),
        "challenger_artifact_id": fields.get("challenger_artifact_id"),
        "competitions": {"values": sorted(fields.get("competitions") or [])},
        "seasons": {"values": sorted(fields.get("seasons") or [])},
        "date_from": fields.get("date_from"),
        "date_to": fields.get("date_to"),
        "prediction_mode": fields.get("prediction_mode", "PRE_MATCH"),
        "query_fingerprint": fields.get("fingerprint", {}),
        "cohort_hash": fields.get("cohort_hash", ""),
    })


def cohort_to_dict(row) -> Dict[str, Any]:
    return {
        "cohort_id": row.cohort_id,
        "champion_artifact_id": row.champion_artifact_id,
        "challenger_artifact_id": row.challenger_artifact_id,
        "competitions": row.competitions,
        "seasons": row.seasons,
        "date_from": row.date_from.isoformat() if row.date_from else None,
        "date_to": row.date_to.isoformat() if row.date_to else None,
        "prediction_mode": row.prediction_mode,
        "query_fingerprint": row.query_fingerprint,
        "cohort_hash": row.cohort_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_cohort(db: Session, cohort_id: str) -> EvidenceCohort:
    row = db.query(EvidenceCohort).filter_by(cohort_id=cohort_id).first()
    if row is None:
        raise CohortError(f"unknown cohort: {cohort_id}",
                          code="UNKNOWN_COHORT")
    return row

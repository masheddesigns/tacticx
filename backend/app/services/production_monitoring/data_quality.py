"""Phase 28 data-quality monitoring.

Observes input quality feeding production predictions: readiness states,
feature availability, conflicts, duplicates, outcome/evaluation gaps.
States: DATA_VALID / DATA_DEGRADED / DATA_UNAVAILABLE / DATA_BLOCKED.
Missing data is reported, never treated as zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.evaluation_records import MatchOutcomeSnapshot
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.db.models.prematch import PreMatchReadinessCertificate
from app.db.models.reconciliation import ReconciliationConflict

from .contracts import (
    DATA_BLOCKED,
    DATA_DEGRADED,
    DATA_UNAVAILABLE,
    DATA_VALID,
    MONITORING_CONTRACT_VERSION,
    safe_rate,
)


def _latest_certs(db: Session) -> List[PreMatchReadinessCertificate]:
    rows = (db.query(PreMatchReadinessCertificate)
            .order_by(PreMatchReadinessCertificate.id.asc()).all())
    latest: Dict[int, PreMatchReadinessCertificate] = {}
    for row in rows:
        latest[row.match_id] = row
    return list(latest.values())


def readiness_quality(db: Session) -> Dict[str, Any]:
    """Readiness states across latest certificates per match."""
    latest = _latest_certs(db)
    counts = {"PREDICTION_READY": 0, "READY_DEGRADED": 0, "BLOCKED": 0}
    missing_required: Dict[str, int] = {}
    missing_optional: Dict[str, int] = {}
    duplicate_candidates = 0
    for cert in latest:
        if cert.readiness_state in counts:
            counts[cert.readiness_state] += 1
        for feat in (cert.missing_required_features or []):
            missing_required[feat] = missing_required.get(feat, 0) + 1
        for feat in (cert.missing_optional_features or []):
            missing_optional[feat] = missing_optional.get(feat, 0) + 1
        verdicts = cert.gate_verdicts or {}
        gate2 = verdicts.get("gate2_reconciliation", {}) \
            if isinstance(verdicts, dict) else {}
        if gate2.get("duplicate_state") == "DUPLICATE_CANDIDATE":
            duplicate_candidates += 1
    total = len(latest)
    if total == 0:
        state = DATA_UNAVAILABLE
    elif counts["BLOCKED"] == total:
        state = DATA_BLOCKED
    elif counts["BLOCKED"] > 0 or counts["READY_DEGRADED"] > 0:
        state = DATA_DEGRADED
    else:
        state = DATA_VALID
    return {
        "state": state,
        "certificate_count": total,
        "ready_count": counts["PREDICTION_READY"],
        "degraded_count": counts["READY_DEGRADED"],
        "blocked_count": counts["BLOCKED"],
        "readiness_rate": safe_rate(
            counts["PREDICTION_READY"] + counts["READY_DEGRADED"], total),
        "blocked_rate": safe_rate(counts["BLOCKED"], total),
        "missing_required_features": missing_required,
        "missing_optional_features": missing_optional,
        "duplicate_candidates": duplicate_candidates,
    }


def conflict_quality(db: Session) -> Dict[str, Any]:
    """Unresolved reconciliation conflicts (open, never inferred)."""
    total = db.query(ReconciliationConflict).count()
    unresolved = db.query(ReconciliationConflict).filter_by(
        resolution_status="unresolved").count()
    return {
        "state": DATA_VALID if unresolved == 0 else DATA_DEGRADED,
        "total_conflicts": total,
        "unresolved_conflicts": unresolved,
    }


def outcome_gaps(db: Session) -> Dict[str, Any]:
    """Finished predicted matches lacking outcome/evaluation coverage."""
    finished_predicted = (
        db.query(Match.id)
        .join(PreMatchPredictionSnapshot,
              PreMatchPredictionSnapshot.match_id == Match.id)
        .filter(Match.status == "FINISHED",
                Match.home_score.isnot(None),
                Match.away_score.isnot(None))
        .distinct().all()
    )
    finished_ids = [row[0] for row in finished_predicted]
    with_outcome = set()
    if finished_ids:
        with_outcome = {
            row[0] for row in
            db.query(MatchOutcomeSnapshot.match_id).filter(
                MatchOutcomeSnapshot.match_id.in_(finished_ids)).all()
        }
    missing = [mid for mid in finished_ids if mid not in with_outcome]
    total = len(finished_ids)
    return {
        "state": DATA_VALID if not missing else DATA_DEGRADED,
        "finished_predicted_count": total,
        "missing_outcomes": len(missing),
        "missing_outcome_rate": safe_rate(len(missing), total),
        "missing_outcome_match_ids": missing[:100],
    }


def data_quality_report(db: Session) -> Dict[str, Any]:
    """Combined data-quality report. Read-only."""
    readiness = readiness_quality(db)
    conflicts = conflict_quality(db)
    gaps = outcome_gaps(db)
    states = [readiness["state"], conflicts["state"], gaps["state"]]
    if DATA_BLOCKED in states:
        overall = DATA_BLOCKED
    elif DATA_DEGRADED in states:
        overall = DATA_DEGRADED
    elif all(s == DATA_UNAVAILABLE for s in states):
        overall = DATA_UNAVAILABLE
    else:
        overall = DATA_VALID
    return {
        "contract": MONITORING_CONTRACT_VERSION,
        "state": overall,
        "readiness": readiness,
        "conflicts": conflicts,
        "outcome_gaps": gaps,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

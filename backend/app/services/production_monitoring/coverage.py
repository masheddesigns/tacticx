"""Phase 28 production coverage funnel.

eligible → ready → predicted → completed → evaluated.

Source of truth: immutable production records (matches, readiness
certificates, prediction snapshots, outcome snapshots, evaluations).
Rates return None (unknown) on zero denominators — never zero.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.db.models.prematch import PreMatchReadinessCertificate
from app.services.prediction_execution.contracts import ELIGIBLE_READINESS

from .contracts import MONITORING_CONTRACT_VERSION, safe_rate


def _scope_match_ids(db: Session, competition: Optional[str],
                     season: Optional[str],
                     date_from: Optional[datetime],
                     date_to: Optional[datetime]) -> Set[int]:
    query = db.query(Match.id)
    need_league = competition is not None or season is not None
    if need_league:
        query = query.join(League, Match.league_id == League.id)
        if competition:
            query = query.filter(League.code == competition)
        if season:
            query = query.filter(League.season == season)
    if date_from is not None:
        query = query.filter(Match.kickoff_at >= date_from)
    if date_to is not None:
        query = query.filter(Match.kickoff_at <= date_to)
    return {row[0] for row in query.all()}


def _latest_certs(db: Session) -> Dict[int, PreMatchReadinessCertificate]:
    """Latest readiness certificate per match (single pass)."""
    rows = (db.query(PreMatchReadinessCertificate)
            .order_by(PreMatchReadinessCertificate.id.asc()).all())
    latest: Dict[int, PreMatchReadinessCertificate] = {}
    for row in rows:
        latest[row.match_id] = row
    return latest


def coverage_funnel(
    db: Session,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic funnel counts + rates. Read-only."""
    eligible = _scope_match_ids(db, competition, season, date_from, date_to)

    latest_certs = _latest_certs(db)
    ready = {mid for mid in eligible
             if mid in latest_certs
             and latest_certs[mid].readiness_state in ELIGIBLE_READINESS}

    snap_query = db.query(PreMatchPredictionSnapshot.match_id)
    if eligible:
        snap_query = snap_query.filter(
            PreMatchPredictionSnapshot.match_id.in_(eligible))
    if model_id:
        snap_query = snap_query.filter_by(model_id=model_id)
    if model_version:
        snap_query = snap_query.filter_by(model_version=model_version)
    predicted = {row[0] for row in snap_query.all()}

    finished = set()
    if predicted:
        finished = {
            row[0] for row in
            db.query(Match.id).filter(
                Match.id.in_(predicted),
                Match.status == "FINISHED",
                Match.home_score.isnot(None),
                Match.away_score.isnot(None)).all()
        }

    evaluated_matches: Set[int] = set()
    if predicted:
        scoped_snaps = db.query(
            PreMatchPredictionSnapshot.prediction_id,
            PreMatchPredictionSnapshot.match_id,
        ).filter(PreMatchPredictionSnapshot.match_id.in_(predicted))
        if model_id:
            scoped_snaps = scoped_snaps.filter_by(model_id=model_id)
        if model_version:
            scoped_snaps = scoped_snaps.filter_by(model_version=model_version)
        pid_to_mid = {pid: mid for pid, mid in scoped_snaps.all()}
        if pid_to_mid:
            evaluated_pids = {
                row[0] for row in
                db.query(PredictionEvaluationRecord.prediction_id).filter(
                    PredictionEvaluationRecord.prediction_id.in_(
                        list(pid_to_mid))).all()
            }
            evaluated_matches = {pid_to_mid[pid] for pid in evaluated_pids}

    eligible_count = len(eligible)
    ready_count = len(ready)
    predicted_count = len(predicted)
    completed_count = len(finished)
    evaluated_count = len(evaluated_matches)

    return {
        "contract": MONITORING_CONTRACT_VERSION,
        "filters": {"competition": competition, "season": season,
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "model_id": model_id, "model_version": model_version},
        "eligible_count": eligible_count,
        "ready_count": ready_count,
        "predicted_count": predicted_count,
        "completed_count": completed_count,
        "evaluated_count": evaluated_count,
        "prediction_readiness_rate": safe_rate(ready_count, eligible_count),
        "prediction_coverage_rate": safe_rate(predicted_count, ready_count),
        "completion_rate": safe_rate(completed_count, predicted_count),
        "evaluation_coverage_rate": safe_rate(evaluated_count, completed_count),
        "denominators": {
            "prediction_readiness_rate": eligible_count,
            "prediction_coverage_rate": ready_count,
            "completion_rate": predicted_count,
            "evaluation_coverage_rate": completed_count,
        },
    }

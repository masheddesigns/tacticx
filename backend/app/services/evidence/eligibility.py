"""Phase 33 eligibility audit + paired observation assembly.

A paired observation = one shadow evaluation row passing every check:
shadow row, outcome, feature snapshot (hash match), temporal validity,
champion cross-check. Exclusions counted with codes; nothing repaired.
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.evaluation_records import (
    MatchOutcomeSnapshot,
    PredictionEvaluationRecord,
)
from app.db.models.governance import (
    ShadowEvaluationRecord,
    ShadowPredictionSnapshot,
)
from app.db.models.prediction_snapshots import PredictionFeatureSnapshot
from app.services.features.temporal import as_naive_utc

from .cohort import get_cohort


def _league_of(db: Session, match_id: int):
    match = db.get(Match, match_id)
    if match is None or match.league_id is None:
        return None, None
    league = db.get(League, match.league_id)
    return match, league


def audit_cohort(db: Session, cohort) -> Dict[str, Any]:
    """Assemble eligible paired observations + exclusion ledger.

    Accepts a persisted EvidenceCohort row or an ephemeral cohort view
    (same attributes, no writes).
    """
    competitions = (cohort.competitions or {}).get("values", [])
    seasons = (cohort.seasons or {}).get("values", [])
    challenger = cohort.challenger_artifact_id

    query = db.query(ShadowEvaluationRecord)
    if challenger:
        query = query.filter_by(challenger_artifact_id=challenger)
    candidates = query.order_by(ShadowEvaluationRecord.id.asc()).all()
    # Deduplicate by shadow pair, keeping the latest evaluation row: a
    # corrected outcome produces a new evaluation, but the pair must not
    # double-count. Older rows remain immutable in the database.
    latest: Dict[str, Any] = {}
    for row in candidates:
        latest[row.shadow_id] = row
    candidates = [latest[key] for key in sorted(latest)]

    paired: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    temporal = {"temporal_valid": 0, "temporal_invalid": 0,
                "excluded_post_cutoff": 0, "excluded_unknown_timing": 0}

    for evaluation in candidates:
        shadow = db.query(ShadowPredictionSnapshot).filter_by(
            shadow_id=evaluation.shadow_id).first()
        if shadow is None:
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "SHADOW_ROW_MISSING"})
            continue
        match, league = _league_of(db, evaluation.match_id)
        if match is None:
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "MATCH_MISSING"})
            continue
        if competitions and (league is None
                             or league.code not in competitions):
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "FILTER_EXCLUDED"})
            continue
        if seasons and (league is None or league.season not in seasons):
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "FILTER_EXCLUDED"})
            continue
        if cohort.date_from is not None or cohort.date_to is not None:
            kickoff = as_naive_utc(match.kickoff_at)
            if kickoff is None:
                excluded.append({"evaluation_id": evaluation.evaluation_id,
                                 "code": "FILTER_EXCLUDED"})
                temporal["excluded_unknown_timing"] += 1
                continue
            from app.services.features.temporal import as_naive_utc as conv

            low = conv(cohort.date_from)
            high = conv(cohort.date_to)
            if (low is not None and kickoff < low) or \
                    (high is not None and kickoff > high):
                excluded.append({"evaluation_id": evaluation.evaluation_id,
                                 "code": "FILTER_EXCLUDED"})
                continue
        outcome = db.query(MatchOutcomeSnapshot).filter_by(
            match_id=evaluation.match_id,
            outcome_hash=evaluation.outcome_hash).first()
        if outcome is None:
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "OUTCOME_MISSING"})
            continue
        feature = db.query(PredictionFeatureSnapshot).filter_by(
            snapshot_id=shadow.feature_snapshot_id).first()
        if shadow.feature_snapshot_id is None or feature is None \
                or feature.snapshot_hash != shadow.feature_snapshot_hash:
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "FEATURE_MISMATCH"})
            temporal["temporal_invalid"] += 1
            continue
        cutoff = as_naive_utc(shadow.cutoff)
        kickoff = as_naive_utc(match.kickoff_at)
        if cutoff is None or kickoff is None:
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "UNKNOWN_TIMING"})
            temporal["excluded_unknown_timing"] += 1
            continue
        if not cutoff < kickoff:
            excluded.append({"evaluation_id": evaluation.evaluation_id,
                             "code": "POST_CUTOFF_VIOLATION"})
            temporal["temporal_invalid"] += 1
            temporal["excluded_post_cutoff"] += 1
            continue
        temporal["temporal_valid"] += 1
        champion_eval = None
        if shadow.production_prediction_id:
            champion_eval = db.query(PredictionEvaluationRecord).filter_by(
                prediction_id=shadow.production_prediction_id,
                outcome_hash=evaluation.outcome_hash).first()
        paired.append({
            "shadow_evaluation_id": evaluation.evaluation_id,
            "shadow_id": evaluation.shadow_id,
            "match_id": evaluation.match_id,
            "outcome_snapshot_id": evaluation.outcome_snapshot_id,
            "outcome_hash": evaluation.outcome_hash,
            "feature_snapshot_id": shadow.feature_snapshot_id,
            "feature_snapshot_hash": shadow.feature_snapshot_hash,
            "champion_artifact_id": evaluation.champion_artifact_id,
            "challenger_artifact_id": evaluation.challenger_artifact_id,
            "champion_metrics": evaluation.champion_metrics or {},
            "challenger_metrics": evaluation.challenger_metrics or {},
            "champion_eval_present": champion_eval is not None,
        })

    return {
        "cohort_id": cohort.cohort_id,
        "cohort_hash": cohort.cohort_hash,
        "candidates": len(candidates),
        "paired": paired,
        "paired_count": len(paired),
        "excluded": excluded,
        "excluded_count": len(excluded),
        "temporal": temporal,
    }


def audit_cohort_by_id(db: Session, cohort_id: str) -> Dict[str, Any]:
    """Audit a persisted cohort by id."""
    return audit_cohort(db, get_cohort(db, cohort_id))

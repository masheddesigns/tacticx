"""Phase 35 observation lifecycle accounting (read-only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.evaluation_records import (
    MatchOutcomeSnapshot,
    PredictionEvaluationRecord,
)
from app.db.models.evidence import EvidenceSnapshot
from app.db.models.governance import (
    ShadowEvaluationRecord,
    ShadowPredictionSnapshot,
)
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot
from app.db.models.prematch import PreMatchReadinessCertificate
from app.services.prediction_execution.contracts import ELIGIBLE_READINESS

from .contracts import (
    EXCLUDE_DUPLICATE,
    EXCLUDE_INSUFFICIENT_HISTORY,
    EXCLUDE_INVALID_PAIR,
    EXCLUDE_MISSING_OUTCOME,
    EXCLUDE_NOT_EVALUATED,
    EXCLUDE_NO_READINESS,
    EXCLUDE_NO_SHADOW,
    EXCLUDE_PENDING_OUTCOME,
    EXCLUDE_READINESS_BLOCKED,
    OBSERVATION_CONTRACT_VERSION,
)


def _scope_match_ids(db: Session, competition: Optional[str],
                     season: Optional[str]) -> Set[int]:
    query = db.query(Match.id)
    if competition is not None or season is not None:
        query = query.join(League, Match.league_id == League.id)
        if competition:
            query = query.filter(League.code == competition)
        if season:
            query = query.filter(League.season == season)
    return {row[0] for row in query.all()}


def _latest_certs(db: Session) -> Dict[int, PreMatchReadinessCertificate]:
    rows = (db.query(PreMatchReadinessCertificate)
            .order_by(PreMatchReadinessCertificate.id.asc()).all())
    latest: Dict[int, PreMatchReadinessCertificate] = {}
    for row in rows:
        latest[row.match_id] = row
    return latest


def observation_summary(
    db: Session,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
) -> Dict[str, Any]:
    """Funnel counts + exclusion reasons. Read-only."""
    discovered = _scope_match_ids(db, competition, season)
    certs = _latest_certs(db)
    matches = {m.id: m for m in db.query(Match).filter(
        Match.id.in_(discovered)).all()} if discovered else {}

    eligible: Set[int] = set()
    exclusions: Dict[str, int] = {}
    exclusion_details: Dict[str, List[int]] = {}

    def exclude(mid: int, code: str) -> None:
        exclusions[code] = exclusions.get(code, 0) + 1
        bucket = exclusion_details.setdefault(code, [])
        if len(bucket) < 50:
            bucket.append(mid)

    for mid in discovered:
        cert = certs.get(mid)
        if cert is None:
            exclude(mid, EXCLUDE_NO_READINESS)
            continue
        if cert.readiness_state not in ELIGIBLE_READINESS:
            reasons = cert.blocking_reasons or []
            blob = " ".join(str(r) for r in reasons)
            if "INSUFFICIENT_HISTORICAL_MATCHES" in blob:
                exclude(mid, EXCLUDE_INSUFFICIENT_HISTORY)
            else:
                exclude(mid, EXCLUDE_READINESS_BLOCKED)
            continue
        gate2 = (cert.gate_verdicts or {}).get("gate2_reconciliation", {}) \
            if isinstance(cert.gate_verdicts, dict) else {}
        if gate2.get("duplicate_state") in ("DUPLICATE_CONFIRMED",
                                            "DUPLICATE_RESOLUTION_REQUIRED"):
            exclude(mid, EXCLUDE_DUPLICATE)
            continue
        # Provider activation is informational, not a prediction gate:
        # the execution pipeline itself does not require ACTIVE.
        eligible.add(mid)

    provider_states: Dict[str, int] = {}
    for mid in eligible:
        cert = certs.get(mid)
        state = (cert.activation_state or "UNKNOWN") if cert else "UNKNOWN"
        provider_states[state] = provider_states.get(state, 0) + 1

    predicted = {row[0] for row in db.query(
        PreMatchPredictionSnapshot.match_id).all()} & discovered
    shadowed = {row[0] for row in db.query(
        ShadowPredictionSnapshot.match_id).all()} & discovered
    finished = {mid for mid in discovered
                if (matches.get(mid) is not None
                    and matches[mid].status == "FINISHED"
                    and matches[mid].home_score is not None
                    and matches[mid].away_score is not None)}
    with_outcome = {row[0] for row in db.query(
        MatchOutcomeSnapshot.match_id).all()} & discovered
    evaluated = _evaluated_matches(db, predicted)
    paired = {row[0] for row in db.query(
        ShadowEvaluationRecord.match_id).all()} & discovered
    included = paired  # latest evidence snapshots draw from paired rows

    # Per-match exclusion refinement for predicted-but-incomplete stages.
    for mid in predicted - finished:
        exclude(mid, EXCLUDE_PENDING_OUTCOME)
    for mid in finished & predicted - with_outcome:
        exclude(mid, EXCLUDE_MISSING_OUTCOME)
    for mid in predicted - shadowed:
        exclude(mid, EXCLUDE_NO_SHADOW)
    for mid in finished & predicted & with_outcome - evaluated:
        exclude(mid, EXCLUDE_NOT_EVALUATED)
    for mid in paired:
        shadow = db.query(ShadowPredictionSnapshot).filter_by(
            match_id=mid).order_by(
            ShadowPredictionSnapshot.id.desc()).first()
        if shadow is not None:
            from app.services.shadow_execution import validate_shadow_pair

            verdict = validate_shadow_pair(db, shadow.shadow_id)
            if not verdict.get("valid"):
                exclude(mid, EXCLUDE_INVALID_PAIR)

    last_activity = _last_activity(db)
    return {
        "contract": OBSERVATION_CONTRACT_VERSION,
        "filters": {"competition": competition, "season": season},
        "discovered": len(discovered),
        "eligible": len(eligible),
        "predicted": len(predicted),
        "shadowed": len(shadowed),
        "finished": len(finished),
        "outcome_verified": len(with_outcome),
        "evaluated": len(evaluated),
        "paired": len(paired),
        "included_in_evidence": len(included),
        "exclusions": exclusions,
        "exclusion_details": exclusion_details,
        "provider_states": provider_states,
        "last_activity": last_activity,
    }


def _latest_pred_id(db: Session, match_id: int) -> Optional[str]:
    from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

    row = (db.query(PreMatchPredictionSnapshot)
           .filter_by(match_id=match_id)
           .order_by(PreMatchPredictionSnapshot.id.desc()).first())
    return row.prediction_id if row else None


def _evaluated_matches(db: Session, predicted: Set[int]) -> Set[int]:
    out: Set[int] = set()
    for mid in predicted:
        pid = _latest_pred_id(db, mid)
        if pid is None:
            continue
        exists = db.query(PredictionEvaluationRecord).filter_by(
            prediction_id=pid).first()
        if exists is not None:
            out.add(mid)
    return out


def _last_activity(db: Session) -> Dict[str, Optional[str]]:
    def _max(model, column: str = "created_at"):
        row = db.query(model).order_by(model.id.desc()).first()
        value = getattr(row, column, None) if row else None
        return value.isoformat() if value is not None else None

    return {
        "acquisition": _max(Match, "updated_at"),
        "prediction": _max(PreMatchPredictionSnapshot),
        "shadow": _max(ShadowPredictionSnapshot),
        "outcome": _max(MatchOutcomeSnapshot),
        "evaluation": _max(PredictionEvaluationRecord),
        "evidence": _max(EvidenceSnapshot),
    }

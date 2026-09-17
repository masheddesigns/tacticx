"""Quality gating for prediction readiness (Phase 8).

Critical identity conflicts block prediction; irrelevant missing fields do
not. xG and unknown-timing rules from Phase 5/6 are preserved unchanged —
nothing here weakens a temporal gate to improve metrics. Data existence and
prediction usability stay distinct concepts.
"""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.reconciliation import ReconciliationConflict
from app.services.reconciliation import quality as quality_svc

# Conflict types that block prediction when unresolved.
BLOCKING_TYPES = {"score_mismatch", "team_mismatch", "league_mismatch",
                  "duplicate_source_match"}
# Missing fields that never block on their own.
NON_BLOCKING_MISSING = {"events", "lineups", "xg"}


def gating_decision(db: Session, match_id: int) -> Dict:
    """Allow / allow-without-xg / blocked + explicit reasons for one match."""
    match = db.get(Match, match_id)
    if match is None:
        return {"decision": "blocked", "reasons": ["match missing"]}
    reasons: List[str] = []
    # Field column stores "type:field"; blocking is decided on the type prefix.
    open_conflicts = db.query(ReconciliationConflict).filter(
        ReconciliationConflict.entity_type == "match",
        ReconciliationConflict.canonical_entity_id == match_id,
        ReconciliationConflict.resolution_status == "unresolved").all()
    blocking = [c for c in open_conflicts
                if c.field.split(":")[0] in BLOCKING_TYPES]
    if blocking:
        reasons.append(f"critical identity conflict blocks prediction: "
                       f"{sorted({c.field.split(':')[0] for c in blocking})}")
        return {"decision": "blocked", "reasons": reasons,
                "conflict_ids": [c.id for c in blocking]}
    assessment = quality_svc.assess_match(db, match_id)
    missing = [f for f in assessment.get("missing_fields", [])
               if f not in NON_BLOCKING_MISSING]
    if "score" in missing and match.status == "FINISHED":
        reasons.append("finished match without score: blocked")
        return {"decision": "blocked", "reasons": reasons}
    relevant_missing = [f for f in missing if f not in ("score",)]
    if relevant_missing:
        reasons.append(f"missing core fields: {relevant_missing}")
        return {"decision": "blocked", "reasons": reasons,
                "quality": assessment}
    notes = []
    for field in assessment.get("missing_fields", []):
        if field in NON_BLOCKING_MISSING:
            notes.append(f"{field} unavailable: prediction allowed without it")
    # Unknown timing: strict mode excludes the affected feature (unchanged rule).
    from app.services.features.temporal import TemporalMode

    notes.append("unknown-timing records excluded under strict mode "
                 "(Phase 5 rule preserved)")
    return {"decision": "allowed", "reasons": notes, "quality": assessment,
            "mode_note": TemporalMode.STRICT_PREMATCH.value}

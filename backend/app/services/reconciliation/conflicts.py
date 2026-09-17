"""Conflict taxonomy: severity, classification, resolution (Phase 8).

Severity policy (documented, reviewable):
  formatting difference      -> low
  statistic definition diff  -> medium
  kickoff disagreement       -> high
  score disagreement         -> critical

Resolution statuses: unresolved | accepted_source_a | accepted_source_b |
merged | definition_difference | not_comparable. The bare word "resolved"
is never stored without recording how.

Automatic resolution is restricted to low-risk cases: name capitalization,
minor punctuation, timezone representation, known aliases. Everything else
needs an explicit rule or manual resolution.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.reconciliation import ReconciliationConflict

SEVERITY_LOW, SEVERITY_MEDIUM, SEVERITY_HIGH, SEVERITY_CRITICAL = (
    "low", "medium", "high", "critical")

STATUS_UNRESOLVED = "unresolved"
STATUS_ACCEPTED_A, STATUS_ACCEPTED_B = "accepted_source_a", "accepted_source_b"
STATUS_MERGED = "merged"
STATUS_DEFINITION_DIFFERENCE = "definition_difference"
STATUS_NOT_COMPARABLE = "not_comparable"

CLASS_DEFINITION = "definition_difference"
CLASS_MEASUREMENT = "measurement_difference"
CLASS_TRUE_CONFLICT = "true_conflict"
CLASS_UNKNOWN = "unknown"

# conflict_type -> (severity, default classification)
SEVERITY_POLICY: Dict[str, tuple] = {
    "team_mismatch": (SEVERITY_HIGH, CLASS_TRUE_CONFLICT),
    "league_mismatch": (SEVERITY_HIGH, CLASS_TRUE_CONFLICT),
    "kickoff_mismatch": (SEVERITY_HIGH, CLASS_TRUE_CONFLICT),
    "season_mismatch": (SEVERITY_MEDIUM, CLASS_TRUE_CONFLICT),
    "status_mismatch": (SEVERITY_MEDIUM, CLASS_TRUE_CONFLICT),
    "score_mismatch": (SEVERITY_CRITICAL, CLASS_TRUE_CONFLICT),
    "duplicate_source_match": (SEVERITY_MEDIUM, CLASS_TRUE_CONFLICT),
    "statistic_mismatch": (SEVERITY_MEDIUM, CLASS_UNKNOWN),
    "event_mismatch": (SEVERITY_MEDIUM, CLASS_UNKNOWN),
    "player_mismatch": (SEVERITY_MEDIUM, CLASS_UNKNOWN),
    "odds_mismatch": (SEVERITY_LOW, CLASS_MEASUREMENT),
    "formatting_difference": (SEVERITY_LOW, CLASS_MEASUREMENT),
}


def dedup_key(entity_type: str, canonical_id: int, field: str,
              source_a: str, source_b: str, value_a: str, value_b: str) -> str:
    pair = "|".join(sorted([source_a or "", source_b or ""]))
    raw = f"{entity_type}:{canonical_id}:{field}:{pair}:{value_a}||{value_b}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def record_conflict(db: Session, entity_type: str, canonical_entity_id: int,
                    conflict_type: str, field: str,
                    source_a: str, source_b: str,
                    value_a, value_b,
                    classification: Optional[str] = None,
                    resolution_status: str = STATUS_UNRESOLVED,
                    resolved_by: str = "") -> ReconciliationConflict:
    """Idempotent persist: same disagreement returns the existing row."""
    severity, default_class = SEVERITY_POLICY.get(conflict_type, (SEVERITY_MEDIUM,
                                                                  CLASS_UNKNOWN))
    key = dedup_key(entity_type, canonical_entity_id, field, source_a, source_b,
                    str(value_a), str(value_b))
    existing = db.query(ReconciliationConflict).filter_by(dedup_key=key).first()
    if existing is not None:
        return existing
    row = ReconciliationConflict(
        entity_type=entity_type, canonical_entity_id=canonical_entity_id,
        field=f"{conflict_type}:{field}", source_a=source_a or "",
        source_b=source_b or "", value_a=str(value_a)[:500],
        value_b=str(value_b)[:500], severity=severity,
        classification=classification or default_class,
        resolution_status=resolution_status, resolved_by=resolved_by,
        resolved_at=datetime.now(timezone.utc) if resolution_status != STATUS_UNRESOLVED else None,
        dedup_key=key)
    db.add(row)
    db.commit()
    return row


def auto_resolvable(conflict_type: str, value_a, value_b) -> Optional[str]:
    """Low-risk auto-resolution. Returns a resolution status or None when
    manual/explicit handling is required."""
    if conflict_type != "formatting_difference":
        # Timezone representation: same instant, different rendering.
        if conflict_type == "kickoff_mismatch":
            try:
                from datetime import datetime as _dt

                a = _dt.fromisoformat(str(value_a).replace("Z", "+00:00"))
                b = _dt.fromisoformat(str(value_b).replace("Z", "+00:00"))
                if abs((a - b).total_seconds()) <= 60:
                    return STATUS_MERGED
            except Exception:
                return None
        return None
    a_norm = re.sub(r"[^a-z0-9]", "", str(value_a).lower())
    b_norm = re.sub(r"[^a-z0-9]", "", str(value_b).lower())
    if a_norm and a_norm == b_norm:
        return STATUS_MERGED
    return None


def summarize(db: Session) -> Dict:
    from sqlalchemy import func

    by_severity = dict(db.query(ReconciliationConflict.severity,
                                func.count()).group_by(
        ReconciliationConflict.severity).all())
    by_status = dict(db.query(ReconciliationConflict.resolution_status,
                              func.count()).group_by(
        ReconciliationConflict.resolution_status).all())
    by_field: Dict[str, int] = {}
    for (field,) in db.query(ReconciliationConflict.field).all():
        base = field.split(":")[0]
        by_field[base] = by_field.get(base, 0) + 1
    return {"total": sum(by_severity.values()), "by_severity": by_severity,
            "by_status": by_status, "by_type": by_field}

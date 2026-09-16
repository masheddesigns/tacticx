"""Source conflict detection + reconciliation (Phase 1.6).

Multiple sources may disagree (e.g. 2-1 vs 1-1). All observations are stored
in source_conflicts; canonical data is NEVER blindly overwritten.
Reconciliation follows the explicit SOURCE_PRIORITY configuration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.core import Match
from app.db.models.provenance import SourceConflict
from app.logging_config import get_logger

log = get_logger(__name__)


def _now():
    return datetime.now(timezone.utc)


def check_score(
    db: Session,
    match_id: int,
    source: str,
    home_score: Optional[int],
    away_score: Optional[int],
) -> Optional[SourceConflict]:
    """Record one source's score observation.

    - First observation sets nothing by itself; the canonical match keeps its
      existing score unless it has none (then the first known score fills it).
    - A differing observation opens/updates a MATCH_CONFLICT row.
    Returns the open conflict, if any.
    """
    if home_score is None or away_score is None:
        return None
    src = (source or "").lower()
    match = db.get(Match, match_id)
    if match is None:
        return None
    observed = [home_score, away_score]

    conflict = (
        db.query(SourceConflict)
        .filter_by(match_id=match_id, entity_type="match", field="score", status="open")
        .first()
    )
    values: dict = dict(conflict.values or {}) if conflict else {}
    if not values:
        if match.home_score is None and match.away_score is None:
            # Nothing known yet: first observation fills the canonical score.
            match.home_score, match.away_score = home_score, away_score
            db.commit()
            return None
        values["canonical"] = [match.home_score, match.away_score]
    values[src] = observed
    distinct = {tuple(v) for v in values.values() if isinstance(v, list) and len(v) == 2}

    if len(distinct) <= 1:
        # Agreement: fill canonical when empty; close any stale open conflict.
        if match.home_score is None:
            match.home_score, match.away_score = home_score, away_score
        if conflict:
            conflict.status = "resolved"
            conflict.resolution = f"observations converged: {observed}"
            conflict.resolved_at = _now()
        db.commit()
        return None

    if conflict is None:
        conflict = SourceConflict(match_id=match_id, entity_type="match", field="score",
                                  values=values, status="open")
        db.add(conflict)
    else:
        conflict.values = values
    db.commit()
    log.warning("MATCH_CONFLICT match=%s values=%s", match_id, values)
    return conflict


def reconcile_match(db: Session, match_id: int) -> Optional[SourceConflict]:
    """Apply SOURCE_PRIORITY: the highest-priority observed score becomes
    canonical; the conflict is marked resolved with an audit trail."""
    conflict = (
        db.query(SourceConflict)
        .filter_by(match_id=match_id, entity_type="match", field="score", status="open")
        .first()
    )
    if conflict is None:
        return None
    values: dict = dict(conflict.values or {})
    winner: Optional[str] = None
    for candidate in get_settings().source_priority_list:
        if candidate in values and candidate != "canonical":
            winner = candidate
            break
    if winner is None:
        # No prioritized source among observers — keep canonical, note why.
        conflict.status = "resolved"
        conflict.resolution = f"no prioritized source observed; canonical kept: {values}"
        conflict.resolved_at = _now()
        db.commit()
        return conflict
    score = values[winner]
    match = db.get(Match, match_id)
    if match is not None and isinstance(score, list) and len(score) == 2:
        match.home_score, match.away_score = int(score[0]), int(score[1])
    conflict.status = "resolved"
    conflict.resolution = f"winner={winner} score={score} (SOURCE_PRIORITY)"
    conflict.resolved_at = _now()
    db.commit()
    return conflict


# Tolerance for float-valued stat observations (xG models legitimately differ
# by small amounts). Within tolerance -> agreement. Beyond it -> both
# observations are preserved in a conflict row; canonical keeps first value.
STAT_TOLERANCE = 0.005


def check_stat_observation(
    db: Session,
    match_id: int,
    team: str,
    stat_name: str,
    value: float,
    source: str,
    tolerance: float = STAT_TOLERANCE,
) -> Optional[SourceConflict]:
    """Record one source's numeric stat observation (e.g. xG).

    Same-source refreshes and in-tolerance agreement return None. Genuine
    divergences open/update a statistic conflict row preserving every
    observation — never averaged, never silently overwritten.
    """
    from app.db.models.core import MatchStatistic

    try:
        observed = float(value)
    except (TypeError, ValueError):
        return None
    src = (source or "").lower()
    rows = (
        db.query(MatchStatistic)
        .filter_by(match_id=match_id, team=team, stat_name=stat_name, period="full")
        .all()
    )
    same_source = [r for r in rows if (r.source or "") == src]
    if same_source:
        return None  # refresh path handled by the caller; nothing to flag
    try:
        others = {r.source or "?": float(r.stat_value) for r in rows}
    except (TypeError, ValueError):
        return None
    if all(abs(v - observed) <= tolerance for v in others.values()) and others:
        return None  # agreement within tolerance
    if not others:
        return None  # first observation; caller persists it canonically

    conflict = (
        db.query(SourceConflict)
        .filter_by(match_id=match_id, entity_type="statistic",
                   field=f"{stat_name}:{team}", status="open")
        .first()
    )
    values: dict = dict(conflict.values or {}) if conflict else {}
    values.update({k: v for k, v in others.items()})
    values[src] = observed
    if conflict is None:
        conflict = SourceConflict(match_id=match_id, entity_type="statistic",
                                  field=f"{stat_name}:{team}", values=values, status="open")
        db.add(conflict)
    else:
        conflict.values = values
    db.commit()
    log.warning("STAT_CONFLICT match=%s stat=%s team=%s values=%s", match_id, stat_name, team, values)
    return conflict

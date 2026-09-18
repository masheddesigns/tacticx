"""Match universe: the set of matches TacticX knows about (Phase 11).

A read view over canonical matches + mappings + observations — no duplicate
table. Each entry carries identity, lifecycle, source count, first/last seen,
temporal and data quality.

Lifecycle derivation (deterministic, documented):
  rescheduled: >1 distinct observed kickoff for the match
  otherwise: direct map of canonical status (SCHEDULED/PRE_MATCH/LIVE/
    HALFTIME/FINISHED/POSTPONED/CANCELLED); abandoned is a CANCELLED-family
    detail preserved in observations, never a separate silent state;
    missing status/kickoff -> unknown.
Lifecycle is never inferred from score presence alone.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match, Team
from app.db.models.freshness import MatchObservation
from app.db.models.provenance import MatchSourceMapping

LIFECYCLE_ORDER = ("discovered", "scheduled", "rescheduled", "live",
                   "finished", "postponed", "cancelled", "abandoned", "unknown")


def lifecycle_of(db: Session, match: Match) -> Dict:
    kickoffs = {r.new_value for r in db.query(MatchObservation).filter_by(
        match_id=match.id, field="kickoff_at").all() if r.new_value}
    if match.kickoff_at is not None:
        kickoffs.add(str(match.kickoff_at))
    if len(kickoffs) > 1:
        lifecycle = "rescheduled"
    elif not match.status:
        lifecycle = "unknown"
    else:
        lifecycle = {"SCHEDULED": "scheduled", "PRE_MATCH": "scheduled",
                     "LIVE": "live", "HALFTIME": "live",
                     "FINISHED": "finished", "POSTPONED": "postponed",
                     "CANCELLED": "cancelled"}.get(match.status, "unknown")
    detail = None
    if lifecycle == "cancelled":
        rows = db.query(MatchObservation).filter_by(
            match_id=match.id, field="status").all()
        for row in rows:
            if (row.new_value or "").lower() in ("abandoned", "abd"):
                detail, lifecycle = "abandoned", "abandoned"
                break
    return {"lifecycle": lifecycle, "detail": detail,
            "distinct_kickoffs": len(kickoffs)}


def confidence_of(db: Session, match: Match) -> Dict:
    """Factual confidence (evidence-based): identity, sources, kickoff,
    competition, status, provenance. Never a probability of occurrence."""
    sources = {m.source for m in db.query(MatchSourceMapping).filter_by(
        match_id=match.id).all()}
    if match.provider:
        sources.add(match.provider)
    league = db.get(League, match.league_id) if match.league_id else None
    observations = db.query(MatchObservation).filter_by(match_id=match.id).count()
    signals = {
        "identity": match.home_team_id is not None and match.away_team_id is not None,
        "multi_source": len(sources) >= 2,
        "kickoff_known": match.kickoff_at is not None,
        "competition_known": league is not None,
        "status_known": bool(match.status),
        "provenance": observations > 0 or bool(match.provider_match_id),
    }
    score = sum(signals.values())
    if score >= 6:
        level = "high"
    elif score >= 4:
        level = "medium"
    elif score >= 2:
        level = "low"
    else:
        level = "unresolved"
    return {"level": level, "signals": signals, "source_count": len(sources)}


def entry(db: Session, match: Match) -> Dict:
    from app.services.reconciliation import quality as quality_svc

    league = db.get(League, match.league_id) if match.league_id else None
    home = db.get(Team, match.home_team_id) if match.home_team_id else None
    away = db.get(Team, match.away_team_id) if match.away_team_id else None
    first = db.query(MatchObservation).filter_by(match_id=match.id).order_by(
        MatchObservation.id.asc()).first()
    last = db.query(MatchObservation).filter_by(match_id=match.id).order_by(
        MatchObservation.id.desc()).first()
    assessment = quality_svc.assess_match(db, match.id)
    quality_label = assessment.get("quality", "unknown")
    temporal_quality = "verified" if match.kickoff_at is not None else "unknown"
    life = lifecycle_of(db, match)
    conf = confidence_of(db, match)
    return {
        "match_id": match.id,
        "competition": league.code if league else None,
        "season": league.season if league and league.season else None,
        "home_team": home.name if home else None,
        "away_team": away.name if away else None,
        "scheduled_kickoff": str(match.kickoff_at) if match.kickoff_at else None,
        "status": match.status,
        "lifecycle": life["lifecycle"],
        "lifecycle_detail": life["detail"],
        "source_count": conf["source_count"],
        "first_seen_at": str(first.observed_at) if first else None,
        "last_seen_at": str(last.observed_at) if last else None,
        "temporal_quality": temporal_quality,
        "data_quality": quality_label,
        "confidence": conf,
    }


def universe(db: Session, league_code: Optional[str] = None,
             status: Optional[str] = None, limit: int = 500) -> Dict:
    """Bounded universe view with agreement breakdown (true conflicts vs
    formatting/timezone/expected differences vs unresolved)."""
    from app.db.models.reconciliation import ReconciliationConflict

    query = db.query(Match)
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            return {"error": f"unknown league: {league_code}"}
        query = query.filter(Match.league_id == league.id)
    if status:
        query = query.filter(Match.status == status)
    matches = query.order_by(Match.id.asc()).limit(max(1, limit)).all()
    entries = [entry(db, m) for m in matches]
    conflicts = db.query(ReconciliationConflict).filter_by(
        entity_type="match").all()
    agreement = {"true_conflicts": 0, "formatting": 0, "timezone": 0,
                 "expected_provider_differences": 0, "unresolved": 0}
    for conflict in conflicts:
        ctype = (conflict.field or "").split(":")[0]
        if conflict.resolution_status != "unresolved":
            continue
        if ctype in ("score_mismatch", "team_mismatch", "league_mismatch",
                     "duplicate_source_match"):
            agreement["true_conflicts"] += 1
        elif ctype == "formatting_difference":
            agreement["formatting"] += 1
        elif ctype == "kickoff_mismatch":
            try:
                from datetime import datetime as _dt

                a = _dt.fromisoformat(str(conflict.value_a).replace("Z", "+00:00"))
                b = _dt.fromisoformat(str(conflict.value_b).replace("Z", "+00:00"))
                if abs((a - b).total_seconds()) <= 3600:
                    agreement["timezone"] += 1
                else:
                    agreement["true_conflicts"] += 1
            except Exception:
                agreement["unresolved"] += 1
        elif ctype == "status_mismatch":
            agreement["expected_provider_differences"] += 1
        else:
            agreement["unresolved"] += 1
    return {"matches": entries, "n": len(entries), "agreement": agreement}

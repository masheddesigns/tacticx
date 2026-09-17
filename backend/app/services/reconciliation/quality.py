"""Data-quality assessment (Phase 8).

Descriptive dimensions: identity_quality, temporal_quality, completeness,
source_agreement, provenance_quality. Numeric score with every component,
weight and threshold defined — no mysterious composite. Quality is NEVER
converted into a prediction probability.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.reconciliation import ReconciliationConflict

# Component weights (documented; sum to 1.0).
WEIGHTS = {"identity": 0.25, "temporal": 0.20, "completeness": 0.25,
           "agreement": 0.15, "provenance": 0.15}
THRESHOLD_HIGH, THRESHOLD_MEDIUM = 0.75, 0.45

EXPECTED_MATCH_FIELDS = ("league", "home_team", "away_team", "kickoff",
                         "status", "score")


def assess_match(db: Session, match_id: int) -> Dict:
    """Quality dimensions + score + label for one canonical match."""
    match = db.get(Match, match_id)
    if match is None:
        return {"error": "match missing"}
    identity = _identity_quality(match)
    temporal = _temporal_quality(match)
    completeness, missing = _completeness(match)
    agreement = _source_agreement(db, match_id)
    provenance = _provenance_quality(db, match_id)
    components = {"identity": identity, "temporal": temporal,
                  "completeness": completeness, "agreement": agreement,
                  "provenance": provenance}
    score = round(sum(components[k] * WEIGHTS[k] for k in WEIGHTS), 4)
    label = "high" if score >= THRESHOLD_HIGH else (
        "medium" if score >= THRESHOLD_MEDIUM else "low")
    return {"match_id": match_id, "components": components,
            "weights": dict(WEIGHTS),
            "thresholds": {"high": THRESHOLD_HIGH, "medium": THRESHOLD_MEDIUM},
            "score": score, "quality": label, "missing_fields": missing}


def _identity_quality(match: Match) -> float:
    if match.home_team_id is None or match.away_team_id is None:
        return 0.0
    if not match.provider_match_id:
        return 0.7
    return 1.0


def _temporal_quality(match: Match) -> float:
    # Verified kickoff present; unknown timing weakens even complete records.
    if match.kickoff_at is None:
        return 0.0
    return 1.0


def _completeness(match: Match) -> tuple:
    present, missing = [], []
    if match.league_id is not None:
        present.append("league")
    else:
        missing.append("league")
    for label, attr in (("home_team", "home_team_id"), ("away_team", "away_team_id"),
                        ("kickoff", "kickoff_at"), ("status", "status")):
        if getattr(match, attr):
            present.append(label)
        else:
            missing.append(label)
    if match.home_score is not None and match.away_score is not None:
        present.append("score")
    else:
        missing.append("score")
    return len(present) / len(EXPECTED_MATCH_FIELDS), missing


def _source_agreement(db: Session, match_id: int) -> float:
    rows = db.query(ReconciliationConflict).filter_by(
        entity_type="match", canonical_entity_id=match_id).all()
    if not rows:
        return 1.0
    critical = sum(1 for r in rows if r.severity in ("high", "critical")
                   and r.resolution_status == "unresolved")
    if critical:
        return 0.0
    open_rows = sum(1 for r in rows if r.resolution_status == "unresolved")
    return max(0.0, 1.0 - 0.2 * open_rows)


def _provenance_quality(db: Session, match_id: int) -> float:
    from app.db.models.provenance import MatchSourceMapping

    mappings = db.query(MatchSourceMapping).filter_by(match_id=match_id).all()
    if not mappings:
        return 0.5
    return 1.0 if len(mappings) >= 2 else 0.8


def league_completeness(db: Session, league_code: Optional[str] = None) -> Dict:
    """Expected vs available vs missing fields aggregated by league."""
    from app.db.models.core import League

    query = db.query(Match)
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            return {"error": f"unknown league: {league_code}"}
        query = query.filter(Match.league_id == league.id)
    matches = query.all()
    totals: Dict[str, int] = {f: 0 for f in EXPECTED_MATCH_FIELDS}
    for match in matches:
        _, missing = _completeness(match)
        for field in EXPECTED_MATCH_FIELDS:
            if field not in missing:
                totals[field] += 1
    n = len(matches)
    return {"matches": n, "league": league_code or "all",
            "available": totals,
            "missing": {f: n - totals[f] for f in EXPECTED_MATCH_FIELDS}}

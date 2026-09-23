"""Phase 28 provider/source quality monitoring.

Reuses Phase 19 qualification + Phase 24 activation systems. No second
qualification system. All measurements scoped provider x competition x
season where the underlying system supports it; scope limits documented
per measurement. Never infers provider quality from prediction
performance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.lifecycle import SourceHealth
from app.db.models.provenance import MatchSourceMapping
from app.db.models.reconciliation import ReconciliationConflict
from app.services.acquisition.activation import get_activation_state

from .contracts import MONITORING_CONTRACT_VERSION, safe_rate


def _league_ids(db: Session, competition: Optional[str],
                season: Optional[str]) -> Optional[List[int]]:
    if competition is None and season is None:
        return None
    query = db.query(League.id)
    if competition:
        query = query.filter(League.code == competition)
    if season:
        query = query.filter(League.season == season)
    return [row[0] for row in query.all()]


def provider_report(
    db: Session,
    *,
    provider: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
) -> Dict[str, Any]:
    """Scoped provider quality. Read-only."""
    league_ids = _league_ids(db, competition, season)

    match_query = db.query(Match)
    if provider:
        match_query = match_query.filter(Match.provider == provider)
    if league_ids is not None:
        match_query = match_query.filter(Match.league_id.in_(league_ids))
    matches = match_query.all()
    fixture_count = len(matches)
    result_count = sum(
        1 for m in matches
        if m.status == "FINISHED" and m.home_score is not None
        and m.away_score is not None)

    providers = sorted({m.provider for m in matches if m.provider})
    if provider:
        providers = [provider]

    per_provider: Dict[str, Any] = {}
    for prov in providers:
        prov_matches = [m for m in matches if m.provider == prov]
        prov_results = sum(
            1 for m in prov_matches
            if m.status == "FINISHED" and m.home_score is not None
            and m.away_score is not None)
        health = db.query(SourceHealth).filter_by(source=prov).first()
        freshness_age_hours = None
        if health is not None and health.updated_at is not None:
            updated = health.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            freshness_age_hours = round(
                (datetime.now(timezone.utc) - updated).total_seconds() / 3600.0, 2)
        mapped = 0
        if prov_matches:
            mapped = db.query(MatchSourceMapping.match_id).filter(
                MatchSourceMapping.source == prov,
                MatchSourceMapping.match_id.in_(
                    [m.id for m in prov_matches])).distinct().count()
        per_provider[prov] = {
            "provider": prov,
            "competition": competition,
            "season": season,
            "activation_state": get_activation_state(
                db, prov, competition, season),
            "fixture_count": len(prov_matches),
            "result_count": prov_results,
            "result_coverage_rate": safe_rate(prov_results, len(prov_matches)),
            "freshness_age_hours": freshness_age_hours,
            "source_state": health.state if health else None,
            "failure_count": health.failure_count if health else None,
            "last_error": health.last_error if health else None,
            "identity_mapped_matches": mapped,
        }

    unresolved_conflicts = db.query(ReconciliationConflict).filter_by(
        resolution_status="unresolved").count()

    return {
        "contract": MONITORING_CONTRACT_VERSION,
        "scope": {"provider": provider, "competition": competition,
                  "season": season},
        "fixture_count": fixture_count,
        "result_count": result_count,
        "providers": per_provider,
        "unresolved_conflicts_global": unresolved_conflicts,
        "scope_notes": "conflict counts are global (conflicts carry no "
                       "provider scope); activation uses actual Phase 24 "
                       "scoped state; quality is never inferred from "
                       "prediction performance",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

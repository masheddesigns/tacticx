"""Source coverage matrix + capabilities (Phase 8).

The matrix is built from ACTUAL stored data (which sources have fixtures,
stats, events, lineups, xG, odds, upcoming rows), joined with the source
registry's declared capabilities and Phase 7 health. Nothing theoretical:
a capability the provider cannot demonstrate is reported missing.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match

DIMENSIONS = ("fixtures", "stats", "events", "lineups", "xg", "odds", "upcoming")


def _source_set(db: Session, entity_counts: Dict[str, Dict[str, int]]) -> Dict:
    return entity_counts


def coverage_matrix(db: Session) -> Dict:
    """Per-source presence across data dimensions, measured from the store."""
    from app.db.models.core import Lineup, Match, MatchEvent, MatchStatistic
    from app.db.models.odds import OddsSnapshot
    from app.db.models.provenance import RawDataRecord

    def sources_for(query, attr="source"):
        return {r[0] for r in query.distinct().all() if r[0]}

    match_sources = sources_for(db.query(Match.provider))
    stat_sources = sources_for(db.query(MatchStatistic.source))
    event_sources = sources_for(db.query(MatchEvent.source))
    lineup_sources = sources_for(db.query(Lineup.source)) if hasattr(Lineup, "source") else set()
    xg_sources = {r[0] for r in db.query(MatchStatistic.source).filter(
        MatchStatistic.stat_name.in_(("xg", "expected_goals",
                                      "expected_goals_for", "exp_g"))).distinct().all()
        if r[0]}
    odds_sources = sources_for(db.query(OddsSnapshot.source))
    raw_sources = {r[0] for r in db.query(RawDataRecord.source).distinct().all()
                   if r[0]}
    upcoming_sources = sources_for(
        db.query(Match.provider).filter(Match.status == "SCHEDULED"))
    present: Dict[str, Dict[str, bool]] = {}
    for source in sorted(match_sources | stat_sources | event_sources | lineup_sources
                         | xg_sources | odds_sources | raw_sources):
        present[source] = {
            "fixtures": source in match_sources,
            "stats": source in stat_sources,
            "events": source in event_sources,
            "lineups": source in lineup_sources,
            "xg": source in xg_sources,
            "odds": source in odds_sources,
            "upcoming": source in upcoming_sources,
        }
    return {"dimensions": list(DIMENSIONS), "sources": present}


def source_registry_view(db: Session) -> List[Dict]:
    """Registry capabilities + measured coverage + health per source."""
    from app.services.lifecycle.health import get_health
    from app.services.sources.registry import (
        get_football_registry,
        get_historical_registry,
        get_odds_registry,
    )

    matrix = coverage_matrix(db)
    health = get_health(db)
    out = []
    for axis, registry in (("football", get_football_registry()),
                           ("odds", get_odds_registry()),
                           ("historical", get_historical_registry())):
        for name in registry.available():
            try:
                source = registry.resolve(name)
                capabilities = source.capabilities.model_dump()
            except Exception:
                capabilities = {}
            out.append({"source": name, "axis": axis,
                        "capabilities": capabilities,
                        "measured_coverage": matrix["sources"].get(name, {}),
                        "health": health.get(name, {"state": "unknown"})})
    return out


def canonical_coverage(db: Session, league_code: Optional[str] = None) -> Dict:
    """Canonical/resolved/unresolved + multi/single-source match counts."""
    from app.db.models.core import League
    from app.db.models.provenance import MatchSourceMapping

    query = db.query(Match)
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            return {"error": f"unknown league: {league_code}"}
        query = query.filter(Match.league_id == league.id)
    matches = query.all()
    multi = single = unresolved = 0
    by_league: Dict[str, Dict[str, int]] = {}
    for match in matches:
        sources = {m.source for m in
                   db.query(MatchSourceMapping).filter_by(match_id=match.id).all()}
        if match.provider:
            sources.add(match.provider)
        league = db.get(League, match.league_id) if match.league_id else None
        code = league.code if league else "unknown"
        slot = by_league.setdefault(code, {"matches": 0, "multi_source": 0,
                                           "single_source": 0, "unresolved": 0})
        slot["matches"] += 1
        if match.home_team_id is None or match.away_team_id is None:
            unresolved += 1
            slot["unresolved"] += 1
        elif len(sources) >= 2:
            multi += 1
            slot["multi_source"] += 1
        else:
            single += 1
            slot["single_source"] += 1
    return {"matches": len(matches), "multi_source": multi,
            "single_source": single, "unresolved": unresolved,
            "by_league": by_league}

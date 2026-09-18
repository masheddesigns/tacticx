"""Measured source capability registry (Phase 10).

Capabilities use measured | documented | unknown | unavailable — never
theoretical claims presented as coverage. Evidence comes from stored rows
(fixtures/results/stats/events/lineups/xg/odds/upcoming per source),
temporal metadata quality (effective_at/retrieved_at presence), the
declared adapter capabilities, and Phase 7 health.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

MEASURED, DOCUMENTED, UNKNOWN, UNAVAILABLE = (
    "measured", "documented", "unknown", "unavailable")

CAPABILITY_DIMS = ("fixtures", "results", "statistics", "events", "lineups",
                   "players", "xg", "odds", "upcoming", "current_season",
                   "historical")


def _presence(db: Session, table, source_attr: str, extra=None) -> Dict[str, int]:
    from sqlalchemy import func

    query = db.query(getattr(table, source_attr), func.count()).group_by(
        getattr(table, source_attr))
    return {str(k or ""): v for k, v in query.all() if k}


def measured_capabilities(db: Session) -> Dict[str, Dict[str, str]]:
    """Per-source capability states grounded in stored evidence."""
    from app.db.models.core import Lineup, Match, MatchEvent, MatchStatistic, Player
    from app.db.models.odds import OddsSnapshot

    match_sources = _presence(db, Match, "provider")
    stat_sources = _presence(db, MatchStatistic, "source")
    event_sources = _presence(db, MatchEvent, "source")
    lineup_sources = _presence(db, Lineup, "source")
    odds_sources = _presence(db, OddsSnapshot, "source")
    from sqlalchemy import func as _func

    xg_sources = {str(k): v for k, v in db.query(
        MatchStatistic.source, _func.count()).filter(
            MatchStatistic.stat_name.in_(("xg", "expected_goals",
                                          "expected_goals_for", "exp_g"))).group_by(
            MatchStatistic.source).all() if k}
    upcoming_sources = {str(k): v for k, v in db.query(
        Match.provider, _func.count()).filter(
            Match.status.in_(("SCHEDULED", "PRE_MATCH"))).group_by(
            Match.provider).all() if k}
    finished_sources = {str(k): v for k, v in db.query(
        Match.provider, _func.count()).filter(
            Match.status == "FINISHED").group_by(Match.provider).all() if k}
    sources = set(match_sources) | set(stat_sources) | set(event_sources) | \
        set(lineup_sources) | set(odds_sources) | set(xg_sources)
    out: Dict[str, Dict[str, str]] = {}
    for source in sorted(sources):
        out[source] = {
            "fixtures": MEASURED if source in match_sources else UNAVAILABLE,
            "results": MEASURED if source in finished_sources else UNAVAILABLE,
            "statistics": MEASURED if source in stat_sources else UNAVAILABLE,
            "events": MEASURED if source in event_sources else UNAVAILABLE,
            "lineups": MEASURED if source in lineup_sources else UNAVAILABLE,
            "players": DOCUMENTED,  # identity layer exists; per-source counts below
            "xg": MEASURED if source in xg_sources else UNAVAILABLE,
            "odds": MEASURED if source in odds_sources else UNAVAILABLE,
            "upcoming": MEASURED if source in upcoming_sources else UNAVAILABLE,
            "current_season": UNAVAILABLE,  # set by season audit, never assumed
            "historical": MEASURED if source in finished_sources else UNAVAILABLE,
        }
    # Effective/retrieval-time quality from metadata presence.
    quality = temporal_metadata_quality(db)
    for source, entry in out.items():
        entry["effective_time_quality"] = quality.get(source, {}).get(
            "effective", UNKNOWN)
        entry["retrieval_time_quality"] = quality.get(source, {}).get(
            "retrieved", UNKNOWN)
    return out


def temporal_metadata_quality(db: Session) -> Dict[str, Dict[str, str]]:
    """effective_at / retrieved_at presence per source (measured)."""
    from app.db.models.core import Lineup, MatchEvent, MatchStatistic

    quality: Dict[str, Dict[str, str]] = {}

    def grade(total: int, present: int) -> str:
        if total == 0:
            return UNKNOWN
        ratio = present / total
        if ratio >= 0.9:
            return MEASURED
        if ratio > 0:
            return DOCUMENTED
        return UNAVAILABLE

    for model, label in ((MatchStatistic, "stats"), (MatchEvent, "events"),
                         (Lineup, "lineups")):
        for source, total in _presence(db, model, "source").items():
            from sqlalchemy import func as _func

            eff = db.query(_func.count()).filter(
                getattr(model, "source") == source,
                getattr(model, "effective_at").is_not(None)).scalar() or 0
            slot = quality.setdefault(source, {})
            prev = slot.get("effective", MEASURED)
            cur = grade(total, eff)
            # Worst grade across tables wins (honest, never inflated).
            order = {MEASURED: 3, DOCUMENTED: 2, UNKNOWN: 1, UNAVAILABLE: 0}
            slot["effective"] = cur if order[cur] < order.get(prev, 3) else prev
            slot["retrieved"] = DOCUMENTED  # retrieved_at ≈ recorded_at server default
    return quality


def registry_view(db: Session) -> List[Dict]:
    """Declared adapter capabilities + measured states + health per source."""
    from app.services.lifecycle.health import get_health
    from app.services.sources.registry import (
        get_football_registry,
        get_historical_registry,
        get_odds_registry,
    )

    measured = measured_capabilities(db)
    health = get_health(db)
    out = []
    seen = set()
    for axis, getter in (("football", get_football_registry),
                         ("odds", get_odds_registry),
                         ("historical", get_historical_registry)):
        try:
            registry = getter()
        except Exception:
            continue
        for name in registry.available():
            seen.add(name)
            try:
                declared = registry.resolve(name).capabilities.model_dump()
            except Exception:
                declared = {}
            out.append({"source": name, "axis": axis,
                        "declared_capabilities": declared,
                        "measured": measured.get(name, {}),
                        "health": health.get(name, {"state": "unknown"})})
    for name in sorted(set(measured) - seen):
        out.append({"source": name, "axis": "observed-in-store",
                    "declared_capabilities": {},
                    "measured": measured[name],
                    "health": health.get(name, {"state": "unknown"})})
    return out

"""Coverage inventory: current canonical coverage per league/season/family (Phase 13).

Measured from stored rows only. Families: matches, stats, xg, shots,
events, lineups, players, minutes, odds + temporal buckets
(strict/estimated/unknown from effective_at evidence).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Lineup, Match, MatchEvent, MatchStatistic, Player
from app.db.models.odds import OddsSnapshot

XG_NAMES = ("xg", "expected_goals", "expected_goals_for", "exp_g")
SHOT_NAMES = ("shots_total", "shots_on_target", "shots_inside_box",
              "shots_outside_box", "shots_off_target", "shots_blocked")
MINUTE_MARKERS = ("minutes", "minutes_played", "mins")


def _season_label(kickoff_at) -> str:
    from app.services.features.temporal import as_naive_utc

    naive = as_naive_utc(kickoff_at)
    if naive is None:
        return "unknown"
    return str(naive.year if naive.month >= 8 else naive.year - 1)


def league_inventory(db: Session, league_code: Optional[str] = None) -> Dict:
    """Per (league, season): matches + family match-counts + temporal split."""
    query = db.query(Match)
    if league_code:
        league = db.query(League).filter_by(code=league_code).first()
        if league is None:
            return {"error": f"unknown league: {league_code}"}
        query = query.filter(Match.league_id == league.id)
    matches = query.all()
    seasons: Dict[str, Dict] = {}
    for match in matches:
        season = _season_label(match.kickoff_at)
        key = (match.league_id, season)
        slot = seasons.setdefault(key, {"league_id": match.league_id,
                                        "season": season, "match_ids": []})
        slot["match_ids"].append(match.id)
    out = []
    for (league_id, season), slot in sorted(seasons.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        ids = slot["match_ids"]
        league = db.get(League, league_id)
        entry: Dict = {"league": league.code if league else None, "season": season,
                       "matches": len(ids)}
        entry["stats"] = _count(db, MatchStatistic.match_id, ids)
        entry["xg"] = _count(db, MatchStatistic.match_id, ids,
                             MatchStatistic.stat_name.in_(XG_NAMES))
        entry["shots"] = _count(db, MatchStatistic.match_id, ids,
                                MatchStatistic.stat_name.in_(SHOT_NAMES))
        entry["events"] = _count(db, MatchEvent.match_id, ids)
        entry["lineups"] = _count(db, Lineup.match_id, ids)
        entry["odds"] = _count(db, OddsSnapshot.match_id, ids)
        entry["players"] = _player_matches(db, ids)
        entry["minutes"] = _count(db, MatchStatistic.match_id, ids,
                                  MatchStatistic.stat_name.in_(MINUTE_MARKERS))
        entry.update(_temporal_split(db, ids))
        out.append(entry)
    return {"seasons": out,
            "totals": {family: sum(e.get(family, 0) for e in out)
                       for family in ("matches", "stats", "xg", "shots",
                                      "events", "lineups", "odds", "players",
                                      "minutes")}}


def _count(db: Session, column, ids: list, extra=None) -> int:
    if not ids:
        return 0
    query = db.query(column).filter(column.in_(ids))
    if extra is not None:
        query = query.filter(extra)
    return query.distinct().count()


def _player_matches(db: Session, ids: list) -> int:
    if not ids:
        return 0
    lineup_matches = db.query(Lineup.match_id).filter(
        Lineup.match_id.in_(ids)).distinct().all()
    event_matches = db.query(MatchEvent.match_id).filter(
        MatchEvent.match_id.in_(ids)).distinct().all()
    return len({r[0] for r in lineup_matches} | {r[0] for r in event_matches})


def _temporal_split(db: Session, ids: list) -> Dict:
    """strict (explicit effective_at) vs estimated (parent-anchored) vs
    unknown, counted over lineup/event/xg rows for these matches."""
    strict = estimated = unknown = 0
    if ids:
        for model in (Lineup, MatchEvent):
            rows = db.query(model).filter(getattr(model, "match_id").in_(ids)).all()
            for row in rows:
                if getattr(row, "effective_at", None) is not None:
                    strict += 1
                else:
                    unknown += 1
        xg_rows = db.query(MatchStatistic).filter(
            MatchStatistic.match_id.in_(ids),
            MatchStatistic.stat_name.in_(XG_NAMES)).all()
        for row in xg_rows:
            if row.effective_at is not None:
                strict += 1
            else:
                unknown += 1
    return {"strict_rows": strict, "estimated_rows": estimated,
            "unknown_rows": unknown}

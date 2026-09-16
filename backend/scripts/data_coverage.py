"""Data coverage report (Phase 1.7).

Tells us whether the dataset is actually sufficient before Phase 2:

    python scripts/data_coverage.py --all
    python scripts/data_coverage.py --league EPL --season 2024
    python scripts/data_coverage.py --league EPL --season 2024 --json

Season grouping derives from kickoff (Aug-Jul season): a match kicking off
2024-09-21 belongs to season "2024". Percentages are matches-with-data over
matches in scope. Absent data is reported, never invented.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401
from app.db.models.core import (  # noqa: E402
    League,
    Lineup,
    Match,
    MatchEvent,
    MatchStatistic,
    Player,
)
from app.db.models.odds import OddsSnapshot  # noqa: E402
from app.db.models.provenance import RawDataRecord, SourceConflict  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.sources.stats_schema import (  # noqa: E402
    CARDS_STATS,
    CORNERS_STATS,
    FORMATION_STATS,
    POSSESSION_STATS,
    SHOTS_STATS,
    XG_STATS,
)


def season_label(kickoff) -> str:
    if kickoff is None:
        return "unknown"
    dt = kickoff
    return str(dt.year if dt.month >= 8 else dt.year - 1)


def _with_stat(db, ids: list[int], names: set[str]) -> set[int]:
    if not ids:
        return set()
    return {r[0] for r in db.query(MatchStatistic.match_id)
            .filter(MatchStatistic.match_id.in_(ids),
                    MatchStatistic.stat_name.in_(names)).distinct().all()}


def build_coverage(db, league: str = "", season: str = "") -> dict:
    leagues = db.query(League).all()
    if league:
        leagues = [lg for lg in leagues if lg.code == league]
    report: dict = {"leagues": {}}
    for lg in leagues:
        matches = db.query(Match).filter_by(league_id=lg.id).all()
        groups: dict[str, list] = {}
        for m in matches:
            groups.setdefault(season_label(m.kickoff_at), []).append(m)
        for season_key, season_matches in sorted(groups.items()):
            if season and season_key != season:
                continue
            ids = [m.id for m in season_matches]
            with_stats = {r[0] for r in db.query(MatchStatistic.match_id)
                          .filter(MatchStatistic.match_id.in_(ids)).distinct().all()} if ids else set()
            with_events = {r[0] for r in db.query(MatchEvent.match_id)
                           .filter(MatchEvent.match_id.in_(ids)).distinct().all()} if ids else set()
            with_lineups = {r[0] for r in db.query(Lineup.match_id)
                            .filter(Lineup.match_id.in_(ids)).distinct().all()} if ids else set()
            with_odds = {r[0] for r in db.query(OddsSnapshot.match_id)
                         .filter(OddsSnapshot.match_id.in_(ids)).distinct().all()} if ids else set()
            historical_odds = {r[0] for r in db.query(OddsSnapshot.match_id)
                               .filter(OddsSnapshot.match_id.in_(ids),
                                       OddsSnapshot.is_live.is_(False)).distinct().all()} if ids else set()
            team_ids = {m.home_team_id for m in season_matches} | \
                {m.away_team_id for m in season_matches}
            team_ids.discard(None)
            player_ids = {p.id for p in db.query(Player).filter(
                Player.team_id.in_(list(team_ids))).all()} if team_ids else set()
            by_source: dict[str, int] = {}
            for m in season_matches:
                src = (m.provider or "unknown") or "unknown"
                by_source[src] = by_source.get(src, 0) + 1
            report["leagues"][f"{lg.code} {season_key}"] = {
                "matches": len(ids),
                "statistics": len(with_stats),
                "shots": len(_with_stat(db, ids, SHOTS_STATS)),
                "possession": len(_with_stat(db, ids, POSSESSION_STATS)),
                "corners": len(_with_stat(db, ids, CORNERS_STATS)),
                "cards": len(_with_stat(db, ids, CARDS_STATS)),
                "xg": len(_with_stat(db, ids, XG_STATS)),
                "events": len(with_events),
                "lineups": len(with_lineups),
                "formations": len(_with_stat(db, ids, FORMATION_STATS)),
                "odds": len(with_odds),
                "historical_odds": len(historical_odds),
                "teams": len(team_ids),
                "players": len(player_ids),
                "sources": by_source,
            }
    report["unresolved_teams"] = db.query(RawDataRecord).filter_by(
        entity_type="team", processing_status="unresolved").count()
    report["unresolved_matches"] = db.query(RawDataRecord).filter_by(
        entity_type="match", processing_status="unresolved").count()
    report["quarantined"] = db.query(RawDataRecord).filter_by(
        processing_status="quarantined").count()
    report["failed"] = db.query(RawDataRecord).filter_by(
        processing_status="failed").count()
    report["conflicts_open"] = db.query(SourceConflict).filter_by(status="open").count()
    report["conflicts_resolved"] = db.query(SourceConflict).filter_by(status="resolved").count()
    tq: dict[str, int] = {}
    for quality in ("verified", "estimated", "unknown"):
        tq[quality] = db.query(RawDataRecord).filter_by(temporal_quality=quality).count()
    report["temporal_quality"] = tq
    return report


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.1f}%" if whole else "n/a"


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="League/season data coverage.")
    ap.add_argument("--league", default="")
    ap.add_argument("--season", default="")
    ap.add_argument("--all", action="store_true", dest="show_all",
                    help="All leagues/seasons (default when no filters given)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        report = build_coverage(db, args.league, args.season)
        if args.as_json:
            print(json.dumps(report, indent=2))
        else:
            for key, cov in report["leagues"].items():
                n = cov["matches"]
                print(f"\n{key}")
                print(f"Matches                  {n:>6}")
                print(f"Statistics               {cov['statistics']:>6}   {_pct(cov['statistics'], n)}")
                print(f"Shots                    {cov['shots']:>6}   {_pct(cov['shots'], n)}")
                print(f"Possession               {cov['possession']:>6}   {_pct(cov['possession'], n)}")
                print(f"Corners                  {cov['corners']:>6}   {_pct(cov['corners'], n)}")
                print(f"Cards                    {cov['cards']:>6}   {_pct(cov['cards'], n)}")
                print(f"xG                       {cov['xg']:>6}   {_pct(cov['xg'], n)}")
                print(f"Events                   {cov['events']:>6}   {_pct(cov['events'], n)}")
                print(f"Lineups                  {cov['lineups']:>6}   {_pct(cov['lineups'], n)}")
                print(f"Formations               {cov.get('formations', 0):>6}   {_pct(cov.get('formations', 0), n)}")
                print(f"Odds                     {cov['odds']:>6}   {_pct(cov['odds'], n)}")
                print(f"Historical odds          {cov['historical_odds']:>6}   {_pct(cov['historical_odds'], n)}")
                print(f"Teams                    {cov['teams']:>6}")
                print(f"Players                  {cov['players']:>6}")
                print(f"Sources                  {cov.get('sources', {})}")
            print(f"\nUnresolved teams:    {report['unresolved_teams']:>6}")
            print(f"Unresolved matches:  {report['unresolved_matches']:>6}")
            print(f"Quarantined:         {report['quarantined']:>6}")
            print(f"Failed:              {report['failed']:>6}")
            print(f"Conflicts open:      {report['conflicts_open']:>6}")
            print(f"Conflicts resolved:  {report['conflicts_resolved']:>6}")
            print("Temporal quality:")
            for quality in ("verified", "estimated", "unknown"):
                print(f"  {quality:<10} {report['temporal_quality'][quality]:>6}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

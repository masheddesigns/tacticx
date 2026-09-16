"""Dataset quality report (Phase 1.7).

Identifies: missing statistics, duplicate matches/source records, conflicting
results, unresolved teams/matches, missing xG, invalid values, suspicious
timestamps, and source coverage by season/league.

    python scripts/data_quality_report.py
    python scripts/data_quality_report.py --json

Human-readable by default, JSON with --json. Findings are reported, never
auto-repaired.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import func

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
    Team,
)
from app.db.models.odds import Bookmaker, Market, OddsSelection, OddsSnapshot  # noqa: E402
from app.db.models.provenance import RawDataRecord, SourceConflict  # noqa: E402
from app.db.session import get_engine, get_session_local  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.services.sources.stats_schema import XG_STATS  # noqa: E402


def build_report(db) -> dict:
    """Pure report builder (testable); main() handles session + printing."""
    now = datetime.now(timezone.utc)
    report: dict = {
        "leagues": db.query(League).count(),
        "teams": db.query(Team).count(),
        "matches": db.query(Match).count(),
        "players": db.query(Player).count(),
        "events": db.query(MatchEvent).count(),
        "statistics": db.query(MatchStatistic).count(),
        "lineups": db.query(Lineup).count(),
        "bookmakers": db.query(Bookmaker).count(),
        "markets": db.query(Market).count(),
        "odds_snapshots": db.query(OddsSnapshot).count(),
        "odds_selections": db.query(OddsSelection).count(),
        "matches_missing_teams": db.query(Match).filter(
            (Match.home_team_id.is_(None)) | (Match.away_team_id.is_(None))).count(),
        "matches_missing_kickoff": db.query(Match).filter(Match.kickoff_at.is_(None)).count(),
    }
    report["matches_with_odds"] = db.query(OddsSnapshot.match_id).distinct().count()
    report["odds_without_match"] = 0  # FK is non-nullable; would fail at insert

    # Duplicate canonical matches: same league + teams + kickoff.
    dupes = (
        db.query(Match.league_id, Match.home_team_id, Match.away_team_id, Match.kickoff_at)
        .group_by(Match.league_id, Match.home_team_id, Match.away_team_id, Match.kickoff_at)
        .having(func.count() > 1).all()
    )
    report["duplicate_matches"] = len(dupes)

    # Duplicate source records: same (source, entity, record id) ingested twice.
    dupes = (
        db.query(RawDataRecord.source, RawDataRecord.entity_type,
                 RawDataRecord.source_record_id)
        .group_by(RawDataRecord.source, RawDataRecord.entity_type,
                  RawDataRecord.source_record_id)
        .having(func.count() > 1).all()
    )
    report["duplicate_source_records"] = len(dupes)

    # Legacy provider-id duplicates (pre-1.6 ingestion paths).
    dupes = 0
    for _provider, _pid in db.query(Match.provider, Match.provider_match_id).group_by(
            Match.provider, Match.provider_match_id).having(func.count() > 1).all():
        dupes += 1
    report["duplicate_provider_match_ids"] = dupes

    # Conflicting results.
    report["conflicts_open"] = db.query(SourceConflict).filter_by(status="open").count()
    report["conflicts_resolved"] = db.query(SourceConflict).filter_by(status="resolved").count()

    # Unresolved identities.
    report["unresolved_teams"] = db.query(RawDataRecord).filter_by(
        entity_type="team", processing_status="unresolved").count()
    report["unresolved_matches"] = db.query(RawDataRecord).filter_by(
        entity_type="match", processing_status="unresolved").count()
    report["quarantined"] = db.query(RawDataRecord).filter_by(
        processing_status="quarantined").count()
    report["failed"] = db.query(RawDataRecord).filter_by(
        processing_status="failed").count()

    # Missing statistics / xG.
    match_ids = [m.id for m in db.query(Match.id).all()]
    with_any = {r[0] for r in db.query(MatchStatistic.match_id).distinct().all()} if match_ids else set()
    report["matches_missing_statistics"] = len(match_ids) - len(with_any & set(match_ids))
    with_xg = {r[0] for r in db.query(MatchStatistic.match_id)
               .filter(MatchStatistic.stat_name.in_(XG_STATS)).distinct().all()} if match_ids else set()
    report["matches_missing_xg"] = len(match_ids) - len(with_xg & set(match_ids))

    # Invalid values still in the store (defense in depth — pipeline should
    # have quarantined these, so any count here is a finding).
    invalid = 0
    for mid, hs, aws in db.query(Match.id, Match.home_score, Match.away_score).all():
        if (hs is not None and (hs < 0 or hs > 30)) or (aws is not None and (aws < 0 or aws > 30)):
            invalid += 1
    for _sid, value in db.query(MatchStatistic.id, MatchStatistic.stat_value).all():
        try:
            if float(str(value).rstrip("%")) < 0:
                invalid += 1
        except (TypeError, ValueError):
            pass  # non-numeric raw values are warnings, not invalid
    for _oid, price in db.query(OddsSelection.id, OddsSelection.odds).all():
        if not price > 1.0:
            invalid += 1
    report["invalid_values"] = invalid

    # Suspicious timestamps: kickoffs in the future for finished matches, or
    # kickoffs missing while a result exists.
    suspicious = 0
    for m in db.query(Match).all():
        try:
            kickoff = m.kickoff_at
            if kickoff is not None and kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            if m.status == "FINISHED" and kickoff is not None and kickoff > now:
                suspicious += 1
            elif kickoff is None and (m.home_score is not None or m.away_score is not None):
                suspicious += 1
        except TypeError:
            suspicious += 1
    report["suspicious_timestamps"] = suspicious

    # Source coverage by season (kickoff-derived) and by league.
    by_season: dict[str, dict[str, int]] = {}
    by_league: dict[str, dict[str, int]] = {}
    leagues = {lg.id: lg.code for lg in db.query(League).all()}
    for m in db.query(Match).all():
        code = leagues.get(m.league_id or -1, "?")
        if m.kickoff_at is None:
            season = "unknown"
        else:
            season = str(m.kickoff_at.year if m.kickoff_at.month >= 8 else m.kickoff_at.year - 1)
        for bucket, key in ((by_season, season), (by_league, code)):
            entry = bucket.setdefault(key, {"matches": 0, "sources": {}})
            entry["matches"] += 1
            src = (m.provider or "unknown") or "unknown"
            entry["sources"][src] = entry["sources"].get(src, 0) + 1
    report["source_coverage_by_season"] = by_season
    report["source_coverage_by_league"] = by_league

    stat_names = sorted({r[0] for r in db.query(MatchStatistic.stat_name).distinct().all()})
    report["statistic_types_present"] = stat_names
    for key in ("xg", "expected_goals"):
        report[f"has_{key}"] = any(key in name for name in stat_names)

    # No-look-ahead audit: records that may postdate the pre-match cutoff.
    # Flagged, never deleted — Phase 2 consumes these flags to filter.
    from app.services.quality import audit_leakage

    report["leakage"] = audit_leakage(db)
    return report


def main() -> int:
    configure_logging(get_settings().LOG_LEVEL)
    ap = argparse.ArgumentParser(description="Dataset quality findings.")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    Base.metadata.create_all(get_engine())
    db = get_session_local()()
    try:
        report = build_report(db)
        if args.as_json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print("== counts ==")
            for key in ("leagues", "teams", "matches", "players", "events", "statistics",
                        "lineups", "bookmakers", "markets", "odds_snapshots", "odds_selections"):
                print(f"  {key:<22} {report[key]:>8}")
            print("== findings (all should be explainable) ==")
            for key in ("matches_missing_teams", "matches_missing_kickoff",
                        "duplicate_matches", "duplicate_source_records",
                        "duplicate_provider_match_ids", "conflicts_open", "conflicts_resolved",
                        "unresolved_teams", "unresolved_matches", "quarantined", "failed",
                        "matches_missing_statistics", "matches_missing_xg",
                        "invalid_values", "suspicious_timestamps"):
                print(f"  {key:<28} {report[key]:>8}")
            print(f"  has_expected_goals:        {report['has_expected_goals']!s:>8}")
            leak = report.get("leakage", {"counts": {}, "total": 0, "examples": []})
            print("== no-look-ahead audit (LEAKAGE_RISK flags; never deleted) ==")
            print(f"  total flagged:           {leak.get('total', 0):>8}")
            for entity, count in sorted(leak.get("counts", {}).items()):
                print(f"  {entity:<28} {count:>8}")
            for ex in leak.get("examples", [])[:5]:
                print(f"    e.g. {ex['entity']} match={ex['match_id']} "
                      f"{ex['stat']} [{ex['reason']}]")
            print("== source coverage by season ==")
            for season, cov in sorted(report["source_coverage_by_season"].items()):
                print(f"  {season:<10} matches={cov['matches']:<6} sources={cov['sources']}")
            print("== source coverage by league ==")
            for code, cov in sorted(report["source_coverage_by_league"].items()):
                print(f"  {code:<10} matches={cov['matches']:<6} sources={cov['sources']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
